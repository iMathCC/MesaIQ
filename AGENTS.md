# Instruções para Agentes de Desenvolvimento (AGENTS.md) — MesaIQ

Este arquivo define os princípios, regras de conduta técnica, convenções de desenvolvimento e padrões arquiteturais que **o desenvolvedor e qualquer agente de IA** devem seguir rigorosamente ao trabalhar no repositório **MesaIQ**.

---

## 1. Princípios Gerais e Filosofia

1. **Documentação Antes da Execução**: Sempre leia a documentação (`README.md`, `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` e ADRs pertinentes) antes de propor alterações ou implementar novas funcionalidades.
2. **Respeito Estrito à Arquitetura**: O MesaIQ segue uma arquitetura de **Monólito Modular** com Clean Architecture/Hexagonal (separação estrita entre `presentation`, `application`, `domain` e `infrastructure`). Não quebre os limites das camadas.
3. **Escopo Delimitado**: Modifique apenas arquivos estritamente necessários para a tarefa atribuída. Não faça "faxinas", refatorações desnecessárias ou antecipações de entregas futuras.
4. **Segurança Primeiro**:
   - Nunca insira credenciais, tokens, chaves de API ou segredos no código ou em arquivos versionados.
   - Sempre utilize variáveis de ambiente validadas por `pydantic-settings`.
   - Trate o conteúdo de avaliações de clientes como **dado não confiável** (risco de prompt injection) sob a estratégia de defesa em profundidade. Não assuma que tags ou delimitadores previnem ataques sozinhos.
   - O assistente LLM jamais deve executar SQL arbitrário; apenas chamadas de ferramentas pré-autorizadas com argumentos tipados e validados.
   - Distinguir validação referencial (conferir no servidor se o `review_id` canônico citado consta nas avaliações recuperadas pela ferramenta) de fundamentação factual (garantir que as afirmações são sustentadas pelos dados recuperados, testado via benchmark). O frontend exibe `external_id`, `source_system` e trechos originais do banco, não citações textuais inventadas pelo modelo.
5. **Qualidade e Testes Contínuos**:
   - Nunca apague, ignore ou comente testes para resolver quebras de build.
   - Toda funcionalidade ou correção de bug deve vir acompanhada dos respectivos testes unitários ou de integração.
   - Não ignore avisos do linter e formatador (`ruff`) ou checagens estáticas de tipos (`mypy`).
6. **Controle de Versão e Comunicação**:
   - Não execute `git commit`, `git push` ou comandos de controle de versão a menos que seja explicitamente solicitado pelo usuário.
   - Sempre documente o racional de decisões técnicas relevantes e mantenha a documentação sincronizada caso um comportamento seja alterado.

---

## 2. Regras por Camada Arquitetural

### 2.1 Domain (`src/domain/`)
- Contém entidades puras, dataclasses nativas do Python, enums, value objects e regras de negócio invariantes.
- **Proibição**: O domínio não pode depender de Pydantic, SQLAlchemy, FastAPI, Gradio, Gemini SDK, PyTorch, HuggingFace ou qualquer biblioteca externa ou de infraestrutura.
- O domínio deve depender exclusivamente da biblioteca padrão do Python (`dataclasses`, `enum`, `typing`, `datetime`, `uuid`). Pydantic v2 é reservado para DTOs e validações nas camadas de Application e Presentation.

### 2.2 Application (`src/application/`)
- Contém casos de uso (use cases), serviços de orquestração (como verificação de citações), DTOs (Data Transfer Objects) e **interfaces abstratas / Protocols** (ports via `typing.Protocol`) para repositórios e provedores externos.
- Orquestra o fluxo de dados entre repositórios, serviços de IA e o domínio.
- Utiliza DTOs fortemente tipados (`AnalysisResult`, `LLMResponse`, `ToolCall`, etc.) em vez de dicionários genéricos (`dict`).
- **Proibição**: Não deve conter lógica específica de framework web (sem requisições HTTP, headers, respostas FastAPI ou componentes Gradio). Não deve instanciar clientes concretos de SDKs de terceiros diretamente.

### 2.3 Infrastructure (`src/infrastructure/`)
- Implementa os contratos definidos na camada de aplicação (adapters).
- Contém repositórios SQLAlchemy 2, migrations Alembic, integração com PostgreSQL/pgvector, clientes da API Google Gemini (`google-genai`), modelos de embeddings locais (`sentence-transformers` / `transformers`) e leitores de arquivos CSV.
- Chamadas para modelos de inferência local (embeddings) devem ser despachadas via thread pool para não bloquear o loop de eventos assíncrono.
- Todo acesso externo (I/O, rede, disco, banco) reside nesta camada.

### 2.4 Presentation (`src/presentation/`)
- Responsável pelos pontos de entrada da aplicação: FastAPI routers (APIs REST) e Gradio Blocks (UI conversacional, upload e visualizações analíticas).
- A interface Gradio é montada no FastAPI sob a rota `/app` via `gr.mount_gradio_app`.
- **Proibição**: Nenhuma regra de negócio deve ser implementada em rotas de API ou eventos de botões do Gradio. A camada de apresentação deve apenas delegar chamadas para os casos de uso da camada `application`.

---

