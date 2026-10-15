import shlex
import subprocess
import sys
from pathlib import Path

SERVER_NAME = "a2a-coop"
TOOL_TIMEOUT_SECONDS = 330


def server_command(db: Path, agent: str) -> list[str]:
    return [sys.executable, "-m", "a2a_coop", "--db", str(db.resolve()), "serve", "--agent", agent]


def shell_join(parts: list[str]) -> str:
    if sys.platform == "win32":
        return subprocess.list2cmdline(parts)

    return shlex.join(parts)


def toml_literal(value: str) -> str:
    return f"'{value}'"


def claude_instructions(db: Path, agent: str) -> str:
    command = ["claude", "mcp", "add", "--scope", "user", SERVER_NAME, "--", *server_command(db, agent)]

    return f"Claude Code - run once:\n  {shell_join(command)}"


def codex_instructions(db: Path, agent: str) -> str:
    executable, *arguments = server_command(db, agent)
    toml_arguments = ", ".join(toml_literal(argument) for argument in arguments)

    return "\n".join([
        "Codex - add to ~/.codex/config.toml:",
        f"  [mcp_servers.{SERVER_NAME}]",
        f"  command = {toml_literal(executable)}",
        f"  args = [{toml_arguments}]",
        f"  tool_timeout_sec = {TOOL_TIMEOUT_SECONDS}",
    ])


def kickoff_instructions() -> str:
    return "\n".join([
        "Then start each agent and tell it:",
        '  "Join the a2a-coop team: call get_briefing and follow the coop protocol.',
        '   Whenever you are idle keep calling wait_for_messages until I tell you to stop."',
        "(In Claude Code you can also run the /mcp__a2a-coop__join prompt.)",
    ])


def setup_text(db: Path, claude_name: str, codex_name: str) -> str:
    return "\n\n".join([
        claude_instructions(db, claude_name),
        codex_instructions(db, codex_name),
        kickoff_instructions(),
    ])
