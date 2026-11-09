# Product Requirements Document (PRD) — MesaIQ

**Versão:** 1.1  
**Status:** Em revisão humana  
**Responsável pelo Projeto:** Desenvolvedor do Projeto (Estudante de Ciência da Computação)  
**Público-alvo:** Desenvolvedor, Avaliadores Técnicos e Agentes Autônomos de Desenvolvimento  

---

## 1. Visão Geral do Produto

O **MesaIQ** é uma plataforma de inteligência de avaliações (*Restaurant Feedback Intelligence*) projetada para proprietários e gestores de restaurantes. O sistema processa volumes expressivos de avaliações textuais não estruturadas de clientes, correlaciona dados semânticos com notas numéricas determinísticas e disponibiliza as descobertas através de dashboards analíticos e de um assistente conversacional inteligente fundamentado em evidências concretas.

O produto é concebido para operar de forma autônoma e independente de APIs fechadas ou plataformas proprietárias (como iFood ou Google Places), adotando um modelo desacoplado via ingestão padronizada de arquivos CSV estruturados.

---

## 2. O Problema e a Oportunidade

### 2.1 Cenário Atual
1. **Sobrecarga de Análise Manual**: Gestores de restaurantes recebem dezenas ou centenas de avaliações semanais. Ler e catalogar manualmente cada comentário é inviável no dia a dia operacional.
2. **Desconexão entre Notas e Motivos**: Painéis tradicionais mostram variações de métricas (ex.: nota média caiu de 4.7 para 4.1), mas são incapazes de indicar com exatidão *por que* isso ocorreu.
3. **Alucinação e Desconfiança em IA**: Soluções genéricas baseadas em LLM frequentemente inventam números ou tiram conclusões sem conseguir apontar quais clientes reais reclamaram de determinado prato ou serviço.

### 2.2 Proposta de Valor do MesaIQ
- **Análise Semântica Granular**: Cada avaliação é decomposta em aspectos operacionais específicos (`food_quality`, `delivery`, `packaging`, `customer_service`, `price_value`, `other`) com extração literal de evidências.
- **Histórico e Reprocessabilidade**: Suporte ao versionamento de análises de avaliações por provedor, modelo e prompt `(review_id, provider_name, model_name, prompt_version)`, com rastreabilidade de tentativas e estados (`PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`).
- **Métricas 100% Determinísticas**: Contagens, médias e séries temporais são calculadas estritamente em SQL no PostgreSQL, eliminando estimativas imprecisas de modelos de linguagem.
- **RAG e Tool Calling Seguro**: O assistente responde perguntas em linguagem natural ("O que os clientes estão falando sobre a embalagem dos pedidos de delivery?") consultando a base por busca vetorial via `review_id` canônico, com validação referencial no servidor e exibição de identificadores (`source_system`, `external_id`) e trechos originais autorizados.

---

## 3. Personas de Usuários

### Persona 1: Carlos Mendonça (Sócio e Gestor de Operações)
- **Perfil**: 38 anos, proprietário de uma hamburgueria artesanal com operação presencial e delivery forte.
- **Dores**: Não tem tempo para ler 300 avaliações por semana. Sabe que o delivery tem reclamações esporádicas, mas não sabe se o problema é o tempo de entrega, o ponto da carne ou o refrigerante quente.
- **Objetivo no MesaIQ**: Fazer perguntas diretas como: *"Quais foram as 3 maiores reclamações desta semana no delivery?"* e receber respostas diretas com links para os comentários reais.

### Persona 2: Amanda Vieira (Gerente de Qualidade e Atendimento)
- **Perfil**: 29 anos, responsável pela experiência do cliente em uma unidade de restaurante gastronômico.
- **Dores**: Precisa tabular dados em planilhas para apresentar relatórios mensais para a diretoria. O processo manual leva dias e atrasa ações corretivas na cozinha e no salão.
- **Objetivo no MesaIQ**: Importar o fechamento mensal em CSV, visualizar a distribuição de sentimentos por categoria e extrair insights consolidados em poucos minutos.

---

