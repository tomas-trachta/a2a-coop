import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import connect, protocol
from .errors import CoopError
from .models import Agent

CommandBuilder = Callable[[str, list[str], str], list[str]]


@dataclass(frozen=True)
class Provider:
    name: str
    label: str
    executable: str
    build: CommandBuilder

    def installed_path(self) -> Optional[str]:
        return shutil.which(self.executable)


def claude_command(executable: str, server: list[str], prompt: str) -> list[str]:
    command, *arguments = server
    mcp_config = {"mcpServers": {connect.SERVER_NAME: {"command": command, "args": arguments}}}

    return [
        executable,
        f"--mcp-config={json.dumps(mcp_config)}",
        f"--allowedTools=mcp__{connect.SERVER_NAME}",
        prompt,
    ]


def codex_command(executable: str, server: list[str], prompt: str) -> list[str]:
    command, *arguments = server
    prefix = f"mcp_servers.{connect.SERVER_NAME}"
    overrides = [
        f"{prefix}.command={json.dumps(command)}",
        f"{prefix}.args={json.dumps(arguments)}",
        f"{prefix}.tool_timeout_sec={connect.TOOL_TIMEOUT_SECONDS}",
        *(f'{prefix}.tools.{tool}.approval_mode="approve"' for tool in protocol.TOOL_NAMES),
    ]

    return [executable, *(part for override in overrides for part in ("-c", override)), prompt]


PROVIDERS = {
    provider.name: provider
    for provider in (
        Provider("claude", "Claude Code", "claude", claude_command),
        Provider("codex", "Codex", "codex", codex_command),
    )
}


def installed_providers() -> list[Provider]:
    return [provider for provider in PROVIDERS.values() if provider.installed_path()]


def get_provider(name: str) -> Provider:
    provider = PROVIDERS.get(name)

    if provider is None:
        raise CoopError(f"Unknown provider {name!r}. Choose one of: {', '.join(PROVIDERS)}.")

    return provider


def provider_for(agent: Agent) -> Provider:
    if agent.provider:
        return get_provider(agent.provider)

    for provider in PROVIDERS.values():
        if agent.name.startswith(provider.name):
            return provider

    raise CoopError(
        f"Agent {agent.name!r} has no provider. Set one with `a2a-coop agent set {agent.name} --provider claude`."
    )


def agent_command(db: Path, agent: Agent) -> list[str]:
    provider = provider_for(agent)
    executable = provider.installed_path()

    if executable is None:
        raise CoopError(f"{provider.label} (`{provider.executable}`) is not installed on this machine.")

    return provider.build(executable, connect.server_command(db, agent.name), protocol.JOIN_PROMPT)


def agent_workdir(agent: Agent, fallback: Path) -> Path:
    workdir = Path(agent.workdir).expanduser() if agent.workdir else fallback

    if not workdir.is_dir():
        raise CoopError(f"Working directory {workdir} of agent {agent.name!r} does not exist.")

    return workdir


def normalize_workdir(text: str) -> str:
    if not text.strip():
        return ""

    workdir = Path(text.strip()).expanduser().resolve()

    if not workdir.is_dir():
        raise CoopError(f"Directory {workdir} does not exist.")

    return str(workdir)


def suggested_name(provider: str, role: str, taken: set[str]) -> str:
    words = "".join(character if character.isalnum() else " " for character in role.lower()).split()
    base = "-".join([provider, *words[:3]])[:28].rstrip("-")

    if base not in taken:
        return base

    return next(f"{base}-{number}" for number in range(2, 1000) if f"{base}-{number}" not in taken)
