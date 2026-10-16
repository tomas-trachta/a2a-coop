import pytest
from textual.widgets import Input

from a2a_coop import events
from a2a_coop.store import EVERYONE, USER
from a2a_coop.tui import CoopDashboard, parse_composer

pytestmark = pytest.mark.anyio


def test_plain_text_goes_to_everyone():
    assert parse_composer("  hello team ") == (EVERYONE, "hello team")


def test_mention_selects_the_recipient():
    assert parse_composer("@codex please review") == ("codex", "please review")


def test_bare_mention_has_no_body():
    assert parse_composer("@codex") == ("codex", "")


async def submit(pilot, text: str) -> None:
    pilot.app.query_one("#composer", Input).value = text
    await pilot.press("enter")
    await pilot.pause()


def sent_by_user(store) -> list[tuple[str, str]]:
    return [(message.recipient, message.body) for message in store.recent_messages() if message.sender == USER]


async def test_composer_sends_messages(team):
    async with CoopDashboard(team, 50).run_test(size=(120, 40)) as pilot:
        await submit(pilot, "hello everyone")
        await submit(pilot, "@codex just you")

        composer_value = pilot.app.query_one("#composer", Input).value

    assert sent_by_user(team) == [(EVERYONE, "hello everyone"), ("codex", "just you")]
    assert composer_value == ""


async def test_unknown_recipient_keeps_the_draft(team):
    async with CoopDashboard(team, 50).run_test(size=(120, 40)) as pilot:
        await submit(pilot, "@nobody are you there")

        composer_value = pilot.app.query_one("#composer", Input).value

    assert sent_by_user(team) == []
    assert composer_value == "@nobody are you there"


async def test_new_messages_appear_and_mark_user_inbox_read(team):
    goal = team.create_goal("Grappling hook")
    team.announce(USER, events.goal_created(goal))

    async with CoopDashboard(team, 50).run_test(size=(120, 40)) as pilot:
        team.send_message("codex", USER, "design is ready")
        pilot.app.refresh_dashboard()
        await pilot.pause()

        shown = len(pilot.app.query(".message"))

    assert shown == 2
    assert team.count_unread(USER) == 0


async def test_sidebar_hides_on_narrow_terminals(team):
    async with CoopDashboard(team, 50).run_test(size=(80, 30)) as pilot:
        await pilot.pause()

        sidebar_shown = pilot.app.query_one("#sidebar").display

    assert sidebar_shown is False


async def test_questions_are_pinned_and_answered_from_their_own_box(team):
    question = team.ask_user("claude", "Which database?")

    async with CoopDashboard(team, 50).run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        listed = pilot.app.query_one("#questions").option_count

        await pilot.press("ctrl+r")
        pilot.app.query_one("#answer", Input).value = "SQLite"
        await pilot.press("enter")
        await pilot.pause()

        remaining = pilot.app.query_one("#questions").option_count

    assert listed == 1
    assert remaining == 0
    assert team.take_unread("claude")[-1].body.startswith(f"Answer to #{question.id}")


async def test_questions_stay_visible_on_narrow_terminals(team):
    team.ask_user("claude", "Ship it?")

    async with CoopDashboard(team, 50).run_test(size=(80, 30)) as pilot:
        await pilot.pause()

        side_shown = pilot.app.query_one("#side").display

    assert side_shown is True


async def test_goal_form_creates_a_goal(team):
    async with CoopDashboard(team, 50).run_test(size=(120, 40)) as pilot:
        await pilot.press("ctrl+g")
        await pilot.pause()
        pilot.app.screen.query_one("#title", Input).value = "Grappling hook"
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert [goal.title for goal in team.list_goals()] == ["Grappling hook"]
    assert "user set a new goal #1: Grappling hook" in [message.body for message in team.recent_messages()]


async def test_agent_form_creates_and_starts_an_agent(team, tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr("a2a_coop.launch.start_in_window", lambda db, agent, fallback: started.append(agent.name) or "test")

    async with CoopDashboard(team, 50, workdir=tmp_path).run_test(size=(120, 40)) as pilot:
        await pilot.press("ctrl+n")
        await pilot.pause()
        pilot.app.screen.query_one("#role", Input).value = "reviewer"
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

    created = [agent for agent in team.list_agents() if agent.name not in ("claude", "codex")]

    assert len(created) == 1
    assert created[0].role == "reviewer" and created[0].workdir == str(tmp_path)
    assert started == [created[0].name]


async def test_enter_on_an_offline_agent_starts_it(store, monkeypatch):
    started = []
    monkeypatch.setattr("a2a_coop.launch.start_in_window", lambda db, agent, fallback: started.append(agent.name) or "test")
    store.define_agent("codex", "codex")

    async with CoopDashboard(store, 50).run_test(size=(120, 40)) as pilot:
        await pilot.press("ctrl+t")
        await pilot.press("enter")
        await pilot.pause()

    assert started == ["codex"]
