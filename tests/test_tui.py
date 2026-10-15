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
