"""Azure AI Foundry agent with Code Interpreter tool."""

import os

from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    CodeInterpreterTool,
    ListSortOrder,
    MessageRole,
    AgentThreadCreationOptions,
)
from azure.identity import DefaultAzureCredential
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

# GenAI semantic convention attribute names
_GEN_AI_SYSTEM = "gen_ai.system"
_GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
_GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
_GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
_GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
_GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

AGENT_INSTRUCTIONS = """You are a helpful Python coding assistant.
You can write and execute Python code to answer questions, analyze data,
create visualizations, and solve problems. Show your work."""


def create_client() -> AgentsClient:
    """Create an authenticated AgentsClient."""
    return AgentsClient(
        endpoint=os.environ["PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )


def run_agent(user_message: str) -> str:
    """Run the code interpreter agent and return the final text response."""
    model = os.environ["MODEL_DEPLOYMENT_NAME"]

    with tracer.start_as_current_span("agent.run") as span:
        span.set_attribute("agent.user_message_length", len(user_message))
        span.set_attribute(_GEN_AI_SYSTEM, "az.ai.agents")
        span.set_attribute(_GEN_AI_OPERATION_NAME, "chat")
        span.set_attribute(_GEN_AI_REQUEST_MODEL, model)

        agents_client = create_client()
        code_interpreter = CodeInterpreterTool()

        with agents_client:
            # Create agent with code interpreter
            agent = agents_client.create_agent(
                model=model,
                name="code-interpreter-agent",
                instructions=AGENT_INSTRUCTIONS,
                tools=code_interpreter.definitions,
            )
            span.set_attribute("gen_ai.agent.id", agent.id)

            try:
                # Create thread with message and run in one call
                thread_options = AgentThreadCreationOptions(
                    messages=[{"role": "user", "content": user_message}]
                )
                run = agents_client.create_thread_and_process_run(
                    agent_id=agent.id,
                    thread=thread_options,
                )
                span.set_attribute("gen_ai.thread.run.status", run.status)

                # Extract token usage from run result
                if hasattr(run, "usage") and run.usage:
                    span.set_attribute(
                        _GEN_AI_USAGE_INPUT_TOKENS, run.usage.prompt_tokens
                    )
                    span.set_attribute(
                        _GEN_AI_USAGE_OUTPUT_TOKENS, run.usage.completion_tokens
                    )
                if hasattr(run, "model") and run.model:
                    span.set_attribute(_GEN_AI_RESPONSE_MODEL, run.model)

                if run.status == "failed":
                    error_msg = f"Run failed: {run.last_error}"
                    span.set_attribute("error.message", error_msg)
                    return error_msg

                # Trace run steps (tool calls) as child spans
                _trace_run_steps(agents_client, run.thread_id, run.id)

                # Extract the last agent message
                messages = agents_client.messages.list(
                    thread_id=run.thread_id, order=ListSortOrder.DESCENDING
                )
                for msg in messages:
                    if msg.role == MessageRole.AGENT and msg.text_messages:
                        response = msg.text_messages[-1].text.value
                        span.set_attribute("agent.response_length", len(response))
                        return response

                return "No response from agent."

            finally:
                agents_client.delete_agent(agent.id)


def _trace_run_steps(agents_client: AgentsClient, thread_id: str, run_id: str):
    """Fetch run steps and create child spans for tool calls."""
    try:
        run_steps = agents_client.run_steps.list(thread_id=thread_id, run_id=run_id)
        for step in run_steps:
            step_details = step.get("step_details", {})
            tool_calls = step_details.get("tool_calls", [])

            for call in tool_calls:
                tool_type = call.get("type", "unknown")
                span_name = f"tool.{tool_type}"

                with tracer.start_as_current_span(span_name) as tool_span:
                    tool_span.set_attribute("gen_ai.tool.name", tool_type)
                    tool_span.set_attribute("gen_ai.tool.call.id", call.get("id", ""))

                    if tool_type == "code_interpreter":
                        ci = call.get("code_interpreter", {})
                        code_input = ci.get("input", "")
                        if code_input:
                            tool_span.set_attribute(
                                "gen_ai.tool.input", code_input[:4096]
                            )
                        outputs = ci.get("outputs", [])
                        for i, output in enumerate(outputs):
                            if output.get("type") == "logs":
                                tool_span.set_attribute(
                                    f"gen_ai.tool.output.{i}",
                                    output.get("logs", "")[:4096],
                                )
    except Exception:
        pass  # Don't fail the agent run if step tracing fails
