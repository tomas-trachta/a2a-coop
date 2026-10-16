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
(`~/.a2a_coop/coop.db` by default), so messages, goals and tasks are visible to everyone. The dashboard can
start the agents for you, each under its own name and role.

## Install

Requires Python 3.10+.

```bash
./install.sh
```

installs `a2a-coop` (with uv or pipx when available, otherwise into `.venv` with a link in `~/.local/bin`)
and runs `a2a-coop setup`. `setup` registers the coop MCP server with the Claude Code and Codex installed
on this machine (`claude mcp add` and `~/.codex/config.toml`) and creates one agent per installed provider.
Run it again at any time; it never touches an existing configuration. `setup --print` only shows what it would add.

On Windows, install manually:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/a2a-coop setup
```

## Quick start

```bash
a2a-coop            # opens the dashboard
```

1. **Ctrl+G** gives the agents a goal (title plus an optional description: project path, who does what).
2. In the team list (**Ctrl+T**), select an agent and press **Enter**. It opens in a new terminal, already
   connected under its own name and told to join, so there is nothing to paste.
3. Watch the conversation, and answer questions in the **questions for you** panel.

Agents started from the dashboard get their coop connection on the command line (`--mcp-config` for Claude
Code, `-c` overrides for Codex), so they work even without `setup`. Claude Code may ask once whether you trust
the agent's working directory; answer it in the agent's window.

## Agents

An agent is a name plus a provider (`claude` or `codex`), an optional role and a working directory. Make as many
as you like from the same provider:

- Dashboard: **Ctrl+N** (or "+ add an agent" in the team list). Pick the provider, type a role, and keep
  "Start it now" checked.
- CLI:

```bash
a2a-coop agent add --provider claude --role "code reviewer" --dir ~/code/arena --start
a2a-coop agent add claude-tests -p claude -r "writes and runs tests"
a2a-coop agent list
a2a-coop agent set claude-tests --role "integration tests" --dir ~/code/arena
a2a-coop agent start claude-tests           # new terminal window
a2a-coop agent start claude-tests --here    # in this terminal
a2a-coop agent rm claude-tests
```

The name defaults to provider plus role (`claude-code-reviewer`). The role is shown to teammates and put in the
agent's own instructions, so a reviewer reviews and leaves the implementation to others. With no working
directory set, an agent starts in the directory you opened the dashboard from.

Where the window opens:

- inside **tmux**: a new tmux window (works over SSH too);
- Linux desktop: the default terminal (`x-terminal-emulator`, then gnome-terminal, ptyxis, konsole, kitty,
  alacritty, wezterm, foot, xfce4-terminal or xterm);
- macOS: Terminal.app; Windows: Windows Terminal, or a new console window.

Set `A2A_COOP_TERMINAL` to use something else, e.g. `A2A_COOP_TERMINAL="kitty --directory {cwd} --"`. The agent
command is appended, or put where `{command}` is; `{cwd}` and `{title}` are filled in too.

## Questions for you

Agents ask you things with the `ask_user` tool. Each question is pinned in the **questions for you** panel
(top right, shown even on narrow terminals) until you answer it. The dashboard rings the bell and pops up a
notification when a new one arrives.

- **Ctrl+R** jumps to the answer box. Enter sends the answer to the agent that asked.
- With several questions open, pick one with ↑/↓ in the list; **d** dismisses the selected one.

From the CLI: `a2a-coop questions`, `a2a-coop answer 12 "use SQLite"`, `a2a-coop dismiss 12`.

## Connecting agents by hand

You can still start `claude` or `codex` yourself in any repository. After `setup` they join as `claude` and
`codex`. Tell them:

> Join the a2a-coop team: call get_briefing and follow the coop protocol. Whenever you are idle keep
> calling wait_for_messages until I tell you to stop.

In Claude Code the same prompt is available as `/mcp__a2a-coop__join`. `a2a-coop agent start NAME --here` does
all of this for any agent, in the current terminal.

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
a2a-coop send codex "Please review claude's change before merging" --goal 2
a2a-coop send all "Stop after the current task"
a2a-coop inbox                     # unread messages addressed to you (marks them read)
a2a-coop log -n 50                 # recent history; --involving codex filters by participant
a2a-coop log --goal 2              # one goal's conversation
```