## 4. Escopo da Primeira Versão (MVP)

### 4.1 Em Escopo
1. **Ingestão de Dados e Auditoria**: Upload e processamento síncrono controlado de arquivos CSV com identificação de origem (`source_system`), validação de esquema, deduplicação por chave única `(restaurant_id, source_system, external_id)` e registro prévio de auditoria em `ImportJob`.
2. **Processamento Semântico com LLM**: Classificação de sentimento geral, geração de resumo e identificação de aspectos específicos com evidências textuais usando Structured Outputs, com suporte a reprocessamento de falhas e chave de rastreamento `(review_id, provider_name, model_name, prompt_version)`.
3. **Métricas Determinísticas**: Painel analítico com contagens exatas, médias e correlações calculadas exclusivamente em SQL.
4. **Embeddings Locais e Busca Vetorial**: Geração local de embeddings com modelo ativo único `multilingual-e5-small` (384 dimensões) em thread pool e busca vetorial exata inicial via `pgvector`.
5. **Chatbot com Tool Calling e Citações Validadas**: Assistente conversacional restrito a um catálogo de ferramentas aprovadas, proibindo SQL arbitrário, com validação referencial no servidor e exibição de dados e trechos originais do banco.
6. **Interface Unificada**: Aplicação interativa em Gradio Blocks montada sob `/app` no FastAPI.

### 4.2 Fora do Escopo da v1 (Não implementar no MVP)
- Infraestrutura de filas duráveis e mensageria distribuída (Celery, Redis, RabbitMQ, Kafka).
- Integrações automáticas via scraping ou APIs privadas de terceiros (iFood, Rappi, Google Reviews, TripAdvisor).
- Multi-tenancy com isolamento estrito de organizações e autenticação complexa (o MVP foca em um restaurante de demonstração).
- Resposta automática aos clientes nas plataformas de origem.
- Fine-tuning supervisionado de modelos de linguagem.

---

## 5. Requisitos Funcionais (RF)

