"""OpenTelemetry tracing setup — exports spans to LangSmith via OTLP/HTTP.

Uses the Azure AI Agents SDK's built-in instrumentor (AIAgentsInstrumentor)
which auto-generates spans for agent creation, thread/message ops, and runs.
Those spans are then exported to LangSmith's OTLP endpoint.
"""

import os

from azure.core.settings import settings
from azure.ai.agents.telemetry import AIAgentsInstrumentor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter


def init_tracing() -> TracerProvider:
    """Initialize OpenTelemetry with LangSmith export and instrument the Agents SDK."""
    # Enable OpenTelemetry bridge for azure-core
    settings.tracing_implementation = "opentelemetry"

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "foundry-otel-langsmith"),
            "deployment.environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "development"),
        }
    )

    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(
        endpoint=os.environ["LANGSMITH_OTEL_ENDPOINT"],
        headers={"x-api-key": os.environ["LANGSMITH_API_KEY"]},
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    # Instrument the Azure AI Agents SDK — auto-creates spans for all agent ops.
    # enable_content_recording includes prompt/response content in spans when the
    # OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT env var is also "true".
    capture_content = os.getenv(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false"
    ).lower() == "true"
    AIAgentsInstrumentor().instrument(enable_content_recording=capture_content)

    return provider
