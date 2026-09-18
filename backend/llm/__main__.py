import argparse
import sys

from llm import LLMError, TracedClient, default_client, load_prompt


def check() -> int:
    prompt = load_prompt("check")
    client = TracedClient(default_client(), purpose="check", prompt_version=prompt.version)
    print(f"asking {client.identity['model']}, the first call after a restart also loads the model")
    try:
        reply = client.chat([{"role": "user", "content": prompt.render()}])
    except LLMError as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1

    print(f"reply    {reply.content.strip()!r}")
    print(f"tokens   {reply.input_tokens} in, {reply.output_tokens} out")
    print(f"took     {reply.duration_ms / 1000:.1f} s")
    print(f"recorded as purpose 'check', prompt {prompt.version}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m llm")
    parser.add_argument("command", choices=["check"])
    parser.parse_args()
    return check()


if __name__ == "__main__":
    sys.exit(main())
