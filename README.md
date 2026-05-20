# Foundry + OpenTelemetry + LangSmith

Trace Azure AI Foundry agent calls to [LangSmith](https://smith.langchain.com/) using OpenTelemetry — no LangChain SDK required.

This project demonstrates how to build a **code-interpreter AI agent** with Azure AI Foundry and route all telemetry through OpenTelemetry's OTLP/HTTP exporter directly to LangSmith for observability.

![Architecture](docs/architecture.png)

## Architecture

```
AgentsClient (azure-ai-agents)
        │
        ▼
Azure AI Agents SDK ──── AIAgentsInstrumentor (auto-spans)
        │                         │
        ▼                         ▼
CodeInterpreterTool     TracerProvider + BatchSpanProcessor
                                  │
                                  ▼
                        OTLP HTTP Exporter → LangSmith
```

**Key insight:** LangSmith supports native OTLP ingestion. You don't need the `langchain` or `langsmith` Python SDK — just point an OTLP exporter at their endpoint.

## Prerequisites

- **Python 3.11+**
- **Azure subscription** with an [Azure AI Foundry](https://ai.azure.com/) project
- **Model deployment** (e.g., `gpt-4o`) in your Foundry project
- **LangSmith account** — [sign up free](https://smith.langchain.com/)
- **Azure CLI** authenticated (`az login`)

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/gabrielab-ms/foundry-otel-langsmith.git
cd foundry-otel-langsmith
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Where to find it |
|----------|-----------------|
| `PROJECT_ENDPOINT` | Azure AI Foundry portal → your project → Overview → Endpoint |
| `MODEL_DEPLOYMENT_NAME` | Azure AI Foundry → Deployments (e.g., `gpt-4o`) |
| `LANGSMITH_API_KEY` | [smith.langchain.com](https://smith.langchain.com/) → Settings → API Keys |
| `LANGSMITH_OTEL_ENDPOINT` | `https://api.smith.langchain.com/otel/v1/traces` |
| `OTEL_SERVICE_NAME` | Any name for your service (e.g., `foundry-otel-langsmith`) |

### 5. Authenticate to Azure

```bash
az login
```

The project uses `DefaultAzureCredential`, which picks up your Azure CLI login, managed identity, or environment variables automatically.

### 6. Run the agent

```bash
# Default prompt (Fibonacci + plot)
python -m src.main

# Custom prompt
python -m src.main "Calculate the first 50 prime numbers and show them in a table"
```

### 7. View traces in LangSmith

Go to [smith.langchain.com](https://smith.langchain.com/) → Projects → look for your `OTEL_SERVICE_NAME`. You'll see:
- A root `agent.run` span
- Child spans for `create_agent`, `create_thread_and_process_run`, `messages.list`
- Timing, status, and attributes for each operation

## Interactive Notebook

For a step-by-step walkthrough that lets you verify each component individually:

```bash
jupyter notebook reset-safe-notebook-langfoundry.ipynb
```

The notebook covers:
1. Installing dependencies
2. Authenticating to Azure (interactive prompt for credentials — nothing hardcoded)
3. Testing the OTLP connection to LangSmith
4. Running the agent end-to-end with full tracing
5. Verifying spans arrive in LangSmith

> **Tip:** The notebook is "reset-safe" — you can re-run any cell without restarting the kernel.

## Project Structure

```
foundry-otel-langsmith/
├── src/
│   ├── __init__.py
│   ├── main.py          # Entry point — loads env, inits tracing, runs agent
│   ├── telemetry.py     # OTEL setup: TracerProvider, OTLP exporter, AIAgentsInstrumentor
│   ├── agent.py         # Agent logic: create, run, extract response, cleanup
│   └── tools/
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   └── test_tracing.py  # Unit tests with InMemorySpanExporter (no network)
├── reset-safe-notebook-langfoundry.ipynb  # Interactive step-by-step notebook
├── notebook.ipynb       # Original exploration notebook
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## How It Works

### Telemetry (`src/telemetry.py`)

1. Sets `settings.tracing_implementation = "opentelemetry"` to enable the azure-core OTEL bridge
2. Creates a `TracerProvider` with service name and environment resource attributes
3. Configures an `OTLPSpanExporter` pointed at LangSmith's endpoint with the API key header
4. Calls `AIAgentsInstrumentor().instrument()` to auto-instrument all Azure AI Agents SDK calls

### Agent (`src/agent.py`)

1. Creates an `AgentsClient` with `DefaultAzureCredential`
2. Creates a code-interpreter agent with a custom system prompt
3. Sends the user's message and processes the run in one call
4. Extracts the agent's text response
5. Always cleans up (deletes the agent) in a `finally` block

### Custom Spans

The `run_agent` function wraps everything in a custom `agent.run` span with attributes like message length, agent ID, run status, and response length — giving you a high-level view in LangSmith.

## Running Tests

```bash
# All tests
pytest tests/ -v

# Single test
pytest tests/test_tracing.py::test_agent_run_creates_span -v
```

Tests use `InMemorySpanExporter` and mocked clients — no Azure or LangSmith credentials needed.

## Configuration Options

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `false` | Set to `true` to include prompt/response content in traces (⚠️ PII risk) |
| `DEPLOYMENT_ENVIRONMENT` | `development` | Environment tag in traces |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `DefaultAzureCredential` error | Run `az login` or check your Azure identity config |
| No traces in LangSmith | Verify `LANGSMITH_API_KEY` and `LANGSMITH_OTEL_ENDPOINT` are correct |
| `ModuleNotFoundError` | Activate your venv and run `pip install -r requirements.txt` |
| Agent run fails | Check that `MODEL_DEPLOYMENT_NAME` matches an active deployment in your project |

## License

MIT
# test
