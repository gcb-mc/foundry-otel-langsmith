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
    with tracer.start_as_current_span("agent.run") as span:
        span.set_attribute("agent.user_message_length", len(user_message))

        agents_client = create_client()
        code_interpreter = CodeInterpreterTool()

        with agents_client:
            # Create agent with code interpreter
            agent = agents_client.create_agent(
                model=os.environ["MODEL_DEPLOYMENT_NAME"],
                name="code-interpreter-agent",
                instructions=AGENT_INSTRUCTIONS,
                tools=code_interpreter.definitions,
            )
            span.set_attribute("agent.id", agent.id)

            try:
                # Create thread with message and run in one call
                thread_options = AgentThreadCreationOptions(
                    messages=[{"role": "user", "content": user_message}]
                )
                run = agents_client.create_thread_and_process_run(
                    agent_id=agent.id,
                    thread=thread_options,
                )
                span.set_attribute("agent.run.status", run.status)

                if run.status == "failed":
                    error_msg = f"Run failed: {run.last_error}"
                    span.set_attribute("agent.error", error_msg)
                    return error_msg

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
