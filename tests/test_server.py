import sys

import anyio
import pytest
from mcp import Client, StdioServerParameters

from a2a_coop.server import build_server

pytestmark = pytest.mark.anyio


def text_of(result) -> str:
    return "\n".join(block.text for block in result.content)


async def test_agents_exchange_messages_in_process(team):
    async with Client(build_server(team, "claude")) as claude, Client(build_server(team, "codex")) as codex:
        await claude.call_tool("send_message", {"to": "codex", "message": "can you take the API?"})

        received = await codex.call_tool("wait_for_messages", {"timeout_seconds": 5})

    assert "claude -> codex: can you take the API?" in text_of(received)


async def test_wait_for_messages_wakes_up_on_new_message(team):
    async with Client(build_server(team, "codex")) as codex:
        async with anyio.create_task_group() as group:
            group.start_soon(send_later, team)
            received = await codex.call_tool("wait_for_messages", {"timeout_seconds": 10})

    assert "please start" in text_of(received)


async def send_later(store) -> None:
    await anyio.sleep(1.5)
    store.send_message("user", "codex", "please start")


async def test_task_flow_is_announced_to_teammates(team):
    goal = team.create_goal("Build login")

    async with Client(build_server(team, "claude")) as claude, Client(build_server(team, "codex")) as codex:
        await claude.call_tool("create_task", {"goal_id": goal.id, "title": "Login form"})
        await codex.call_tool("claim_task", {"task_id": 1})
        refused = await claude.call_tool("claim_task", {"task_id": 1})
        briefing = await codex.call_tool("get_briefing", {})

    assert refused.is_error
    assert "already assigned to codex" in text_of(refused)
    assert "Task #1 [in_progress] Login form" in text_of(briefing)
    assert "claude created task #1" in "\n".join(message.body for message in team.take_unread("user"))


async def test_tools_and_join_prompt_are_exposed(team):
    async with Client(build_server(team, "claude")) as claude:
        tools = {tool.name for tool in (await claude.list_tools()).tools}
        prompts = {prompt.name for prompt in (await claude.list_prompts()).prompts}

    assert {"get_briefing", "send_message", "wait_for_messages", "claim_task"} <= tools
    assert "join" in prompts


async def test_separate_stdio_processes_share_the_coop(tmp_path):
    claude = Client(stdio_server(tmp_path, "claude"))
    codex = Client(stdio_server(tmp_path, "codex"))

    async with claude, codex:
        await claude.call_tool("list_agents", {})
        await codex.call_tool("list_agents", {})
        await claude.call_tool("send_message", {"to": "codex", "message": "ping across processes"})

        received = await codex.call_tool("wait_for_messages", {"timeout_seconds": 5})

    assert "ping across processes" in text_of(received)


def stdio_server(tmp_path, agent: str) -> StdioServerParameters:
    arguments = ["-m", "a2a_coop", "--db", str(tmp_path / "coop.db"), "serve", "--agent", agent]

    return StdioServerParameters(command=sys.executable, args=arguments)


async def test_ask_user_pins_a_question_and_role_reaches_the_instructions(store):
    store.define_agent("claude-reviewer", "claude", "code reviewer")

    async with Client(build_server(store, "claude-reviewer")) as reviewer:
        asked = await reviewer.call_tool("ask_user", {"question": "Merge now?"})
        briefing = await reviewer.call_tool("get_briefing", {})

    assert "question #" in text_of(asked)
    assert [request.body for request in store.open_questions()] == ["Merge now?"]
    assert "Your role in this team: code reviewer" in text_of(briefing)


async def test_tool_names_constant_matches_the_server(team):
    from a2a_coop.protocol import TOOL_NAMES

    async with Client(build_server(team, "claude")) as claude:
        tools = {tool.name for tool in (await claude.list_tools()).tools}

    assert tools == set(TOOL_NAMES)
