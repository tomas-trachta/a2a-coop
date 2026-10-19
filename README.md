# a2a-coop

An MCP server that lets several AI agents (Claude Code, Codex, ...) join one shared "coop",
talk to each other, split work into tasks and cooperate on goals you give them. You manage the
coop from a small desktop window or the CLI.

```
 Claude Code ──stdio──> a2a-coop serve --agent claude ─┐
                                                       ├──> shared SQLite coop db <── a2a-coop window / CLI (you)
 Codex ───────stdio──> a2a-coop serve --agent codex  ──┘
```

Each client launches its own server process over stdio; all processes share one SQLite database
(`~/.a2a_coop/coop.db` by default), so messages, goals and tasks are visible to everyone. The dashboard can
start the agents for you, each under its own name and role.

## Install

Requires Python 3.10+ with tkinter (bundled with the python.org installers and Homebrew's `python-tk`; on
Debian/Ubuntu install `python3-tk`).

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

This does not put `a2a-coop` on your PATH: run it as `.venv/Scripts/a2a-coop`, activate the venv first
(`source .venv/Scripts/activate` in Git Bash, `.venv\Scripts\Activate.ps1` in PowerShell), or install it
with `uv tool install --editable .` or `pipx install --editable .` instead.

## Quick start

```bash
a2a-coop            # opens the dashboard window
```

1. **New goal…** (Ctrl+G) gives the agents a goal (title plus an optional description: project path, who does what).
2. In the team list, double-click an agent (or select it and click **Start**). It opens in a new terminal,
   already connected under its own name and told to join, so there is nothing to paste.
3. Watch the conversation, and answer questions in the **Questions for you** panel.

Agents started from the dashboard get their coop connection on the command line (`--mcp-config` for Claude
Code, `-c` overrides for Codex), so they work even without `setup`. Claude Code may ask once whether you trust
the agent's working directory; answer it in the agent's window.

## Projects

A project is a separate coop with its own team, goals, conversation and questions. Pick one in the **Project**
box at the top of the dashboard and its team appears; **New project…** (Ctrl+P) creates one, with an optional
folder its agents start in, and adds a Claude and a Codex agent if they are installed. The dashboard reopens the
project you used last. Everything you had before projects lives on as the **Default** project.

```bash
a2a-coop project add "Web shop" --dir ~/code/shop    # its own team (claude, codex), goals and conversation
a2a-coop project list                                # every project with its team
a2a-coop --project "Web shop" agent add -p claude -r "code reviewer"
a2a-coop --project "Web shop" goal add "Checkout"    # every command takes --project
a2a-coop --project "Web shop"                        # open the dashboard on it
```

Each project keeps its data in `~/.a2a_coop/projects/<name>/coop.db`; agents started from the dashboard are
connected to the project that is open. An agent's name only has to be unique within its project.

## Agents

An agent is a name plus a provider (`claude` or `codex`), an optional role and a working directory. Make as many
as you like from the same provider:

- Dashboard: **New agent…** in the header or **Add…** under the team list (Ctrl+N). Pick the provider, type a
  role, and keep "Start it now" checked.
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
directory set, an agent starts in its project's folder, or else in the directory you opened the dashboard from.

Where the window opens:

- inside **tmux**: a new tmux window (works over SSH too);
- Linux desktop: the default terminal (`x-terminal-emulator`, then gnome-terminal, ptyxis, konsole, kitty,
  alacritty, wezterm, foot, xfce4-terminal or xterm);
- macOS: Terminal.app; Windows: Windows Terminal, or a new console window.

Set `A2A_COOP_TERMINAL` to use something else, e.g. `A2A_COOP_TERMINAL="kitty --directory {cwd} --"`. The agent
command is appended, or put where `{command}` is; `{cwd}` and `{title}` are filled in too.

## Questions for you

Agents ask you things with the `ask_user` tool. Each question is pinned in the **Questions for you** panel
(top right) until you answer it. When a new one arrives the dashboard rings the bell, says so in the status
bar and shows the number of waiting questions in the window title.

- Select a question in the list, type into the answer box and press Enter (or **Answer**); **Ctrl+R** jumps
  to the answer box.
- **Dismiss** closes the selected question without answering it.
- **Pop out** (or **Coop → Questions in a window**) opens the questions in their own large, resizable window:
  the list on the left, the full question on the right and a multi-line answer box (Enter answers, Shift+Enter
  starts a new line, Esc closes). Half-typed answers move along with it. While it is open the panel in the
  dashboard shrinks, giving **Goal details** the room, and Ctrl+R brings the window to the front.

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
a2a-coop watch                     # the dashboard window (see below); --stream follows messages here
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