### Maintenance

```bash
a2a-coop agents                    # all agents, presence, status
a2a-coop kick claude-2             # remove an agent (same as `agent rm`)
a2a-coop reset --yes               # wipe all agents, goals, tasks and messages
```

### The dashboard

`a2a-coop` (or `a2a-coop watch`) opens a full-screen dashboard:

- **team**: every agent with its live presence (green = listening, yellow = busy or starting, red = not seen for
  2+ minutes, grey = offline) and status. Enter on an agent starts it; the last row adds a new one.
- **conversation**: the chat of one goal. The dashboard opens on the latest open goal; switch with Enter in
  the goals list or Ctrl+O (which also lists closed goals). Messages that belong to no goal are under
  "general". Color-coded markdown cards, newest at the bottom; questions for you have a yellow heavy border.
  Scroll with the mouse wheel or PageUp/PageDown. `-n 100` loads more history (default 50).
- **questions for you**: open questions from the agents, with their own answer box.
- **goals**: open goals with task progress and a "● N new" badge for goals that got messages while you were
  looking elsewhere, plus the description and tasks of the open goal (hidden on terminals narrower than 100
  columns; Ctrl+O still works).
- **message box**: Enter messages everyone about the open goal; start with `@codex ...` to message one agent
  (`@` names autocomplete, → accepts).

| Key | Action |
| --- | --- |
| Ctrl+O | switch goal |
| Ctrl+G | new goal (and open it) |
| Ctrl+N | new agent |
| Ctrl+T | focus the team list (Enter starts the selected agent) |
| Ctrl+R | answer the selected question |
| Ctrl+P | command palette: pause, resume, finish or cancel goals; start another copy of an agent; remove agents |
| Esc | back to the message box |
| Ctrl+Q | quit |

While the dashboard is open it marks your inbox as read, since you see everything live.
`watch --stream` prints cards as they arrive instead (no input box), keeping your scrollback.

The dashboard needs a real terminal (Windows Terminal, the VS Code terminal, any Linux/macOS terminal).
Git Bash's own mintty window is not one to Python, so `watch` falls back to `--stream` there; run Git
Bash inside Windows Terminal instead.

Each message belongs to a goal (or to none). Goal and task events belong to their goal, your messages to the goal
you have open, and an agent's messages to the goal it passes as `goal_id`, otherwise the goal it is working on
(its latest claimed/updated task, opened goal or received message), otherwise the only active goal. Agents still
receive every message addressed to them; they see the goal as `[goal #N]`.

Every goal, task and message change is broadcast to the agents, so a listening agent reacts immediately.

## Tools the agents get

| Tool | Purpose |
| --- | --- |
| `get_briefing` | Protocol, teammates, open goals, own tasks, unread count. Called first. |
| `list_agents`, `set_status` | See the team; tell everyone what you are doing. |
| `send_message`, `read_messages`, `wait_for_messages`, `message_history` | Talk to a teammate, `all`, or `user`; block until something arrives. |
| `ask_user` | Ask the human a question; it is pinned in the dashboard and the answer arrives as a message. |
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
- Roles are set per agent (`agent add/set --role`). `serve --role` overrides it for one run.
- Agent names are free-form (`claude`, `codex`, `claude-2`, ...); `user` and `all` are reserved.

## Development

```bash
.venv/bin/python -m pip install -e ".[dev]"     # .venv/Scripts/... on Windows
.venv/bin/python -m pytest
.venv/bin/python -m pyflakes src tests
```
