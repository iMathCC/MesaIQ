# ADR-0003: Adoção do PostgreSQL com pgvector para Armazenamento Relacional e Vetorial

**Data:** 2026-11-08  
**Status:** Aceito  
**Decisor:** Desenvolvedor do Projeto (Estudante de Ciência da Computação)  

---

## 1. Contexto

O **MesaIQ** necessita de duas capacidades centrais de persistência de dados:
1. **Dados Relacionais Estritos e Transacionais (ACID):** Restaurantes, avaliações (`reviewed_at`, `imported_at`), análises versionadas de sentimentos com status (`ReviewAnalysis`), aspectos, auditoria de importações (`ImportJob` com chave estrangeira para `Restaurant`) e histórico de conversas (`ChatSession`/`ChatMessage`).
2. **Dados Vetoriais de Alta Dimensão:** Representações semânticas densas (*embeddings* de 384 dimensões gerados pelo `multilingual-e5-small`) para recuperação de feedbacks via busca por similaridade de cosseno (RAG).

Além disso, as métricas de negócio (distribuição de notas, evolução temporal, médias) precisam ser calculadas de forma determinística por consultas agregadas em banco de dados.

---

## 2. Problema

Como estruturar a camada de persistência para suportar simultaneamente operações relacionais ACID/SQL e busca vetorial eficiente, minimizando a complexidade operacional de infraestrutura e evitando a sincronização frágil entre múltiplos bancos de dados?

---

## 3. Decisão

Decidiu-se adotar o **PostgreSQL** equipado com a extensão vetorial **pgvector** como banco de dados unificado para dados relacionais e vetoriais.

Toda a modelagem e controle de versão de esquema serão realizados através de **SQLAlchemy 2** e migrações estruturadas no **Alembic**.

Para a busca vetorial e governança de embeddings:
- **Abordagem Inicial do MVP:** Utilização de busca vetorial exata (`ORDER BY embedding <=> :query_vec LIMIT :k`). Ela oferece precisão máxima, elimina a necessidade de calibragem prematura de hiperparâmetros e é perfeitamente adequada para a volumetria inicial do MVP.
- **Relação 1:0..1 e Modelo Único Ativo:** O MVP adota uma relação 1:0..1 entre `Review` e `ReviewEmbedding` sob um único modelo ativo (`intfloat/multilingual-e5-small`, 384 dimensões). A aplicação proíbe comparação de vetores heterogêneos; caso o modelo seja alterado, os embeddings devem ser integralmente reconstruídos.
- **Evolução Condicionada a Benchmark:** A criação de índices aproximados (como **HNSW** com operador `vector_cosine_ops`) será avaliada na Entrega 4 mediante testes de desempenho que demonstrem ganhos reais de latência sem degradação inaceitável de `Recall@5`.

Para identificação de avaliações, governança transacional e esgrima de tentativas:
- A identificação única das avaliações respeita `(restaurant_id, source_system, external_id)`.
- A descoberta de avaliações pendentes ou com falha utiliza consultas com `LEFT JOIN` ou `NOT EXISTS` apoiadas por índices B-tree, evitando predicados com subconsultas em índices parciais.
- A reserva individual atômica utiliza `FOR UPDATE OF r SKIP LOCKED LIMIT 1` e gera um novo `attempt_id` (UUID), persistindo o resultado via UPDATE condicional para prevenir que tentativas expiradas por timeout sobrescrevam o estado atual. Conexões transacionais não permanecem retidas durante requisições de rede ao LLM.

---

## 4. Alternativas Consideradas

### Alternativa 1: PostgreSQL Relacional + Banco Vetorial Dedicado (ex.: Pinecone, Qdrant, Chroma ou Milvus)
- **Descrição:** Manter os dados transacionais no PostgreSQL e exportar os embeddings para uma base vetorial externa.
- **Motivo da Rejeição:** 
  - **Problema do Dual-Write:** Exige coordenar transações distribuídas; se a escrita falhar em uma base, os dados ficam dessincronizados.
  - **Filtragem Complexa:** Consultas híbridas (ex.: "recupere avaliações negativas de delivery do restaurante X nos últimos 15 dias usando similaridade semântica") exigiriam tráfego de rede cruzado entre dois bancos ou pós-filtragem ineficiente na aplicação.
  - **Custo e Infraestrutura:** Pinecone introduziria dependência de serviço SaaS pago em nuvem; Qdrant/Milvus adicionariam mais um container de infraestrutura para gerenciar.

### Alternativa 2: SQLite com extensão vetorial (sqlite-vss / sqlite-vec)
- **Descrição:** Usar SQLite local em arquivo para simplicidade.
- **Motivo da Rejeição:** Não é adequado para ambientes concorrentes de produção com escrita assíncrona, não possui o mesmo ecossistema maduro de migrações e índices do PostgreSQL, e limitaria a escalabilidade futura da aplicação.

---

## 5. Consequências

### Consequências Positivas
- **Pilha de Infraestrutura Unificada:** Um único container de banco de dados (`pgvector/pgvector:pg16`) atende a 100% das necessidades de persistência do projeto.
- **Consultas Híbridas Nativas e Eficientes:** Permite realizar buscas vetoriais combinadas com filtros relacionais e agregadores em uma única query SQL (ex.: `WHERE restaurant_id = :id ORDER BY embedding <=> :query_vec LIMIT 5`).
- **Garantias ACID:** Consistência transacional imediata entre a avaliação de texto, suas tentativas de análise e seu respectivo vetor.
- **Governança via Alembic:** Todas as tabelas e índices relacionais/vetoriais são declarativos e versionados no repositório.

### Consequências Negativas
- **Consumo de Recursos para Volumes Elevados:** Operações de busca exata exigem escaneamento sequencial dos vetores. No entanto, para a base de demonstração do MVP (centenas a poucos milhares de registros), a latência permanece na ordem de milissegundos, permitindo postergar o índice HNSW para o momento em que benchmarks formais comprovem a necessidade.
