import time
from typing import Optional

import anyio
from mcp.server.mcpserver import MCPServer

from . import events, protocol, render
from .models import Message
from .store import ACTIVE, OFFLINE, WAITING, CoopStore

DEFAULT_WAIT_SECONDS = 45
MAX_WAIT_SECONDS = 300
POLL_INTERVAL_SECONDS = 1.0


def serve(store: CoopStore, agent: str, role: str = "") -> None:
    store.register_agent(agent, role)

    try:
        build_server(store, agent).run("stdio")
    finally:
        store.touch_agent(agent, OFFLINE)


def build_server(store: CoopStore, agent: str) -> MCPServer:
    server = MCPServer(name="a2a-coop", instructions=protocol.instructions_for(agent, agent_role(store, agent)))

    register_team_tools(server, store, agent)
    register_message_tools(server, store, agent)
    register_goal_tools(server, store, agent)
    register_task_tools(server, store, agent)
    register_prompts(server)

    return server


def register_team_tools(server: MCPServer, store: CoopStore, agent: str) -> None:
    @server.tool(structured_output=False)
    def get_briefing() -> str:
        """Start here. Explains how the coop works and shows your teammates, the open goals, your open tasks and your unread message count."""
        store.touch_agent(agent)

        return briefing(store, agent)

    @server.tool(structured_output=False)
    def list_agents() -> str:
        """List every agent in the coop with its role, presence and current status."""
        store.touch_agent(agent)

        return render.agents(store.list_agents(), time.time())

    @server.tool(structured_output=False)
    def set_status(status: str) -> str:
        """Tell the team and the user what you are doing right now, e.g. "implementing task #3: login form"."""
        updated = store.set_agent_status(agent, status)

        return f"Status set: {updated.status or '(cleared)'}"


def register_message_tools(server: MCPServer, store: CoopStore, agent: str) -> None:
    @server.tool(structured_output=False)
    def send_message(to: str, message: str) -> str:
        """Send a message. `to` is a teammate's name, "all" for every agent plus the user, or "user" for the human operator. To ask the user something that needs a decision, use ask_user instead."""
        store.touch_agent(agent)
        sent = store.send_message(agent, to, message)

        return f"Sent message #{sent.id} to {sent.recipient}."

    @server.tool(structured_output=False)
    def ask_user(question: str) -> str:
        """Ask the human operator a question that only they can decide. It is pinned in their dashboard until answered; the answer arrives later as a message from "user", so do not stop listening."""
        store.touch_agent(agent)
        asked = store.ask_user(agent, question)

        return f"Asked the user (question #{asked.id}). The answer will arrive as a message; keep working or call wait_for_messages."

    @server.tool(structured_output=False)
    def read_messages() -> str:
        """Return your unread messages immediately (without waiting) and mark them as read."""
        store.touch_agent(agent)

        return render.messages(store.take_unread(agent), "No unread messages.")

    @server.tool(structured_output=False)
    async def wait_for_messages(timeout_seconds: int = DEFAULT_WAIT_SECONDS) -> str:
        """Wait until a message arrives for you, then return it. Call this in a loop whenever you are idle so teammates and the user can reach you. timeout_seconds is capped at 300."""
        try:
            received = await wait_for_unread(store, agent, timeout_seconds)
        finally:
            store.touch_agent(agent, ACTIVE)

        if not received:
            return "No new messages yet. Call wait_for_messages again to keep listening."

        return render.messages(received)

    @server.tool(structured_output=False)
    def message_history(limit: int = 30, involving: Optional[str] = None) -> str:
        """Show the most recent coop messages, oldest first. Optionally only those sent by or addressed to one participant. Use it to catch up on context."""
        store.touch_agent(agent)

        return render.messages(store.recent_messages(clamp(limit, 1, 200), involving))


def register_goal_tools(server: MCPServer, store: CoopStore, agent: str) -> None:
    @server.tool(structured_output=False)
    def list_goals(include_closed: bool = False) -> str:
        """List the goals the user has set. Closed (done/cancelled) goals are hidden unless include_closed is true."""
        store.touch_agent(agent)

        return render.goals(store.list_goals(include_closed))

    @server.tool(structured_output=False)
    def get_goal(goal_id: int) -> str:
        """Show one goal with its full description and all of its tasks."""
        store.touch_agent(agent)

        return render.goal_details(store.get_goal(goal_id), store.list_tasks(goal_id=goal_id))


def register_task_tools(server: MCPServer, store: CoopStore, agent: str) -> None:
    @server.tool(structured_output=False)
    def create_task(goal_id: int, title: str, description: str = "", assignee: Optional[str] = None) -> str:
        """Create a task under a goal. Leave assignee empty to let anyone claim it, or name a teammate (or yourself) to assign it."""
        store.touch_agent(agent)
        task = store.create_task(goal_id, title, agent, description, assignee)
        store.announce(agent, events.task_created(agent, task))

        return render.task_details(task)

    @server.tool(structured_output=False)
    def claim_task(task_id: int) -> str:
        """Take ownership of an unassigned task and mark it in_progress. Fails if a teammate already owns it."""
        store.touch_agent(agent)
        task = store.claim_task(task_id, agent)
        store.announce(agent, events.task_claimed(agent, task))

        return render.task_details(task)

    @server.tool(structured_output=False)
    def update_task(
        task_id: int,
        status: Optional[str] = None,
        result: Optional[str] = None,
        assignee: Optional[str] = None,
    ) -> str:
        """Update a task. status is one of todo, in_progress, blocked, done. result is a short summary of the outcome or of what blocks you. assignee hands the task to a teammate."""
        store.touch_agent(agent)
        task = store.update_task(task_id, status, result, assignee)
        store.announce(agent, events.task_updated(agent, task))

        return render.task_details(task)

    @server.tool(structured_output=False)
    def list_tasks(goal_id: Optional[int] = None, assignee: Optional[str] = None, include_done: bool = False) -> str:
        """List tasks, optionally filtered by goal and/or assignee. Done tasks are hidden unless include_done is true."""
        store.touch_agent(agent)

        return render.tasks(store.list_tasks(goal_id, assignee, include_done))


def register_prompts(server: MCPServer) -> None:
    @server.prompt(name="join", description="Join the coop and start cooperating on the active goals.")
    def join() -> str:
        return protocol.JOIN_PROMPT


def agent_role(store: CoopStore, agent: str) -> str:
    return next((known.role for known in store.list_agents() if known.name == agent), "")


def briefing(store: CoopStore, agent: str) -> str:
    sections = [
        protocol.instructions_for(agent, agent_role(store, agent)),
        render.section("Team", render.agents(store.list_agents(), time.time())),
        render.section("Open goals", render.goals(store.list_goals())),
        render.section("Your open tasks", render.tasks(store.list_tasks(assignee=agent, include_done=False))),
        f"Unread messages: {store.count_unread(agent)} (read them with read_messages or wait_for_messages).",
    ]

    return "\n\n".join(sections)


async def wait_for_unread(store: CoopStore, agent: str, timeout_seconds: int) -> list[Message]:
    deadline = time.monotonic() + clamp(timeout_seconds, 1, MAX_WAIT_SECONDS)

    while True:
        store.touch_agent(agent, WAITING)
        received = store.take_unread(agent)

        if received or time.monotonic() >= deadline:
            return received

        await anyio.sleep(POLL_INTERVAL_SECONDS)


def clamp(value: int, lowest: int, highest: int) -> int:
    return max(lowest, min(value, highest))
