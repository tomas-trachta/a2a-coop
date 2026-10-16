import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .protocol import TOOL_NAMES

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


def claude_add_command(db: Path, agent: str) -> list[str]:
    return ["claude", "mcp", "add", "--scope", "user", SERVER_NAME, "--", *server_command(db, agent)]


def claude_instructions(db: Path, agent: str) -> str:
    return f"Claude Code - run once:\n  {shell_join(claude_add_command(db, agent))}"


def codex_block(db: Path, agent: str) -> list[str]:
    executable, *arguments = server_command(db, agent)
    toml_arguments = ", ".join(toml_literal(argument) for argument in arguments)
    approvals = [
        line
        for tool in TOOL_NAMES
        for line in ("", f"[mcp_servers.{SERVER_NAME}.tools.{tool}]", 'approval_mode = "approve"')
    ]

    return [
        f"[mcp_servers.{SERVER_NAME}]",
        f"command = {toml_literal(executable)}",
        f"args = [{toml_arguments}]",
        f"tool_timeout_sec = {TOOL_TIMEOUT_SECONDS}",
        *approvals,
    ]


def codex_instructions(db: Path, agent: str) -> str:
    block = codex_block(db, agent)[:4]

    return "\n".join(["Codex - add to ~/.codex/config.toml:", *(f"  {line}" for line in block)])


def codex_config_path() -> Path:
    home = os.environ.get("CODEX_HOME")

    return (Path(home).expanduser() if home else Path.home() / ".codex") / "config.toml"


def configure_claude(db: Path, agent: str) -> str:
    if not shutil.which("claude"):
        return "Claude Code: not installed, skipped."

    if run_quietly(["claude", "mcp", "get", SERVER_NAME]) == 0:
        return f"Claude Code: already configured (`claude mcp get {SERVER_NAME}` to inspect)."

    if run_quietly(claude_add_command(db, agent)) != 0:
        return f"Claude Code: `claude mcp add` failed. Run it yourself:\n  {shell_join(claude_add_command(db, agent))}"

    return f"Claude Code: added the {SERVER_NAME} MCP server (user scope) as agent {agent!r}."


def configure_codex(db: Path, agent: str, config: Path) -> str:
    if not shutil.which("codex"):
        return "Codex: not installed, skipped."

    existing = config.read_text(encoding="utf-8") if config.exists() else ""

    if f"[mcp_servers.{SERVER_NAME}]" in existing:
        return f"Codex: already configured in {config}."

    separator = "" if not existing or existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(existing + separator + "\n".join(codex_block(db, agent)) + "\n", encoding="utf-8")

    return f"Codex: added the {SERVER_NAME} MCP server to {config} as agent {agent!r}."


def run_quietly(command: list[str]) -> int:
    try:
        return subprocess.run(command, capture_output=True, timeout=60).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


def configure_clients(db: Path, claude_name: str, codex_name: str) -> list[str]:
    return [configure_claude(db, claude_name), configure_codex(db, codex_name, codex_config_path())]


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