| ID | Requisito Funcional | Descrição Detalhada |
|---|---|---|
| **RF-01** | **Ingestão, Auditoria e Deduplicação de CSV** | O sistema deve aceitar arquivos CSV contendo avaliações (`external_id`, `rating`, `content`, `reviewed_at`, e opcionalmente `source_system`), persistir previamente o registro de `ImportJob` com status `PROCESSING`, validar tipos e campos obrigatórios, descartar registros inválidos (`rows_rejected`), ignorar duplicatas existentes no banco (`rows_skipped` com base na restrição única `restaurant_id, source_system, external_id`), persistir novas avaliações válidas (`rows_imported`), associando a data da importação (`imported_at`), e atualizar o job com status `COMPLETED` garantindo que `rows_total = rows_imported + rows_skipped + rows_rejected`. |
| **RF-02** | **Análise Granular de Feedbacks e Versionamento** | O sistema deve submeter avaliações pendentes ao LLM via Structured Outputs para extrair: sentimento geral (`positive`, `neutral`, `negative`), resumo em uma frase, e uma lista de aspectos com categoria (`food_quality`, `delivery`, `packaging`, `customer_service`, `price_value`, `other`), sentimento do aspecto e trecho literal como evidência. Cada análise deve ser registrada em `ReviewAnalysis` com estados `PENDING`, `PROCESSING`, `COMPLETED` ou `FAILED`, respeitando a restrição única `(review_id, provider_name, model_name, prompt_version)`. A análise vigente é determinada pela configuração ativa centralizada. |
| **RF-03** | **Rastreabilidade, Esgrima de Tentativas e Recuperação de Falhas** | Toda análise deve persistir metadados técnicos de auditoria (`provider_name`, `model_name`, `prompt_version`, `attempt_count`, `attempt_id`, `error_summary`, `started_at`, `finished_at`, `created_at`). Cada reserva atômica gera um novo `attempt_id` (UUID). Análises que permaneçam em `PROCESSING` com `started_at < :stale_before` (calculado via parâmetro `ANALYSIS_PROCESSING_TIMEOUT_SECONDS`) são marcadas como `FAILED`. A persistência de resultados (`COMPLETED` ou `FAILED`) valida estritamente `attempt_id` e status `PROCESSING` via UPDATE condicional, rejeitando atualizações tardias de tentativas que perderam autoridade. |
| **RF-04** | **Cálculo de Métricas Determinísticas** | O sistema deve calcular indicadores analíticos exclusivamente via consultas agregadas no PostgreSQL (total de avaliações, nota média geral, distribuição de notas de 1 a 5, distribuição de sentimentos e evolução temporal por `reviewed_at`). |
| **RF-05** | **Geração de Embeddings Locais e Governança** | O sistema deve gerar embeddings vetoriais de 384 dimensões para o texto das avaliações utilizando o modelo ativo único `intfloat/multilingual-e5-small` executado fora da thread assíncrona principal (via thread pool), aplicando estritamente o prefixo `passage:` para documentos e `query:` para buscas semânticas, mantendo registro da versão e revisão do checkpoint (`model_revision`) e sem comparar vetores de modelos heterogêneos. |
| **RF-06** | **Assistente Conversacional com Ferramentas Fortemente Tipadas** | O assistente deve manter histórico de conversas e responder a perguntas do usuário executando exclusivamente chamadas de ferramentas pré-autorizadas com esquemas Pydantic dedicados (`get_review_metrics`, `get_top_issues`, `search_reviews`, `get_review_details`), proibindo a geração ou execução de código SQL arbitrário. O contexto do restaurante (`restaurant_id`) é injetado pela aplicação. O assistente referencia avaliações via `review_id` canônico interno. Respostas de métricas numéricas preservam os valores originais retornados pelas consultas SQL sem exibição de código interno. |
| **RF-07** | **Validação Referencial no Servidor e Citações Fundamentadas** | A aplicação deve verificar rigorosamente no servidor as citações apresentadas pelo assistente, distinguindo validação referencial (conferir se o `review_id` citado consta nos registros recuperados pelas ferramentas naquela resposta) de fundamentação factual. O frontend deve apresentar trechos originais e identificadores (`external_id`, `source_system`) recuperados do banco, rejeitando referências desconhecidas. Respostas sem evidências suficientes devem explicitar tal limitação. |

---

## 6. Requisitos Não Funcionais (RNF)

| ID | Categoria | Requisito Não Funcional |
|---|---|---|
| **RNF-01** | **Segurança** | Credenciais e chaves de API (ex.: `GEMINI_API_KEY`) devem ser lidas exclusivamente de variáveis de ambiente gerenciadas por `pydantic-settings`. Nenhum arquivo com segredos (`.env`) deve ser versionado. |
| **RNF-02** | **Defesa em Profundidade contra Injeção** | Todo conteúdo textual de avaliações deve ser tratado como dado não confiável (*untrusted input*), isolado de instruções do sistema. A segurança baseia-se em defesa em profundidade: separação de prompts, ferramentas somente de leitura, validação tipada de parâmetros, verificação de citações no servidor e testes com payloads adversariais. Não se deve assumir que tags ou delimitadores forneçam imunidade completa contra prompt injection. |
| **RNF-03** | **Confiabilidade e Resiliência** | A ingestão de avaliações deve persistir os dados brutos no banco antes da execução da análise de IA. Falhas na API do provedor de LLM ou estouro de limites de requisição registram o status `FAILED` na análise correspondente, preservando a avaliação original intacta para reprocessamento controlado posterior. |
| **RNF-04** | **Eficiência e Custos** | Embeddings semânticos devem ser processados localmente em CPU/GPU sem custo de chamadas a APIs externas. O sistema não deve reprocessar avaliações que já possuam análise com status `COMPLETED` para a mesma combinação de `model_name` e `prompt_version`. |
| **RNF-05** | **Arquitetura e Tipagem** | A arquitetura deve seguir o padrão Monólito Modular / Clean Architecture com tipagem estrita no Python 3.12, verificação estática via `mypy` e checagem de código com `ruff`. |
| **RNF-06** | **Qualidade de Software** | Cobertura de testes unitários para regras de domínio e casos de uso, testes de integração para persistência e validação contínua em pipeline de CI (GitHub Actions). |

