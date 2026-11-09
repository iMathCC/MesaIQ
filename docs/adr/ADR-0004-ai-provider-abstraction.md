# ADR-0004: Integração de Provedores de IA Desacoplada e Agnóstica

**Data:** 2026-11-08  
**Status:** Aceito  
**Decisor:** Desenvolvedor do Projeto (Estudante de Ciência da Computação)  

---

## 1. Contexto

O **MesaIQ** depende de dois pilares fundamentais de Inteligência Artificial:
1. **Modelos de Linguagem Grandes (LLMs):** Para interpretação semântica de textos não estruturados, classificação de sentimentos, resumos estruturados e orquestração conversacional com Tool Calling.
2. **Modelos de Embeddings Vetoriais:** Para gerar vetores de significado denso a partir dos comentários e das consultas dos usuários.

O mercado de IA generativa evolui em ritmo acelerado, com constante surgimento de novos modelos, alterações de custos e novos SDKs. Acoplar a lógica de negócio diretamente ao SDK de um provedor específico geraria dívida técnica e fragilidade arquitetural.

---

## 2. Problema

Como integrar capacidades de LLM (neste MVP, Google Gemini via Google Gen AI SDK) e embeddings (modelo local `multilingual-e5-small`) de forma que:
- O domínio e os casos de uso da aplicação não dependam diretamente de bibliotecas proprietárias ou SDKs de terceiros?
- A camada de aplicação defina contratos e DTOs fortemente tipados em vez de estruturas fracas (`dict` genéricos)?
- A troca do provedor de LLM (por exemplo, migrar de Gemini para Claude, OpenAI ou um modelo open-source local) possa ser feita sem alterar as regras de negócio?
- A inferência local de embeddings não bloqueie o loop de eventos assíncrono da aplicação web?

---

## 3. Decisão

Decidiu-se adotar o padrão **Portas e Adaptadores (Hexagonal Architecture)** para isolar totalmente as integrações de Inteligência Artificial:

1. **Definição de Interfaces Abstratas (Portas) na Camada de Aplicação (`src/application/ports/`):**
   - Utilização do recurso `Protocol` do módulo nativo `typing` do Python para definir as interfaces `LLMProvider` e `EmbeddingProvider`.
   - Utilização de modelos **Pydantic v2** para todos os esquemas de entrada e saída estruturados: `AnalysisResult`, `AspectResult`, `ChatMessageDTO`, schemas específicos de argumentos de ferramentas (`GetReviewMetricsArgs`, `GetTopIssuesArgs`, `SearchReviewsArgs`, e `GetReviewDetailsArgs` com validação condicional estrita), `QuantitativeMetricDTO`, `ReviewEvidenceItem`, `ToolResult` e uma união discriminada para `LLMResponse` (`ToolCallRequest` vs `FinalChatResponse`), prevenindo estados inválidos. A camada `domain/` permanece pura e independente de Pydantic.
   - Utilização de `Enum` estritos para sentimentos (`positive`, `neutral`, `negative`) e categorias de aspectos (`food_quality`, `delivery`, `packaging`, `customer_service`, `price_value`, `other`).
   - Adoção do `review_id` canônico interno para identificação de evidências nas ferramentas, com validação referencial no servidor (`CitationVerifierService`) e exibição de `source_system` e `external_id` no frontend.
   - Esgrima de concorrência com `attempt_id` (UUID) na entidade `ReviewAnalysis`, rejeitando retornos tardios de requisições de IA cujas reservas expiraram por timeout (`ANALYSIS_PROCESSING_TIMEOUT_SECONDS`).
   - Distinção conceitual entre validação referencial no servidor (`CitationVerifierService`) e fundamentação factual avaliada em testes de alucinação.
   - Centralização da configuração ativa (`provider_name`, `model_name`, `prompt_version`) em `pydantic-settings`, garantindo que a análise vigente seja sempre a da configuração ativa do sistema, viabilizando benchmarks comparativos futuros.
2. **Implementação de Adaptadores Concretos na Camada de Infraestrutura (`src/infrastructure/ai/`):**
   - `GeminiLLMAdapter`: Encapsula o Google Gen AI SDK, valida as saídas com Structured Outputs via schemas Pydantic e traduz tool calls entre o formato interno e a API do Gemini.
   - `E5LocalEmbeddingAdapter`: Carrega localmente o modelo `intfloat/multilingual-e5-small` e aplica a convenção dos prefixos `passage:` e `query:`. Como a inferência local é síncrona e consome CPU/GPU, sua execução a partir de fluxos assíncronos é realizada via thread pool (`asyncio.to_thread` / `run_in_threadpool`).

Nenhum arquivo em `domain/` ou `application/` importa `google.genai`, `sentence_transformers`, `torch` ou bibliotecas similares.

---

## 4. Alternativas Consideradas

### Alternativa 1: Acoplamento Direto do SDK do Gemini nos Casos de Uso
- **Descrição:** Instanciar o cliente da API do Gemini diretamente dentro do caso de uso `AnalyzeReviewUseCase`.
- **Motivo da Rejeição:** Viola o princípio de inversão de dependência (DIP do SOLID). Tornaria os testes unitários lentos e dependentes de rede ou monkeypatching frágil, além de impedir a substituição de provedores de IA sem reescrever o fluxo de negócio.

### Alternativa 2: Uso de Frameworks Pesados de Orquestração (ex.: LangChain, LlamaIndex, CrewAI)
- **Descrição:** Adotar LangChain ou LlamaIndex para gerenciar toda a esteira de RAG e agentes.
- **Motivo da Rejeição:** 
  - **Sobrecarga de Abstrações (*Leaky Abstractions*):** Esses frameworks frequentemente introduzem complexidade excessiva, atualizações frequentes com quebra de retrocompatibilidade (*breaking changes*) e dificuldade de depuração fina.
  - **Falta de Clareza Didática e Técnica:** Em entrevistas técnicas, a implementação direta de Tool Calling e RAG utilizando contratos simples demonstra muito mais profundidade conceitual e domínio de engenharia do que o uso de bibliotecas que "escondem a mágica".

### Alternativa 3: Utilização de API Externa Paga para Embeddings (ex.: OpenAI text-embedding-3 ou Gemini Embeddings)
- **Descrição:** Gerar embeddings por meio de requisições HTTP para endpoints externos.
- **Motivo da Rejeição:** Custo financeiro contínuo e dependência de rede para uma operação que pode ser executada com alta eficiência e de forma determinística localmente com o modelo `intfloat/multilingual-e5-small`.

---

## 5. Consequências

### Consequências Positivas
- **Independência de Fornecedor (*Vendor Lock-in Free*):** Qualquer provedor que atenda ao contrato Pydantic pode ser plugado em minutos.
- **Testabilidade Superior:** Casos de uso podem ser testados com mocks determinísticos e rápidos sem gastar créditos de API ou necessitar de chaves de ambiente nos testes unitários.
- **Tipagem Forte e Previsibilidade:** O uso de Pydantic e Enums elimina erros em tempo de execução causados por chaves ausentes em dicionários genéricos.
- **Custo Zero e Prevenção de Bloqueio de Thread:** A geração de embeddings locais é gratuita e, executada em thread pool, mantém a responsividade da aplicação web.

### Consequências Negativas
- **Código Inicial de Infraestrutura:** Exige a escrita manual das classes adaptadoras e do mapeamento de schemas Pydantic (um esforço pontual amplamente compensado pela clareza e controle arquitetural).
