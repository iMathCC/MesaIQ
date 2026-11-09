# ADR-0001: Adoção do Padrão Monólito Modular (Modular Monolith)

**Data:** 2026-11-08  
**Status:** Aceito  
**Decisor:** Desenvolvedor do Projeto (Estudante de Ciência da Computação)  

---

## 1. Contexto

O **MesaIQ** é uma aplicação que combina ingestão de dados, processamento de inteligência artificial (LLM e embeddings), persistência relacional e vetorial, computação de métricas e interface web interativa. O desenvolvedor é o único responsável pela concepção, implementação e manutenção do sistema. O objetivo central da primeira versão (MVP) é validar a eficácia técnica da análise de feedbacks e fornecer inteligência acionável a gestores de restaurantes com agilidade e consistência.

A arquitetura precisa ser suficientemente robusta para manter limites claros entre módulos de negócio, permitindo testes independentes e futura expansão, mas sem adicionar complexidade operacional desnecessária.

---

## 2. Problema

Como estruturar o sistema de forma a garantir:
1. Alta manutenibilidade e baixo acoplamento entre regras de negócio, persistência, frameworks web e integrações de IA?
2. Facilidade de desenvolvimento e depuração local sem a sobrecarga de infraestrutura e orquestração de microsserviços?
3. Preparação para escalabilidade futura sem exigir refatorações destrutivas?

---

## 3. Decisão

Decidiu-se adotar o padrão arquitetural de **Monólito Modular** (*Modular Monolith*), organizado internamente conforme os preceitos da **Clean Architecture / Arquitetura Hexagonal** (separação estrita entre `domain`, `application`, `infrastructure` e `presentation`).

Todos os módulos residem em um único repositório e processo de execução em Python 3.12, porém com fronteiras estritas de dependência:
- A camada de **Domínio** não possui dependências externas ou de infraestrutura (depende unicamente da biblioteca padrão do Python, usando dataclasses nativas e enums, sem depender de Pydantic, SQLAlchemy ou frameworks externos).
- A camada de **Aplicação** orquestra casos de uso, define DTOs com Pydantic v2 e depende apenas de interfaces abstratas (*Protocols* em `typing`).
- As camadas de **Infraestrutura** e **Apresentação** implementam os adaptadores concretos.

---

## 4. Alternativas Consideradas

### Alternativa 1: Arquitetura de Microsserviços
- **Descrição:** Dividir a aplicação em múltiplos serviços autônomos (ex.: serviço de ingestão, serviço de IA/LLM, serviço analítico, backend da UI) comunicando-se via REST ou mensageria (Kafka/RabbitMQ).
- **Motivo da Rejeição:** Complexidade desproporcional para o estágio de MVP e para um desenvolvedor individual. Exigiria governança de deploys múltiplos, traces distribuídos, latência de rede entre serviços, consistência eventual e sobrecarga de infraestrutura.

### Alternativa 2: Monólito Tradicional sem Separação de Camadas (Script único / Django padrão)
- **Descrição:** Concentrar regras de negócio diretamente em rotas FastAPI ou em handlers de eventos do Gradio, com queries SQLAlchemy acopladas na apresentação.
- **Motivo da Rejeição:** Cria alto acoplamento (*spaghetti code*), impossibilita a criação de testes unitários rápidos e dificulta a substituição de provedores de IA ou de banco de dados.

---

## 5. Consequências

### Consequências Positivas
- **Simplicidade de Operação e Deploy:** Executa como um único serviço, facilitando o desenvolvimento local e reduzindo o consumo de memória e containers.
- **Fronteiras Claras:** Regras de negócio protegidas e testáveis sem a necessidade de levantar banco de dados ou mockar servidores HTTP remotos.
- **Transição Suave para Microsserviços (se necessário):** Caso algum módulo (como a geração de embeddings) exija escalabilidade independente no futuro, ele já estará isolado em seu próprio pacote e poderá ser extraído com mínimo atrito.

### Consequências Negativas
- **Disciplina de Engenharia Obrigatória:** Requer vigilância contínua para evitar que limites de camadas sejam violados (ex.: importar SQLAlchemy ou Gradio dentro de `domain` ou `application`). Essa restrição é mitigada pelas regras explícitas documentadas no `AGENTS.md` e verificação no linter.