---

## 7. Casos de Uso Principais

### UC-01: Importar Lote de Avaliações
- **Ator**: Gestor do Restaurante.
- **Pré-condição**: Arquivo CSV disponível no formato esperado (`external_id`, `rating`, `content`, `reviewed_at`, opcional `source_system`).
- **Fluxo Principal**:
  1. O usuário faz upload do arquivo CSV pela aba de importação da interface Gradio, definindo o `source_system` (ex.: `manual_import`, `synthetic_dataset`).
  2. A aplicação cria e persiste imediatamente um registro `ImportJob` vinculado ao `restaurant_id` com status `PROCESSING` e data `started_at`.
  3. A importação permanece desacoplada do provedor de IA (não cria instâncias de análise no momento da importação).
  4. O parser processa o arquivo linha a linha de forma síncrona controlada:
     - Linhas malformadas, com notas fora do intervalo [1..5] ou datas inválidas são contabilizadas em `rows_rejected`.
     - Registros cujo `external_id` já exista para aquele restaurante e `source_system` são contabilizados em `rows_skipped` (sem sobrescrever registros existentes no MVP).
     - Registros válidos e inéditos são inseridos na tabela `reviews` com `source_system`, `reviewed_at` e `imported_at` preenchidos e contabilizados em `rows_imported`.
  5. O job é atualizado com status `COMPLETED`, `finished_at` e contadores calculados (`rows_total = rows_imported + rows_skipped + rows_rejected`).
  6. A interface exibe o resumo com a quantidade de avaliações importadas, ignoradas e rejeitadas.
- **Exceção**: Se ocorrer erro fatal no arquivo (ex.: CSV ilegível), o job é atualizado para `FAILED` com descrição em `error_summary` e mensagem para o usuário.

### UC-02: Processar Análises Semânticas e Embeddings (Controlado)
- **Ator**: Usuário ou Caso de Uso de Aplicação (`ProcessPendingReviewsUseCase`).
- **Pré-condição**: Avaliações persistidas sem análise concluída ou com falha para a configuração ativa de IA.
- **Fluxo Principal**:
  1. **Recuperação de Análises Abandonadas**: Rotina controlada identifica registros `ReviewAnalysis` em status `PROCESSING` cujo `started_at < :stale_before` (onde `stale_before = NOW() - INTERVAL(ANALYSIS_PROCESSING_TIMEOUT_SECONDS)`). Esses registros são atualizados condicionalmente para `FAILED` com `error_summary="Timeout de processamento excedido (tentativa abandonada)"` e `finished_at=NOW()`.
  2. **Ciclo Transacional de Reserva Individual com Fencing Token**:
     - *Passo 1*: Abre transação de banco.
     - *Passo 2*: Executa seleção elegível com bloqueio e salto de concorrência (`FOR UPDATE OF r SKIP LOCKED LIMIT 1`).
     - *Passo 3*: Gera um novo `attempt_id = uuid4()`. Insere ou atualiza o registro em `ReviewAnalysis` para `status = 'PROCESSING'`, incrementa `attempt_count`, define o novo `attempt_id` e registra `started_at = NOW()`.
     - *Passo 4*: Confirma e encerra a transação de banco imediatamente. Locks são liberados antes de qualquer chamada externa.
  3. **Execução Externa Fora de Transação**: O provedor de LLM é acionado via rede de forma assíncrona/desacoplada de locks de banco.
  4. **Persistência Condicional do Resultado (Esgrima de Concorrência)**:
     - *Passo 5*: Abre nova transação de banco de curta duração.
     - *Passo 6*: Executa `UPDATE review_analyses SET status = 'COMPLETED', finished_at = NOW() WHERE id = :analysis_id AND attempt_id = :attempt_id AND status = 'PROCESSING'`.
     - *Passo 7*: A aplicação confere se `rows_affected == 1`. Se zero registros foram atualizados, a tentativa perdeu autoridade (sofreu timeout/recuperação prévia) e o resultado tardio é rejeitado e descartado.
     - *Passo 8*: Em caso de sucesso na atualização, persiste `ReviewAspect`. Se a chamada original tiver falhado por erro da API, a transição para `FAILED` também exige conferência de `attempt_id` e `status = 'PROCESSING'`.
     - *Passo 9*: Confirma a transação.
  5. Para avaliações sem embedding para o modelo ativo, o provedor local gera o vetor (`passage: {content}`) fora da thread principal (thread pool) e persiste em `ReviewEmbedding` (1:0..1) com `model_name` e `model_revision`.

