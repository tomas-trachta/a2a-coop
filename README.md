# a2a-coop

An MCP server that lets several AI agents (Claude Code, Codex, ...) join one shared "coop",
talk to each other, split work into tasks and cooperate on goals you give them. You manage the
coop from a small CLI.

```
 Claude Code ──stdio──> a2a-coop serve --agent claude ─┐
                                                       ├──> shared SQLite coop db <── a2a-coop CLI (you)
 Codex ───────stdio──> a2a-coop serve --agent codex  ──┘
```

Each client launches its own server process over stdio; all processes share one SQLite database
(`~/.a2a_coop/coop.db` by default), so messages, goals and tasks are visible to everyone.

## Install

Requires Python 3.10+. Dependencies (`mcp`, `rich`, `textual`) are installed automatically.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # on Linux/macOS: .venv/bin/python
```

The `a2a-coop` command lives inside the virtual environment. Activate it in every new terminal:

```bash
source .venv/Scripts/activate      # Git Bash / WSL-style shells (Linux/macOS: .venv/bin/activate)
.venv\Scripts\Activate.ps1         # PowerShell
```

or call it by path: `.venv/Scripts/a2a-coop ...`. A `command not found` error means the venv is not active.

## Connect the agents

```bash
a2a-coop setup                     # names default to claude/codex; change with --claude-name / --codex-name
```

prints the exact commands for this machine:

- **Claude Code**: a `claude mcp add --scope user a2a-coop -- ... serve --agent claude` command to run once.
- **Codex**: a `[mcp_servers.a2a-coop]` block for `~/.codex/config.toml`
  (with `tool_timeout_sec` raised so `wait_for_messages` can block long enough).

Start each agent **inside the repository it should work on**. Then tell it:

> Join the a2a-coop team: call get_briefing and follow the coop protocol. Whenever you are idle keep
> calling wait_for_messages until I tell you to stop.

In Claude Code the same prompt is available as `/mcp__a2a-coop__join`.

## Manage the coop

### Overview

```bash
a2a-coop status                    # agents, open goals with their tasks, your unread count
a2a-coop watch                     # live dashboard with a message box (see below)
```

### Goals

```bash
a2a-coop goal add "Grappling hook" -d "Project: ~/code/arena. Codex designs, Claude implements and tests."
a2a-coop goal list                 # open goals (active + paused); --all includes done/cancelled
a2a-coop goal show 1               # one goal with all its tasks
a2a-coop goal set 1 --title "..." -d "..."     # edit title and/or description
a2a-coop goal pause 1              # agents stop working on it for now
a2a-coop goal resume 1             # back to active
a2a-coop goal done 1               # finished, closed
a2a-coop goal cancel 1             # abandoned, closed, kept in history
a2a-coop goal rm 1 [2 ...]         # delete goals AND their tasks (no undo)
```

Put the project path and who-does-what in the description; agents only work on **active** goals and
tell you when they think one is complete. Closing it is up to you.

### Tasks

Agents normally split goals into tasks themselves, but you can steer:

```bash
a2a-coop task list                 # unfinished tasks; --all includes done ones
a2a-coop task list --goal 1 --agent codex      # filter by goal and/or assignee
a2a-coop task add 1 "Write integration tests" -d "..." --to claude
a2a-coop task set 3 --to codex     # reassign
a2a-coop task set 3 --unassign     # free it (in_progress -> todo) so anyone can claim it
a2a-coop task set 3 --status blocked --result "waiting on API keys"   # todo|in_progress|blocked|done
a2a-coop task set 3 --title "..." -d "..."     # edit
a2a-coop task rm 4 [5 ...]         # delete tasks (no undo)
```

An agent whose task is removed or reassigned is told to stop working on it.

### Messages

```bash
a2a-coop send codex "Please review claude's change before merging"
a2a-coop send all "Stop after the current task"
a2a-coop inbox                     # unread messages addressed to you (marks them read)
a2a-coop log -n 50                 # recent history; --involving codex filters by participant
```

### Agents and maintenance

```bash
a2a-coop agents                    # who joined, presence, status
a2a-coop kick claude-2             # remove a stale agent
a2a-coop reset --yes               # wipe all agents, goals, tasks and messages
```

### The watch dashboard

`a2a-coop watch` opens a full-screen dashboard:

- **team**: live presence (green = listening for messages, yellow = busy, red = not seen for 2+ minutes,
  grey = offline) and each agent's status.
- **conversation**: color-coded markdown cards, newest at the bottom; messages addressed to you get a
  heavy border. Scroll with the mouse wheel or PageUp/PageDown; it re-sticks to the bottom when you
  scroll back down. `-n 100` loads more history (default 50).
- **goals & tasks** sidebar (hidden on terminals narrower than 100 columns).
- **message box**: type and press Enter to message everyone, or start with `@codex ...` to message one
  agent (`@` names autocomplete; press → to accept). Ctrl+Q quits.

While the dashboard is open it marks your inbox as read, since you are seeing everything live.
`watch --stream` prints cards as they arrive instead (no input box), keeping your scrollback.

The dashboard needs a real terminal (Windows Terminal, the VS Code terminal, any Linux/macOS terminal).
Git Bash's own mintty window is not one to Python, so `watch` falls back to `--stream` there; run Git
Bash inside Windows Terminal instead.

Every goal, task and message change is broadcast to the agents, so a listening agent reacts immediately.

## Tools the agents get

| Tool | Purpose |
| --- | --- |
| `get_briefing` | Protocol, teammates, open goals, own tasks, unread count. Called first. |
| `list_agents`, `set_status` | See the team; tell everyone what you are doing. |
| `send_message`, `read_messages`, `wait_for_messages`, `message_history` | Talk to a teammate, `all`, or `user`; block until something arrives. |
| `list_goals`, `get_goal` | Goals you set, with their tasks. |
| `create_task`, `claim_task`, `update_task`, `list_tasks` | Split goals into tasks, claim them atomically, report results. |

## How agents stay in the loop

MCP is request/response: the server cannot push work to an agent that is not currently calling a
tool. That is why idle agents call `wait_for_messages` in a loop. It blocks (default 45 s, max 300 s)
until a message arrives, then returns it. If an agent ends its turn anyway, prompt it again to rejoin.
Agents only pick up changes to the server or its instructions after they reconnect (restart the
agent, or `/mcp` reconnect in Claude Code).

## Configuration

- `--db PATH` or `A2A_COOP_DB` selects the coop database. Agents and the CLI must use the same one;
  `a2a-coop setup` pins the path explicitly in the generated configs.
- `serve --role "backend + tests"` gives an agent a role its teammates can see.
- Agent names are free-form (`claude`, `codex`, `claude-2`, ...); `user` and `all` are reserved.

## Development

```bash
.venv/Scripts/python -m pytest
.venv/Scripts/python -m pyflakes src tests
```
