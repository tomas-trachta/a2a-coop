import json
from pathlib import Path

import pytest

from a2a_coop import connect, providers, terminal
from a2a_coop.errors import CoopError
from a2a_coop.models import Agent

SERVER = ["/usr/bin/python3", "-m", "a2a_coop", "--db", "/coop.db", "serve", "--agent", "claude-reviewer"]


def agent(name: str, provider: str = "") -> Agent:
    return Agent(name, "", "", "offline", 0, 0, provider, "")


def test_claude_gets_its_identity_from_an_inline_mcp_config():
    command = providers.claude_command("/bin/claude", SERVER, "join")
    config = json.loads(command[1].removeprefix("--mcp-config="))

    assert command[0] == "/bin/claude" and command[-1] == "join"
    assert config["mcpServers"]["a2a-coop"]["args"][-1] == "claude-reviewer"
    assert "--allowedTools=mcp__a2a-coop" in command


def test_codex_gets_its_identity_from_config_overrides():
    command = providers.codex_command("/bin/codex", SERVER, "join")
    overrides = [command[index + 1] for index, part in enumerate(command) if part == "-c"]

    assert 'mcp_servers.a2a-coop.args=["-m", "a2a_coop", "--db", "/coop.db", "serve", "--agent", "claude-reviewer"]' in overrides
    assert 'mcp_servers.a2a-coop.tools.ask_user.approval_mode="approve"' in overrides
    assert command[-1] == "join"


def test_provider_is_inferred_from_legacy_agent_names():
    assert providers.provider_for(agent("codex-2")).name == "codex"
    assert providers.provider_for(agent("helper", "claude")).name == "claude"

    with pytest.raises(CoopError, match="has no provider"):
        providers.provider_for(agent("helper"))


def test_suggested_names_are_unique():
    assert providers.suggested_name("claude", "Code reviewer", set()) == "claude-code-reviewer"
    assert providers.suggested_name("claude", "", {"claude"}) == "claude-2"


def test_tmux_is_preferred_when_running_inside_it():
    argv, where = terminal.window_command("reviewer", ["a2a-coop", "x y"], Path("/repo"), env={"TMUX": "1"}, platform="linux")

    assert argv == ["tmux", "new-window", "-n", "reviewer", "-c", "/repo", "a2a-coop 'x y'"]
    assert where == "a new tmux window"


def test_custom_terminal_template():
    argv, _ = terminal.window_command(
        "reviewer", ["run"], Path("/repo"), env={terminal.TERMINAL_ENV_VAR: "kitty --directory {cwd} --"}, platform="linux"
    )

    assert argv == ["kitty", "--directory", "/repo", "--", "run"]


def test_windows_prefers_windows_terminal():
    argv, where = terminal.window_command("reviewer", ["run"], Path("/repo"), env={}, platform="win32", which=lambda name: name)

    assert argv[:6] == ["wt", "-w", "0", "new-tab", "--title", "reviewer"]
    assert argv[-1] == "run"
    assert where == "a new Windows Terminal tab"


def test_windows_without_windows_terminal_runs_the_command_in_its_own_console():
    argv, where = terminal.window_command("reviewer", ["run", "x y"], Path("/repo"), env={}, platform="win32", which=lambda name: None)

    assert argv == ["run", "x y"]
    assert where == "a new console window"


def test_linux_uses_the_first_installed_terminal():
    installed = {"xterm", "kitty"}
    argv, _ = terminal.window_command(
        "reviewer", ["run"], Path("/repo"), env={"DISPLAY": ":0"}, platform="linux",
        which=lambda name: name if name in installed else None,
    )

    assert argv == ["kitty", "--title", "reviewer", "run"]


def test_linux_without_a_display_explains_what_to_do():
    with pytest.raises(CoopError, match="tmux"):
        terminal.window_command("reviewer", ["run"], Path("/repo"), env={}, platform="linux", which=lambda name: name)


def test_codex_setup_appends_once(tmp_path, monkeypatch):
    monkeypatch.setattr(connect.shutil, "which", lambda name: f"/bin/{name}")
    config = tmp_path / "config.toml"
    config.write_text('model = "x"\n')

    first = connect.configure_codex(Path("/coop.db"), "codex", config)
    second = connect.configure_codex(Path("/coop.db"), "codex", config)
    text = config.read_text()

    assert first.startswith("Codex: added") and second.startswith("Codex: already configured")
    assert text.startswith('model = "x"\n\n[mcp_servers.a2a-coop]')
    assert text.count("[mcp_servers.a2a-coop]") == 1
    assert "tool_timeout_sec = 330" in text
