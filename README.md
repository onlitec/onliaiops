# 🤖 ONLI-AIOPS — Autonomic Operations & SRE Infrastructure AI Agent

O **ONLI-AIOPS** é um agente autônomo e inteligente para operações de infraestrutura (AIOps / SRE), projetado para triagem, diagnóstico automatizado e execução segura de runbooks de remediação em ambientes multi-cloud e on-premises (Proxmox VE, Proxmox Backup Server, MikroTik, Linux Hosts, HestiaCP e Docker).

---

## 🌟 Principais Funcionalidades

1. **🛡️ Smart Alert Triage & Offline Suppression:**
   * Detecção determinística de servidores inacessíveis/offline, **poupando 100% dos tokens de IA**.
   * Silenciamento automático de alertas repetitivos (limite configurável de 5 notificações) até o restabelecimento (*Auto-Recovery*).
   * Deduplicação inteligente de alertas dentro de janelas temporais de 15 minutos.

2. **🧠 Multi-Provider AI Engine:**
   * Suporte nativo e otimizado para **Anthropic Claude** (`claude-3-5-haiku-20241022`, `claude-sonnet-4-5`), **Google Gemini** (`gemini-1.5-flash`, `gemini-2.0-flash`), **OpenAI** (`gpt-4o-mini`) e modelos locais via **Ollama**.
   * Formatação limpa de respostas em **Markdown profissional com suporte a marked.js**.

3. **🔧 Tool Gateway Seguro & Auditado:**
   * Execução restrita e não-destrutiva de comandos diagnósticos: `consultar_servidor`, `consultar_cpu`, `consultar_disco`, `consultar_memoria`, `consultar_processos`, `testar_ping`, `testar_porta`, `reiniciar_servico`, `consultar_proxmox`, `consultar_mikrotik`.

4. **⚡ Central de Incidentes Interativa & Fila de Aprovação (HITL):**
   * Interface Web moderna e responsiva na porta `8088`.
   * Drawer de detalhes de incidentes com evidências brutas, hipóteses geradas e botão de re-diagnóstico em tempo real (*Diagnosticar Novamente Agora*).
   * Modelo Human-in-the-Loop (HITL) para ações com nível de risco Médio, Alto ou Crítico.

5. **🔗 Integração com Stack de Observabilidade:**
   * Receptor nativo de Webhooks do **Prometheus Alertmanager** (`/api/v1/webhook/alertmanager`).
   * WebSocket bidirecional para atualizações em tempo real no dashboard.

---

## 🏗️ Estrutura do Repositório

```
onliaiops/
├── app.py                  # Servidor Principal FastAPI & WebSocket
├── requirements.txt        # Dependências Python (FastAPI, Uvicorn, etc.)
├── Dockerfile              # Containerização Docker
├── .gitignore              # Proteção de credenciais e dados em runtime
├── engine/
│   ├── ai_client.py        # Cliente Universal de Provedores de IA
│   ├── prompt_manager.py   # Gerenciador de System Prompts (22 Princípios SRE)
│   ├── risk_evaluator.py   # Avaliador de Risco e Matriz de Autorização
│   ├── loop_breaker.py     # Prevenção contra Loops de Remediação
│   ├── runbooks.py         # Catálogo de Runbooks Aprovados
│   └── smart_triage.py     # Motor de Triagem Inteligente e Supressão de Alertas
├── gateway/
│   └── tool_gateway.py     # Gateway de Ferramentas de Infraestrutura
├── static/
│   ├── index.html          # Painel Web do ONLI-AIOPS
│   ├── style.css           # Estilos e Temas Customizados
│   ├── app.js              # Lógica Frontend e Conexão WebSocket
│   └── marked.min.js       # Renderizador de Markdown
└── data/
    └── config.example.json # Modelo de Configuração
```

---

## 🚀 Como Executar Localmente

1. **Criar Ambiente Virtual:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configurar Credenciais:**
   ```bash
   cp data/config.example.json data/config.json
   # Edite data/config.json e informe sua API Key
   ```

3. **Iniciar a Aplicação:**
   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8088 --reload
   ```

4. **Acessar a Interface Web:**
   * Navegador: `http://localhost:8088`

---

## 📄 Licença
Propriedade exclusiva de **ONLITEC Tecnologia**. Todos os direitos reservados.
