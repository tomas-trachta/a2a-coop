import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

from .errors import CoopError

TERMINAL_ENV_VAR = "A2A_COOP_TERMINAL"

Which = Callable[[str], Optional[str]]

LINUX_TERMINALS: tuple[tuple[str, Callable[[str, list[str]], list[str]]], ...] = (
    ("x-terminal-emulator", lambda title, command: ["-T", title, "-e", *command]),
    ("gnome-terminal", lambda title, command: ["--title", title, "--", *command]),
    ("ptyxis", lambda title, command: ["--new-window", "--", *command]),
    ("konsole", lambda title, command: ["-e", *command]),
    ("kitty", lambda title, command: ["--title", title, *command]),
    ("alacritty", lambda title, command: ["--title", title, "-e", *command]),
    ("wezterm", lambda title, command: ["start", "--", *command]),
    ("foot", lambda title, command: ["--title", title, *command]),
    ("xfce4-terminal", lambda title, command: ["-T", title, "-x", *command]),
    ("xterm", lambda title, command: ["-T", title, "-e", *command]),
)


def window_command(
    title: str,
    command: list[str],
    cwd: Path,
    env: Mapping[str, str] = os.environ,
    platform: str = sys.platform,
    which: Which = shutil.which,
) -> tuple[list[str], str]:
    template = env.get(TERMINAL_ENV_VAR)

    if template:
        return custom_terminal(template, title, command, cwd), f"`{template.split()[0]}`"

    if env.get("TMUX"):
        return ["tmux", "new-window", "-n", title, "-c", str(cwd), shlex.join(command)], "a new tmux window"

    if platform == "win32":
        return windows_terminal(title, command, cwd, which)

    if platform == "darwin":
        return mac_terminal(command, cwd), "a new Terminal window"

    return linux_terminal(title, command, env, which)


def custom_terminal(template: str, title: str, command: list[str], cwd: Path) -> list[str]:
    parts = [part.replace("{title}", title).replace("{cwd}", str(cwd)) for part in shlex.split(template)]

    if "{command}" in parts:
        position = parts.index("{command}")
        return [*parts[:position], *command, *parts[position + 1:]]

    return [*parts, *command]


def windows_terminal(title: str, command: list[str], cwd: Path, which: Which) -> tuple[list[str], str]:
    if which("wt"):
        return ["wt", "-w", "0", "new-tab", "--title", title, "-d", str(cwd), *command], "a new Windows Terminal tab"

    return command, "a new console window"


def mac_terminal(command: list[str], cwd: Path) -> list[str]:
    script = f"cd {shlex.quote(str(cwd))} && {shlex.join(command)}"
    escaped = script.replace("\\", "\\\\").replace('"', '\\"')

    return [
        "osascript",
        "-e", f'tell application "Terminal" to do script "{escaped}"',
        "-e", 'tell application "Terminal" to activate',
    ]


def linux_terminal(title: str, command: list[str], env: Mapping[str, str], which: Which) -> tuple[list[str], str]:
    if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        raise CoopError(
            "No graphical display found. Run the dashboard inside tmux, or set "
            f"{TERMINAL_ENV_VAR} to a terminal command such as 'kitty --'."
        )

    for executable, arguments in LINUX_TERMINALS:
        if which(executable):
            return [executable, *arguments(title, command)], f"a new {executable} window"

    raise CoopError(f"No terminal emulator found. Install one, use tmux, or set {TERMINAL_ENV_VAR}.")


def open_window(title: str, command: list[str], cwd: Path) -> str:
    argv, where = window_command(title, command, cwd)

    try:
        subprocess.Popen(argv, cwd=cwd, **detached_options())
    except OSError as error:
        raise CoopError(f"Could not open a terminal with `{argv[0]}`: {error}") from error

    return where


def detached_options() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_CONSOLE}

    return {
        "start_new_session": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
