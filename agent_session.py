#!/usr/bin/env python3
import os
import sys

import anthropic

AGENT_ID = os.environ.get("ANTHROPIC_AGENT_ID", "agent_012fS2cHxR7UReXEEuLu4RL1")
ENVIRONMENT_ID = os.environ.get("ANTHROPIC_ENVIRONMENT_ID", "env_01GKVp55MZe62UJDdrMpkUia")


def main() -> int:
    message = " ".join(sys.argv[1:]) or "Hello"

    client = anthropic.Anthropic()

    try:
        session = client.beta.sessions.create(
            agent={"type": "agent", "id": AGENT_ID},
            environment_id=ENVIRONMENT_ID,
        )
    except anthropic.APIError as e:
        print(f"Failed to create session: {e}", file=sys.stderr)
        return 1

    print(f"Session: {session.id}")
    print(f"Trace: https://platform.claude.com/workspaces/default/sessions/{session.id}")

    try:
        with client.beta.sessions.events.stream(session_id=session.id) as stream:
            client.beta.sessions.events.send(
                session_id=session.id,
                events=[
                    {
                        "type": "user.message",
                        "content": [{"type": "text", "text": message}],
                    }
                ],
            )

            for event in stream:
                if event.type == "agent.message":
                    for block in event.content:
                        if block.type == "text":
                            print(block.text, end="", flush=True)
                elif event.type == "session.status_idle":
                    print("\n--- Agent idle ---")
                    break
                elif event.type == "session.status_terminated":
                    print("\n--- Session terminated ---")
                    break
                elif event.type == "session.error":
                    print(f"\nSession error: {event.error.message}", file=sys.stderr)
                    return 1
    except anthropic.APIError as e:
        print(f"API error while streaming: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