## 3. Diretrizes de IA e LLM

1. **Abstração de Provedores**:
   - A camada de aplicação deve interagir com serviços de IA via interfaces abstratas (`LLMProvider`, `EmbeddingProvider`).
   - O uso do Google Gen AI SDK (`google-genai` / Gemini) deve ficar contido em `src/infrastructure/ai/gemini_adapter.py`.
2. **Structured Outputs e Versionamento**:
   - Sempre utilize esquemas estritos (Pydantic models) para instruir o modelo a gerar respostas estruturadas (análise de sentimentos, aspectos, resumos).
   - Registre o status da análise (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`), o identificador único da tentativa atual (`attempt_id` UUID para esgrima/fencing de concorrência) e os metadados de auditoria (`provider_name`, `model_name`, `prompt_version`, `attempt_count`, `error_summary`).
   - A persistência de resultados (`COMPLETED` ou `FAILED`) deve obrigatoriamente validar `attempt_id` e `status = 'PROCESSING'` via UPDATE condicional para rejeitar atualizações de tentativas obsoletas que perderam a reserva por timeout.
   - Permita múltiplas análises por avaliação com base na chave única `(review_id, provider_name, model_name, prompt_version)`. A análise vigente é determinada pela configuração ativa do sistema e não por ordenação temporal de modelos arbitrários.
3. **Embeddings Locais e Governança**:
   - O modelo de embeddings ativo no MVP é `intfloat/multilingual-e5-small` (384 dimensões).
   - O modelo e sua revisão (`model_revision`) devem ser registrados na entidade `ReviewEmbedding`. Vetores de modelos ou revisões incompatíveis jamais devem ser comparados; trocas de modelo exigem reconstrução integral de embeddings.
   - Garanta a convenção de prefixos:
     - Documentos/avaliações no banco: `passage: <texto da avaliação>`
     - Consultas do usuário para busca: `query: <texto da consulta>`
   - O cálculo de embeddings é local e executado em thread pool para não bloquear o event loop.
4. **Tool Calling Seguro e Citações Factuais**:
   - O assistente conversacional utiliza chamadas de ferramentas (*tool calling*).
   - As ferramentas permitidas são restritas: `get_review_metrics`, `get_top_issues`, `search_reviews`, `get_review_details`.
   - Cada ferramenta é uma função estritamente tipada com parâmetros validados.
   - O `restaurant_id` é injetado pelo contexto da sessão e não confiado ao modelo.
   - O assistente utiliza o identificador canônico interno `review_id` para referenciar evidências estruturadas nas ferramentas.
   - A aplicação verifica no servidor (`CitationVerifierService`) se o `review_id` citado consta nos dados recuperados pela ferramenta antes de exibir a resposta, apresentando ao usuário o `external_id` e o `source_system` com o texto original do banco.

---

## 4. Banco de Dados e Métricas

1. **Determinismo nas Métricas**:
   - Médias, contagens, distribuições e séries temporais são calculadas via SQL no PostgreSQL, nunca estimadas por LLMs.
2. **Armazenamento e Migrações**:
   - Toda alteração estrutural no banco de dados deve ser gerenciada pelo Alembic.
   - Índices parciais com subconsultas são terminantemente proibidos no PostgreSQL. Junções e checagens de existência (`LEFT JOIN` ou `NOT EXISTS`) com índices B-tree convencionais devem ser usadas para buscar análises pendentes ou com falha.
   - A busca vetorial no MVP é exata inicialmente; a criação de índices aproximados (HNSW com `vector_cosine_ops`) dependerá de benchmarks que justifiquem seu uso.
3. **Resiliência e Auditoria de Dados**:
   - Registros de `ImportJob` devem ser persistidos antes da leitura das linhas do CSV, associados obrigatoriamente a um `restaurant_id` e contabilizando: `rows_total = rows_imported + rows_skipped + rows_rejected`.
   - Avaliações importadas mantêm as datas separadas: `reviewed_at` (publicação original) e `imported_at` (ingestão no sistema), além do canal de procedência `source_system`.
   - Duplicatas identificadas por `(restaurant_id, source_system, external_id)` são ignoradas (`rows_skipped`) sem sobrescrever dados prévios no MVP.
   - A importação não acopla nem cria registros de análise; as análises são criadas sob demanda pelo `ProcessPendingReviewsUseCase`. Se uma análise falhar, a avaliação permanece persistida para posterior reprocessamento e a análise é marcada como `FAILED`.

---

## 5. Checklist de Verificação para Todo PR ou Entrega

Antes de considerar uma tarefa concluída, o desenvolvedor ou agente deve verificar:
- [ ] O código segue a tipagem estrita do Python 3.12 (Type hints completos).
- [ ] O linter e formatador (`ruff check .`, `ruff format --check .`) executam sem erros.
- [ ] O checador de tipos estáticos (`mypy .`) executa sem erros.
- [ ] A suíte de testes passa integralmente (`pytest`).
- [ ] Nenhuma chave de API ou segredo está em arquivos de código ou teste.
- [ ] Nenhuma dependência foi introduzida sem justificativa documentada.
- [ ] A documentação correspondente em `docs/` foi atualizada se houver mudança de contrato ou comportamento.