### UC-03: Consulta Conversacional via Chatbot
- **Ator**: Gestor do Restaurante.
- **Pré-condição**: Dados importados e analisados no banco.
- **Fluxo Principal**:
  1. O usuário envia uma mensagem: *"Por que os clientes reclamaram da batata frita nos últimos dias?"*.
  2. O caso de uso carrega o histórico da sessão e injeta o `restaurant_id` da sessão ativa no contexto de execução.
  3. O LLM recebe a mensagem junto com as definições tipadas das ferramentas autorizadas.
  4. O LLM emite uma chamada de ferramenta validada pelo schema correspondente (ex.: `SearchReviewsArgs(query="batata frita murcha fria", limit=5)`).
  5. A aplicação executa a busca vetorial no `pgvector`, obtém as avaliações mais similares e formata o resultado como `ToolResult`, registrando a lista autorizada de `review_id` (UUIDs canônicos internos).
  6. O LLM formula a resposta estruturada referenciando o `review_id` das avaliações usadas.
  7. O `CitationVerifierService` no servidor executa a validação referencial: verifica se todos os `review_id` citados constam de fato entre os registros retornados na etapa 5. Citações a IDs não recuperados são rejeitadas.
  8. O frontend apresenta os identificadores amigáveis (`source_system` e `external_id`) e trechos originais obtidos diretamente do banco como evidências autênticas, sem permitir que o LLM substitua dados numéricos calculados por SQL determinístico.
  9. A mensagem do usuário e a resposta validada são gravadas em `ChatMessage` com metadados de auditoria.

---

## 8. Critérios de Aceitação do MVP

1. **Upload e Auditoria de CSV**: Upload de arquivo CSV de 500 avaliações conclui registrando métricas exatas no `ImportJob` (`rows_total = rows_imported + rows_skipped + rows_rejected`), persistindo o job antes do processamento, capturando `source_system` e ignorando duplicatas por `(restaurant_id, source_system, external_id)` sem sobrescrever dados prévios.
2. **Validação de Análises**: Toda análise com status `COMPLETED` deve respeitar rigorosamente o schema estruturado Pydantic. A análise vigente é determinada pela configuração ativa centralizada (`provider_name`, `model_name`, `prompt_version`). Em caso de indisponibilidade de API ou falha de validação, o status da análise deve ser registrado como `FAILED` e a avaliação original deve permanecer íntegra para reprocessamento.
3. **Métricas Determinísticas**: O painel de analytics exibe indicadores calculados diretamente via SQL (`AVG(rating)`, `COUNT(*)`, agrupamentos por sentimento e data de publicação `reviewed_at`), idênticos aos resultados obtidos via console do PostgreSQL, preservando os valores numéricos sem adulteração pelo LLM.
4. **Busca Vetorial**: A recuperação semântica RAG é realizada via busca vetorial exata no `pgvector` sobre vetores de 384 dimensões gerados localmente pelo modelo único ativo `multilingual-e5-small` com `model_revision` registrado. A adoção de índices aproximados (HNSW) fica condicionada a benchmarks posteriores de latência e Recall@5.
5. **Segurança e Citações no Chat**: O chatbot não executa código SQL arbitrário. Todas as afirmações factuais com citações de feedbacks são conferidas pelo servidor (`CitationVerifierService`) contra o identificador canônico `review_id` das avaliações efetivamente retornadas pelas ferramentas pré-autorizadas, exibindo evidências textuais e identificadores (`source_system`, `external_id`) originais do banco de dados.
