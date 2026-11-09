# ADR-0002: Adoção do Gradio Blocks como Camada de Apresentação

**Data:** 2026-11-08  
**Status:** Aceito  
**Decisor:** Desenvolvedor do Projeto (Estudante de Ciência da Computação)  

---

## 1. Contexto

O **MesaIQ** precisa fornecer uma interface interativa para que gestores de restaurantes possam:
1. Dialogar com o assistente inteligente através de uma experiência de chat amigável.
2. Visualizar gráficos e indicadores de métricas determinísticas (médias, notas, gráficos de barras e séries temporais).
3. Efetuar upload de arquivos CSV para ingestão de novas avaliações e visualização de jobs de importação.

O desenvolvimento da interface de usuário precisa ser rápido, centrado em Python, sem a necessidade de manter uma stack frontend separada (como React, Vue ou Next.js) que desviaria o foco do desenvolvedor das competências centrais do projeto (Engenharia de IA e Backend).

---

## 2. Problema

Qual tecnologia de apresentação adotar para construir a interface web do MVP que:
- Permita criar telas ricas (chat, dashboards analíticos e upload de arquivos) inteiramente em Python?
- Seja facilmente montada e servida sob a mesma infraestrutura web assíncrona do backend (FastAPI)?
- Possua governança sustentável, manutenção ativa e comunidade consolidada?

---

## 3. Decisão

Decidiu-se adotar o **Gradio Blocks**, integrado diretamente ao aplicativo principal **FastAPI** por meio do método oficial `gr.mount_gradio_app(app, blocks, path="/app")`.

Para manter o princípio da Clean Architecture, a camada de apresentação em Gradio **não conterá nenhuma regra de negócio**. Ela atuará estritamente como visualizadora e consumidora dos casos de uso expostos pela camada `application`.

---

## 4. Alternativas Consideradas

### Alternativa 1: Chainlit
- **Descrição:** Framework Python focado na construção rápida de interfaces conversacionais para LLMs.
- **Motivo da Rejeição:** Embora o Chainlit oferecesse uma boa experiência para protótipos conversacionais, o repositório oficial do projeto no GitHub (`Chainlit/chainlit`) foi formalmente arquivado em **15/10/2026**, tornando-se somente leitura (*read-only*), após passar por um período de manutenção comunitária com baixa atividade. Adotar um framework arquivado e descontinuado gera riscos técnicos inaceitáveis de segurança, obsolescência e quebra de dependências futuras.

### Alternativa 2: Streamlit
- **Descrição:** Biblioteca popular em Python para dashboards analíticos e protótipos de dados.
- **Motivo da Rejeição:** O modelo de execução do Streamlit reexecuta todo o script a cada interação do usuário (*full script re-run*), o que torna a gestão de sessões assíncronas de chat com websockets e montagem nativa dentro de uma aplicação FastAPI mais complexa e menos ergonômica em comparação ao Gradio.

### Alternativa 3: Frontend Separado em React / Next.js
- **Descrição:** Aplicação Single Page Application (SPA) consumindo uma API REST/Websocket do FastAPI.
- **Motivo da Rejeição:** Complexidade de desenvolvimento e manutenção excessiva para um desenvolvedor individual no MVP. Exigiria gerenciar dois ecossistemas (Node/NPM + Python), setup de bundlers, CORS, deploy de dois artefatos distintos e esforço considerável de design UI.

---

## 5. Consequências

### Consequências Positivas
- **Ecossistema 100% Python:** Permite ao desenvolvedor focar em código backend e de IA sem alternar contextos de linguagem.
- **Componentes Nativos Prontos:** O Gradio fornece nativamente componentes de `Chatbot`, `Plot` (suporte a Matplotlib/Plotly), `DataFrame` e `File` prontos para uso.
- **Integração Perfeita com FastAPI:** Montagem direta sob `/app`, compartilhando o mesmo processo, porta e ciclo de vida do servidor ASGI (`uvicorn`).
- **Comunidade Forte e Ativa:** Mantido e apoiado pela Hugging Face, com atualizações contínuas e documentação robusta.

### Consequências Negativas
- **Personalização Visual Limitada:** Menor flexibilidade de customização de estilos CSS refinados se comparado a uma interface construída do zero em Tailwind/React (compensado pela velocidade de entrega no MVP).
