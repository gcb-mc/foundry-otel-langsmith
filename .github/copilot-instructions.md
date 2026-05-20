# Copilot Instructions

## Project Overview

This project builds a code-interpreter AI agent using Azure AI Foundry, with tracing routed through OpenTelemetry to LangSmith for observability.

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

- **Agent layer**: `azure-ai-agents` `AgentsClient` directly (not via `AIProjectClient.agents` which is for agent registry/versioning in v2.x). The agent uses `CodeInterpreterTool` for Python execution.
- **Telemetry layer**: `AIAgentsInstrumentor` from `azure.ai.agents.telemetry` auto-instruments all agent SDK calls (create_agent, create_thread_and_process_run, messages.list). The `azure-core-tracing-opentelemetry` bridge connects azure-core HTTP calls to OTEL. Spans export via OTLP/HTTP to LangSmith.
- **No LangChain dependency**: Uses LangSmith's native OTLP ingestion — no `langchain` or `langsmith` Python SDK needed.

## Tech Stack

- Python 3.11+
- `azure-ai-projects` + `azure-ai-agents` — Foundry agent SDK
- `azure-core-tracing-opentelemetry` — bridges azure-core to OpenTelemetry
- `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http` — tracing pipeline
- `python-dotenv` — environment config

## Commands

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Run the agent (default prompt or custom)
python -m src.main
python -m src.main "Calculate the first 50 primes"

# Run a single test
pytest tests/test_tracing.py::test_agent_run_creates_span -v

# Run all tests
pytest tests/ -v
```

## Environment Variables

Required in `.env` (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `PROJECT_ENDPOINT` | Azure AI Foundry project endpoint URL |
| `MODEL_DEPLOYMENT_NAME` | Model deployment name (e.g. `gpt-4o`) |
| `LANGSMITH_OTEL_ENDPOINT` | LangSmith OTLP ingestion URL |
| `LANGSMITH_API_KEY` | Auth for LangSmith |
| `OTEL_SERVICE_NAME` | Service name tag in traces |

## Key Conventions

- **Tracing in `src/telemetry.py`** — single module that sets `settings.tracing_implementation = "opentelemetry"`, configures TracerProvider, OTLP exporter, and calls `AIAgentsInstrumentor().instrument()`. Must be called before creating any `AIProjectClient`.
- **Agent in `src/agent.py`** — creates and tears down the agent per invocation. Always deletes the agent in a `finally` block to avoid leaked resources.
- **Custom spans** — wrap high-level operations with `tracer.start_as_current_span("agent.run")`. The SDK instrumentor handles sub-spans for individual API calls.
- **Testing** — use `InMemorySpanExporter` and mock `AIProjectClient` to test span emission without network calls.
- **PII** — `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` defaults to `false`. Only set `true` in dev.
