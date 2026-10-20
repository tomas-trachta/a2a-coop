import os
import subprocess
import sys
from pathlib import Path

from . import providers, terminal
from .models import Agent


def start_in_window(db: Path, agent: Agent, fallback_dir: Path) -> str:
    providers.agent_command(db, agent)
    workdir = providers.agent_workdir(agent, fallback_dir)
    command = [
        sys.executable, "-m", "a2a_coop", "--db", str(db.resolve()),
        "agent", "start", agent.name, "--here", "--hold", "--dir", str(workdir),
    ]

    return terminal.open_window(agent.name, command, workdir)


def run_here(db: Path, agent: Agent, fallback_dir: Path) -> int:
    command = providers.agent_command(db, agent)
    os.chdir(providers.agent_workdir(agent, fallback_dir))

    if sys.platform == "win32":
        name_console(agent.name)
        return subprocess.call(command)

    os.execv(command[0], command)


def name_console(title: str) -> None:
    import ctypes

    ctypes.windll.kernel32.SetConsoleTitleW(title)


def ensure_default_agents(store) -> list[Agent]:
    if store.list_agents():
        return []

    return [store.define_agent(provider.name, provider.name) for provider in providers.installed_providers()]


def add_team_agents(store, team: str) -> list[Agent]:
    taken = {agent.name for agent in store.list_agents()}
    added = []

    for provider in providers.installed_providers():
        agent = store.define_agent(providers.suggested_name(provider.name, team, taken), provider.name, team=team)
        taken.add(agent.name)
        added.append(agent)

    return added