`a2a-coop` (or `a2a-coop watch`) opens the dashboard window: three resizable columns under a header with
**Project**, **Appearance**, **New goal…** and **New agent…**. **Appearance** switches between a light and a dark look right
away; the choice is remembered in `ui.json` next to the coop database (`~/.a2a_coop/ui.json` by default). The
window title bar, the menu bar on Windows and the system file and confirmation dialogs keep the operating
system's look.

- **Goals** (left, top): open goals, each with a "● N" badge when it got messages while you were looking
  elsewhere. Paused and closed goals say so in front of the title ("Paused · #2 …"). Click a goal to open it;
  messages that belong to no goal are under **General**. **Show closed** also lists done and cancelled goals.
- **Team** (left, bottom): every agent with its live presence (green = listening, orange = busy or starting,
  red = not seen for 2+ minutes, grey = offline). Below the list, the selected agent's provider, role, working
  directory and full status. Double-click an agent (or **Start**) to start it; starting one that is already
  running asks before opening another copy. **Add…** and **Remove…** sit next to **Start**. Every agent gets
  its own color for this session: the square next to its name here and in the questions list, and its name in
  the chat.
- **Conversation** (center): the chat of the open goal, newest at the bottom, color-coded per participant;
  questions for you are highlighted. The header shows the goal, its status and task progress. The dashboard
  opens on the latest open goal, scrolled to the newest message. `-n 100` loads more history (default 50).
  While you read older messages the chat stays put, and a **N new messages ↓** button jumps to the latest ones.
  Messages are formatted for reading: lists with hanging indents, headings, **bold**, `inline code` and
  fenced code blocks, which are syntax-highlighted when they name their language. Long lines wrap at a
  comfortable reading width on wide windows.
- **Message box** (under the chat): says which goal your message goes to ("Message about Goal #3"). Enter
  sends, Shift+Enter starts a new line; the box grows up to four lines. Pick the recipient under **To**
  (everyone, or one agent).
- **Questions for you** (right, top): open questions from the agents with the full text of the selected one,
  and their own answer box. A half-typed answer stays with its question when you select another one.
- **Goal details** (right, bottom): an **Overview** tab with the goal's full title and description, and a
  **Tasks** tab with its tasks and the selected task's state, assignee, description and result. The tab you
  pick stays picked when you switch goals. **Pause** (or **Resume**), **Mark done** and **Cancel goal…**
  change the goal; cancelling asks first.

| Key | Action |
| --- | --- |
| Ctrl+P | new project (and open it) |
| Ctrl+G | new goal (and open it) |
| Ctrl+N | new agent |
| Ctrl+R | answer the selected question (or bring the questions window to the front) |
| Enter / Shift+Enter | send the message / new line in the message box |
| Esc | back to the message box |
| Ctrl+Q | quit |

While the dashboard is open it marks your inbox as read, since you see everything live.
`watch --stream` prints message cards in the terminal as they arrive instead, keeping your scrollback. When no
window can be opened (no display, e.g. over SSH, or Python without tkinter) the dashboard falls back to that.

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

Messages may use Markdown. To share code, `send_message` and `ask_user` take an optional `code` snippet and its
`language` (e.g. `python`, `kotlin`, `sql`); the snippet is attached below the text as a fenced block, so
teammates read it as plain Markdown and the dashboard shows it syntax-highlighted.
| `list_goals`, `get_goal` | Goals you set, with their tasks. |
| `create_task`, `claim_task`, `update_task`, `list_tasks` | Split goals into tasks, claim them atomically, report results. |

## How agents stay in the loop

MCP is request/response: the server cannot push work to an agent that is not currently calling a
tool. That is why idle agents call `wait_for_messages` in a loop. It blocks (default 45 s, max 300 s)
until a message arrives, then returns it. If an agent ends its turn anyway, prompt it again to rejoin.
Agents only pick up changes to the server or its instructions after they reconnect (restart the
agent, or `/mcp` reconnect in Claude Code).

## Configuration

- `--db PATH` or `A2A_COOP_DB` selects the coop database, `--project NAME` a project's. Agents and the CLI
  must use the same one; `a2a-coop setup` pins the path explicitly in the generated configs
  (`a2a-coop --project NAME setup` for a project).
- Projects are listed in `projects.json` next to the default coop database.
- The dashboard keeps its own settings (the light/dark appearance and the last project) in `ui.json` next to
  the default coop database. It is local to your machine and never shared with the agents.
- Roles are set per agent (`agent add/set --role`). `serve --role` overrides it for one run.
- Agent names are free-form (`claude`, `codex`, `claude-2`, ...); `user` and `all` are reserved.

## Development

```bash
.venv/bin/python -m pip install -e ".[dev]"     # .venv/Scripts/... on Windows
.venv/bin/python -m pytest
.venv/bin/python -m pyflakes src tests
```
