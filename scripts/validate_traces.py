"""Local trace validation — runs the agent and prints the full span tree.

Usage:
    python scripts/validate_traces.py
    python scripts/validate_traces.py "Your custom prompt here"

Requires: .env file with PROJECT_ENDPOINT, MODEL_DEPLOYMENT_NAME configured.
Does NOT require LangSmith — uses InMemorySpanExporter to inspect spans locally.
"""

import os
import sys
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.resources import Resource
from azure.core.settings import settings
from azure.ai.agents.telemetry import AIAgentsInstrumentor

# --- Setup tracing with in-memory exporter ---
settings.tracing_implementation = "opentelemetry"

resource = Resource.create({"service.name": "validate-traces"})
provider = TracerProvider(resource=resource)
exporter = InMemorySpanExporter()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)

capture_content = os.getenv(
    "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true"
).lower() == "true"
AIAgentsInstrumentor().instrument(enable_content_recording=capture_content)

# --- Run the agent ---
from src.agent import run_agent

prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Print the numbers 1 to 5"

print(f"Running agent with prompt: {prompt!r}\n")
result = run_agent(prompt)
print(f"\nAgent response: {result[:200]}{'...' if len(result) > 200 else ''}\n")

# --- Analyze spans ---
provider.force_flush()
spans = exporter.get_finished_spans()

print(f"{'='*70}")
print(f"TRACE VALIDATION — {len(spans)} spans captured")
print(f"{'='*70}\n")

# Build parent-child tree
children = defaultdict(list)
span_map = {}
for s in spans:
    span_map[s.context.span_id] = s
    parent_id = s.parent.span_id if s.parent else None
    children[parent_id].append(s)

# Find roots
roots = children[None]


def print_span_tree(span, indent=0):
    """Recursively print the span tree."""
    prefix = "  " * indent + ("└─ " if indent > 0 else "")
    duration_ms = (span.end_time - span.start_time) / 1_000_000
    print(f"{prefix}{span.name} ({duration_ms:.1f}ms)")

    # Print key attributes
    if span.attributes:
        for key, value in sorted(span.attributes.items()):
            if key.startswith("gen_ai.") or key.startswith("agent."):
                val_str = str(value)
                if len(val_str) > 80:
                    val_str = val_str[:77] + "..."
                print(f"{'  ' * (indent + 1)}   {key}: {val_str}")

    # Print children
    for child in children.get(span.context.span_id, []):
        print_span_tree(child, indent + 1)


for root in roots:
    print_span_tree(root)
    print()

# --- Validate GenAI semantic conventions ---
print(f"\n{'='*70}")
print("GENAI SEMCONV VALIDATION")
print(f"{'='*70}\n")

REQUIRED_ATTRS = [
    "gen_ai.system",
    "gen_ai.operation.name",
    "gen_ai.request.model",
]

DESIRED_ATTRS = [
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.response.model",
    "gen_ai.agent.id",
    "gen_ai.thread.run.status",
]

# Check the agent.run span
agent_run_spans = [s for s in spans if s.name == "agent.run"]
if not agent_run_spans:
    print("FAIL: No 'agent.run' span found!")
    sys.exit(1)

agent_span = agent_run_spans[0]
all_passed = True

for attr in REQUIRED_ATTRS:
    value = agent_span.attributes.get(attr)
    status = "PASS" if value else "FAIL"
    if not value:
        all_passed = False
    print(f"  [{status}] {attr} = {value}")

for attr in DESIRED_ATTRS:
    value = agent_span.attributes.get(attr)
    status = "PASS" if value else "WARN"
    print(f"  [{status}] {attr} = {value}")

# Check for tool spans
tool_spans = [s for s in spans if s.name.startswith("tool.")]
print(f"\n  Tool spans found: {len(tool_spans)}")
for ts in tool_spans:
    print(f"    - {ts.name}: {dict(ts.attributes)}")

# Check hierarchy
print(f"\n  Span hierarchy depth: {len(spans)} total spans")
sdk_spans = [s for s in spans if s.name != "agent.run" and not s.name.startswith("tool.")]
print(f"  SDK auto-instrumented spans: {len(sdk_spans)}")
for s in sdk_spans:
    print(f"    - {s.name}")

print(f"\n{'='*70}")
if all_passed:
    print("ALL REQUIRED CHECKS PASSED")
else:
    print("SOME CHECKS FAILED — review output above")
print(f"{'='*70}")

provider.shutdown()
