"""Entry point — initializes tracing and runs the agent."""

import sys

from dotenv import load_dotenv

load_dotenv()

from src.telemetry import init_tracing
from src.agent import run_agent


def main():
    provider = init_tracing()

    # Use CLI argument as prompt, or default
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "Write a Python function that generates the first 20 Fibonacci numbers, "
        "then plot them as a line chart."
    )

    try:
        print(f"Prompt: {prompt}\n")
        response = run_agent(prompt)
        print(f"Response:\n{response}")
    finally:
        provider.shutdown()


if __name__ == "__main__":
    main()
