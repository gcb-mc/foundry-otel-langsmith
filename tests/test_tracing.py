"""Tests that tracing spans are emitted correctly."""

import os
from unittest.mock import patch, MagicMock

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory import InMemorySpanExporter
from opentelemetry import trace


def test_telemetry_init_sets_provider():
    """Verify init_tracing configures the global TracerProvider."""
    env = {
        "LANGSMITH_OTEL_ENDPOINT": "http://localhost:4318/v1/traces",
        "LANGSMITH_API_KEY": "fake-key",
        "OTEL_SERVICE_NAME": "test-service",
    }
    with patch.dict(os.environ, env):
        from src.telemetry import init_tracing

        provider = init_tracing()
        assert provider is not None
        current = trace.get_tracer_provider()
        assert current is provider
        provider.shutdown()


def test_agent_run_creates_span():
    """Verify run_agent emits an 'agent.run' span wrapping the agent call."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Mock the AIProjectClient and its agents interface
    mock_client = MagicMock()
    mock_agents = mock_client.__enter__.return_value.agents
    mock_agents = mock_client.agents

    mock_agent = MagicMock()
    mock_agent.id = "agent-123"
    mock_agents.create_agent.return_value = mock_agent

    mock_thread = MagicMock()
    mock_thread.id = "thread-456"
    mock_agents.threads.create.return_value = mock_thread

    mock_run = MagicMock()
    mock_run.status = "completed"
    mock_agents.runs.create_and_process.return_value = mock_run

    # Mock message response
    mock_msg = MagicMock()
    mock_msg.role = "assistant"
    mock_text = MagicMock()
    mock_text.text.value = "Here are the Fibonacci numbers..."
    mock_msg.text_messages = [mock_text]
    mock_msg.role = MagicMock()
    mock_msg.role.__eq__ = lambda self, other: True  # match MessageRole.AGENT
    mock_agents.messages.list.return_value = [mock_msg]

    env = {
        "PROJECT_ENDPOINT": "https://fake.services.ai.azure.com",
        "MODEL_DEPLOYMENT_NAME": "gpt-4o",
    }

    with patch.dict(os.environ, env):
        with patch("src.agent.create_client", return_value=mock_client):
            from src.agent import run_agent

            result = run_agent("test input")

    spans = exporter.get_finished_spans()
    agent_spans = [s for s in spans if s.name == "agent.run"]
    assert len(agent_spans) == 1
    assert agent_spans[0].attributes["agent.user_message_length"] == 10
    assert "Fibonacci" in result

    provider.shutdown()
