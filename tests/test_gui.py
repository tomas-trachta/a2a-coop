import tkinter as tk

import pytest

from a2a_coop import events, preferences, theme
from a2a_coop.gui import EVERYONE_LABEL, CoopDashboard
from a2a_coop.store import EVERYONE, USER


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"no display for tkinter: {error}")

    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def open_dashboard(root, tmp_path):
    def open_on(store) -> CoopDashboard:
        dashboard = CoopDashboard(root, store, 50, workdir=tmp_path)
        root.update()

        return dashboard

    return open_on


@pytest.fixture
def started(monkeypatch):
    names = []
    monkeypatch.setattr("a2a_coop.launch.start_in_window", lambda db, agent, fallback: names.append(agent.name) or "test")

    return names


def send(dashboard: CoopDashboard, recipient: str, text: str) -> None:
    dashboard.recipient.set(recipient)
    dashboard.composer.insert("1.0", text)
    dashboard.send_message()


def conversation(dashboard: CoopDashboard) -> str:
    return dashboard.conversation.get("1.0", "end")


def draft(dashboard: CoopDashboard) -> str:
    return dashboard.composer.get("1.0", "end-1c")


def sent_by_user(store) -> list[tuple[str, str]]:
    return [(message.recipient, message.body) for message in store.recent_messages() if message.sender == USER]


def test_composer_sends_messages(team, open_dashboard):
    dashboard = open_dashboard(team)

    send(dashboard, EVERYONE_LABEL, "hello everyone")
    send(dashboard, "codex", "just you")

    assert sent_by_user(team) == [(EVERYONE, "hello everyone"), ("codex", "just you")]
    assert draft(dashboard) == ""
    assert "just you" in conversation(dashboard)


def test_failed_send_keeps_the_draft(team, open_dashboard):
    dashboard = open_dashboard(team)

    send(dashboard, "nobody", "are you there")

    assert sent_by_user(team) == []
    assert draft(dashboard) == "are you there"
    assert "nobody" in dashboard.notice.cget("text")


def test_recipients_follow_the_team(team, open_dashboard):
    dashboard = open_dashboard(team)

    assert list(dashboard.recipient.cget("values")) == [EVERYONE_LABEL, "claude", "codex"]


def test_new_messages_appear_and_mark_user_inbox_read(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    team.announce(USER, events.goal_created(goal), goal.id)
    dashboard = open_dashboard(team)

    team.send_message("codex", USER, "design is ready", goal_id=goal.id)
    dashboard.refresh_dashboard()

    assert "user set a new goal #1: Grappling hook" in conversation(dashboard)
    assert "design is ready" in conversation(dashboard)
    assert team.count_unread(USER) == 0


def test_questions_are_pinned_and_answered(team, open_dashboard):
    question = team.ask_user("claude", "Which database?")
    dashboard = open_dashboard(team)
    listed = len(dashboard.question_list.get_children())

    dashboard.answer_box.insert(0, "SQLite")
    dashboard.answer()

    assert listed == 1
    assert dashboard.question_list.get_children() == ()
    assert team.take_unread("claude")[-1].body.startswith(f"Answer to #{question.id}")


def test_questions_can_be_dismissed(team, open_dashboard):
    team.ask_user("claude", "Ship it?")
    dashboard = open_dashboard(team)

    dashboard.dismiss_question()

    assert team.open_questions() == []
    assert "No open questions" in dashboard.question_hint.cget("text")
    assert dashboard.question_hint.winfo_manager() == "pack"
    assert dashboard.answer_box.instate(["disabled"])


def test_goal_dialog_creates_and_opens_a_goal(team, open_dashboard):
    dashboard = open_dashboard(team)
    dialog = dashboard.new_goal()

    dialog.goal_title.set("Grappling hook")
    dialog.description.insert("1.0", "Project: ~/code/arena")
    dialog.submit()

    goal = team.list_goals()[0]

    assert (goal.title, goal.description) == ("Grappling hook", "Project: ~/code/arena")
    assert dashboard.goal_id == goal.id
    assert not dialog.winfo_exists()


def test_goal_dialog_requires_a_title(team, open_dashboard):
    dashboard = open_dashboard(team)
    dialog = dashboard.new_goal()

    dialog.submit()

    assert team.list_goals() == []
    assert dialog.error.cget("text") == "Give the goal a title."


def test_agent_dialog_creates_and_starts_an_agent(team, open_dashboard, started, tmp_path):
    dashboard = open_dashboard(team)
    dialog = dashboard.new_agent()

    dialog.role.set("reviewer")
    dialog.submit()

    created = [agent for agent in team.list_agents() if agent.name not in ("claude", "codex")]

    assert len(created) == 1
    assert created[0].role == "reviewer" and created[0].workdir == str(tmp_path.resolve())
    assert started == [created[0].name]


def test_agent_dialog_reports_a_missing_directory(team, open_dashboard, tmp_path):
    dashboard = open_dashboard(team)
    dialog = dashboard.new_agent()

    dialog.workdir.set(str(tmp_path / "missing"))
    dialog.submit()

    assert "does not exist" in dialog.error.cget("text")
    assert dialog.winfo_exists()


def test_starting_the_selected_offline_agent(store, open_dashboard, started):
    store.define_agent("codex", "codex")
    dashboard = open_dashboard(store)

    dashboard.team.selection_set("codex")
    dashboard.start_selected_agent()

    assert started == ["codex"]
    assert dashboard.team.set("codex", "presence") == "starting…"


def test_dashboard_opens_the_latest_goal_and_shows_only_its_conversation(team, open_dashboard):
    old = team.create_goal("Old goal")
    latest = team.create_goal("Latest goal")
    team.send_message("claude", EVERYONE, "about the old goal", goal_id=old.id)
    team.send_message("claude", EVERYONE, "about the latest goal", goal_id=latest.id)
    team.send_message("claude", EVERYONE, "not about any goal")
    dashboard = open_dashboard(team)

    opened = dashboard.goal_id
    shown_latest = conversation(dashboard)

    send(dashboard, EVERYONE_LABEL, "hello latest")
    team.send_message("codex", EVERYONE, "more about the old goal", goal_id=old.id)
    dashboard.refresh_dashboard()
    unseen_old = dashboard.goal_list.set(f"goal-{old.id}", "new")

    dashboard.goal_list.selection_set(f"goal-{old.id}")
    dashboard.root.update()

    assert opened == latest.id
    assert "about the latest goal" in shown_latest and "old goal" not in shown_latest
    assert team.goal_messages(latest.id)[-1].body == "hello latest"
    assert unseen_old == "● 1"
    assert dashboard.goal_id == old.id
    assert "more about the old goal" in conversation(dashboard)


def test_goal_actions_change_the_open_goal(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)

    dashboard.set_goal_status("paused")

    assert team.get_goal(goal.id).status == "paused"
    assert dashboard.goal_buttons["paused"].instate(["disabled"])
    assert not dashboard.goal_buttons["active"].instate(["disabled"])


def test_closed_goals_are_listed_on_request(team, open_dashboard):
    closed = team.create_goal("Old goal")
    team.set_goal_status(closed.id, "done")
    team.create_goal("Current goal")
    dashboard = open_dashboard(team)

    hidden = dashboard.goal_list.exists(f"goal-{closed.id}")
    dashboard.show_closed.set(True)
    dashboard.refresh_dashboard()

    assert not hidden
    assert dashboard.goal_list.exists(f"goal-{closed.id}")


def test_a_goal_removed_elsewhere_falls_back_to_the_general_conversation(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)

    team.remove_goal(goal.id)
    dashboard.refresh_dashboard()

    assert dashboard.goal_id is None
    assert dashboard.conversation_title.cget("text") == "General conversation"
    assert dashboard.composer_scope.cget("text") == "Message in General"


def select(dashboard: CoopDashboard, tree, iid: str) -> None:
    tree.selection_set(iid)
    dashboard.root.update()


def answers_to(store, agent: str) -> list[str]:
    return [message.body for message in store.take_unread(agent) if message.sender == USER]


def test_goal_switch_updates_title_composer_scope_and_routing(team, open_dashboard):
    old = team.create_goal("Old goal")
    latest = team.create_goal("Latest goal")
    dashboard = open_dashboard(team)

    opened_scope = dashboard.composer_scope.cget("text")
    select(dashboard, dashboard.goal_list, f"goal-{old.id}")
    old_title = dashboard.conversation_title.cget("text")
    send(dashboard, EVERYONE_LABEL, "about the old one")
    select(dashboard, dashboard.goal_list, "general")
    send(dashboard, EVERYONE_LABEL, "about nothing")

    assert opened_scope == f"Message about Goal #{latest.id}"
    assert old_title == f"#{old.id} Old goal"
    assert team.goal_messages(old.id)[-1].body == "about the old one"
    assert team.goal_messages(None)[-1].body == "about nothing"
    assert dashboard.conversation_title.cget("text") == "General conversation"
    assert dashboard.composer_scope.cget("text") == "Message in General"


def test_answer_drafts_stay_with_their_question(team, open_dashboard):
    first_goal = team.create_goal("First")
    second_goal = team.create_goal("Second")
    first = team.ask_user("claude", "Which database?", goal_id=first_goal.id)
    second = team.ask_user("codex", "Which port?", goal_id=second_goal.id)
    dashboard = open_dashboard(team)

    select(dashboard, dashboard.question_list, str(first.id))
    dashboard.answer_box.insert(0, "SQLite")
    team.ask_user("claude", "Ship it?")
    dashboard.refresh_dashboard()
    kept_after_poll = (dashboard.selected_question(), dashboard.answer_box.get())

    select(dashboard, dashboard.question_list, str(second.id))
    draft_on_switch = dashboard.answer_box.get()
    dashboard.answer_box.insert(0, "8080")
    dashboard.answer()

    select(dashboard, dashboard.question_list, str(first.id))
    restored = dashboard.answer_box.get()
    dashboard.answer()

    assert kept_after_poll == (first.id, "SQLite")
    assert draft_on_switch == ""
    assert restored == "SQLite"
    codex_answers, claude_answers = answers_to(team, "codex"), answers_to(team, "claude")

    assert len(codex_answers) == 1 and codex_answers[0].startswith(f"Answer to #{second.id} ")
    assert codex_answers[0].endswith("8080")
    assert claude_answers[-1].startswith(f"Answer to #{first.id} ") and claude_answers[-1].endswith("SQLite")
    assert [question.body for question in team.open_questions()] == ["Ship it?"]


def test_a_new_question_does_not_take_the_selection(team, open_dashboard):
    question = team.ask_user("claude", "Which database?")
    dashboard = open_dashboard(team)

    dashboard.answer_box.insert(0, "Postgres")
    team.ask_user("codex", "Which port?")
    dashboard.refresh_dashboard()

    assert dashboard.selected_question() == question.id
    assert dashboard.answer_box.get() == "Postgres"
    assert len(dashboard.question_list.get_children()) == 2
    assert "Which database?" in dashboard.question_text.content()


def test_cancelling_a_goal_asks_first(team, open_dashboard, monkeypatch):
    goal = team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)
    asked = []

    monkeypatch.setattr(dashboard, "confirm", lambda question: asked.append(question) or False)
    dashboard.goal_buttons["cancelled"].invoke()
    kept = team.get_goal(goal.id).status

    monkeypatch.setattr(dashboard, "confirm", lambda question: asked.append(question) or True)
    dashboard.goal_buttons["cancelled"].invoke()

    assert kept == "active"
    assert team.get_goal(goal.id).status == "cancelled"
    assert len(asked) == 2 and f"#{goal.id}" in asked[0] and "Grappling hook" in asked[0]


def test_pause_and_resume_share_one_place(team, open_dashboard):
    team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)

    while_active = dashboard.goal_buttons["paused"].winfo_manager(), dashboard.goal_buttons["active"].winfo_manager()
    dashboard.goal_buttons["paused"].invoke()
    while_paused = dashboard.goal_buttons["paused"].winfo_manager(), dashboard.goal_buttons["active"].winfo_manager()

    assert while_active == ("pack", "")
    assert while_paused == ("", "pack")


def test_general_disables_goal_actions(team, open_dashboard):
    team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)

    select(dashboard, dashboard.goal_list, "general")

    assert all(button.instate(["disabled"]) for button in dashboard.goal_buttons.values())
    assert "Select a goal" in dashboard.goal_details.content()


def test_agent_details_show_the_full_status(store, open_dashboard):
    status = "Implementing the three-pane redesign" + " with a very long explanation" * 10
    store.register_agent("claude", "architect")
    store.define_agent("codex", "codex", "reviewer")
    store.set_agent_status("claude", status)
    dashboard = open_dashboard(store)

    first = dashboard.team.selection()
    select(dashboard, dashboard.team, "codex")
    dashboard.refresh_dashboard()
    codex_details = dashboard.agent_details.content()
    select(dashboard, dashboard.team, "claude")

    assert first == ("claude",)
    assert dashboard.team.selection() == ("claude",)
    assert status in dashboard.agent_details.content()
    assert "Role: architect" in dashboard.agent_details.content()
    assert "Provider: codex" in codex_details and "Role: reviewer" in codex_details


def test_team_buttons_need_an_agent(store, open_dashboard):
    dashboard = open_dashboard(store)

    assert dashboard.start_button.instate(["disabled"])
    assert dashboard.remove_button.instate(["disabled"])
    assert "No agents yet" in dashboard.agent_details.content()


def test_task_details_show_description_and_result(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    task = team.create_task(goal.id, "Design the hook", "codex", description="Rope physics", assignee="codex")
    team.update_task(task.id, status="done", result="Spec in docs/HOOK.md")
    dashboard = open_dashboard(team)

    select(dashboard, dashboard.task_list, str(task.id))
    dashboard.refresh_dashboard()

    details = dashboard.task_details.content()

    assert dashboard.task_list.selection() == (str(task.id),)
    assert dashboard.task_list.set(str(task.id), "state") == "Done"
    assert "Rope physics" in details and "Result: Spec in docs/HOOK.md" in details
    assert dashboard.conversation_summary.cget("text") == "Active  ·  1 of 1 tasks done"


def test_polling_keeps_the_reader_scrolled_back(team, open_dashboard):
    goal = team.create_goal("Grappling hook")

    for number in range(80):
        team.send_message("claude", EVERYONE, f"line {number}", goal_id=goal.id)

    dashboard = open_dashboard(team)
    dashboard.conversation.yview_moveto(0)
    team.send_message("codex", EVERYONE, "newest", goal_id=goal.id)
    dashboard.refresh_dashboard()

    assert dashboard.conversation.yview()[0] == 0
    assert "newest" in conversation(dashboard)


def typed(dashboard: CoopDashboard, *keys: str) -> None:
    dashboard.root.deiconify()
    dashboard.composer.focus_force()
    dashboard.root.update()

    for key in keys:
        if key.startswith("<"):
            dashboard.composer.event_generate(key)
        else:
            dashboard.composer.insert("insert", key)

    dashboard.root.update()


def test_shift_enter_adds_a_line_and_enter_sends_the_whole_draft(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)

    typed(dashboard, "first line", "<Shift-Return>", "second line")
    before_sending = (draft(dashboard), sent_by_user(team), int(dashboard.composer.cget("height")))
    typed(dashboard, "<Return>")

    assert before_sending == ("first line\nsecond line", [], 2)
    assert team.goal_messages(goal.id)[-1].body == "first line\nsecond line"
    assert draft(dashboard) == ""


def test_the_composer_grows_to_four_lines_and_shrinks_after_sending(team, open_dashboard):
    dashboard = open_dashboard(team)

    typed(dashboard, "one", "<Shift-Return>", "two", "<Shift-Return>", "three", "<Shift-Return>", "four", "<Shift-Return>", "five")
    grown = int(dashboard.composer.cget("height"))
    typed(dashboard, "<Return>")

    assert grown == 4
    assert int(dashboard.composer.cget("height")) == 2
    assert sent_by_user(team)[-1] == (EVERYONE, "one\ntwo\nthree\nfour\nfive")


def test_an_empty_draft_is_not_sent(team, open_dashboard):
    dashboard = open_dashboard(team)

    typed(dashboard, "   ", "<Shift-Return>", "<Return>")

    assert sent_by_user(team) == []


def test_a_failed_multiline_send_keeps_the_exact_draft(team, open_dashboard):
    dashboard = open_dashboard(team)
    dashboard.recipient.set("nobody")

    typed(dashboard, "  are you", "<Shift-Return>", "there  ", "<Return>")

    assert draft(dashboard) == "  are you\nthere  "
    assert sent_by_user(team) == []


def scroll_back_with_history(team, open_dashboard):
    goal = team.create_goal("Grappling hook")

    for number in range(80):
        team.send_message("claude", EVERYONE, f"line {number}", goal_id=goal.id)

    dashboard = open_dashboard(team)
    dashboard.conversation.yview_moveto(0)
    dashboard.root.update()

    return goal, dashboard


def test_new_messages_below_are_counted_while_reading_back(team, open_dashboard):
    goal, dashboard = scroll_back_with_history(team, open_dashboard)
    other = team.create_goal("Other goal")

    team.send_message("codex", EVERYONE, "newest", goal_id=goal.id)
    team.send_message("codex", EVERYONE, "elsewhere", goal_id=other.id)
    dashboard.refresh_dashboard()
    dashboard.root.update()
    first_count = dashboard.new_below

    team.send_message("codex", EVERYONE, "even newer", goal_id=goal.id)
    dashboard.refresh_dashboard()
    dashboard.root.update()

    assert first_count == 1
    assert dashboard.new_below == 2
    assert dashboard.jump_button.cget("text").startswith("2 new messages")
    assert dashboard.jump_button.winfo_manager() == "place"
    assert dashboard.conversation.yview()[0] == 0


def test_jumping_to_the_latest_clears_the_count(team, open_dashboard):
    goal, dashboard = scroll_back_with_history(team, open_dashboard)

    team.send_message("codex", EVERYONE, "newest", goal_id=goal.id)
    dashboard.refresh_dashboard()
    dashboard.jump_button.invoke()
    dashboard.root.update()

    assert dashboard.new_below == 0
    assert dashboard.jump_button.winfo_manager() == ""
    assert dashboard.conversation.yview()[1] >= 0.999


def test_scrolling_to_the_end_clears_the_count(team, open_dashboard):
    goal, dashboard = scroll_back_with_history(team, open_dashboard)

    team.send_message("codex", EVERYONE, "newest", goal_id=goal.id)
    dashboard.refresh_dashboard()
    dashboard.root.update()
    counted = dashboard.new_below
    dashboard.conversation.yview_moveto(1)
    dashboard.root.update()

    assert counted == 1
    assert dashboard.new_below == 0


def test_switching_goals_resets_the_count(team, open_dashboard):
    goal, dashboard = scroll_back_with_history(team, open_dashboard)

    team.send_message("codex", EVERYONE, "newest", goal_id=goal.id)
    dashboard.refresh_dashboard()
    select(dashboard, dashboard.goal_list, "general")
    select(dashboard, dashboard.goal_list, f"goal-{goal.id}")

    assert dashboard.new_below == 0
    assert dashboard.jump_button.winfo_manager() == ""


def test_following_the_end_shows_no_count(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)

    team.send_message("codex", EVERYONE, "newest", goal_id=goal.id)
    dashboard.refresh_dashboard()

    assert dashboard.new_below == 0


def test_goal_list_puts_titles_first_and_words_on_exceptional_states(team, open_dashboard):
    paused = team.create_goal("Stealth")
    team.set_goal_status(paused.id, "paused")
    active = team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)

    assert dashboard.goal_list.set(f"goal-{active.id}", "goal") == f"#{active.id} Grappling hook"
    assert dashboard.goal_list.set(f"goal-{paused.id}", "goal") == f"Paused · #{paused.id} Stealth"
    assert "status" not in dashboard.goal_list.cget("displaycolumns")
    assert "state" not in dashboard.task_list.cget("displaycolumns")


def current_tab(dashboard: CoopDashboard) -> str:
    return dashboard.inspector.tab(dashboard.inspector.select(), "text")


def pick_tab(dashboard: CoopDashboard, tab) -> None:
    dashboard.inspector.select(tab)
    dashboard.inspector.event_generate("<ButtonRelease-1>")
    dashboard.root.update()


def test_inspector_opens_on_tasks_when_the_goal_has_some(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    team.create_task(goal.id, "Design the hook", "codex")
    dashboard = open_dashboard(team)

    assert current_tab(dashboard) == "Tasks 0/1"


def test_inspector_opens_on_overview_without_tasks(team, open_dashboard):
    team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)

    assert current_tab(dashboard) == "Overview"


def test_the_chosen_tab_survives_polls_new_tasks_and_goal_switches(team, open_dashboard):
    old = team.create_goal("Old goal")
    latest = team.create_goal("Latest goal")
    team.create_task(latest.id, "Design the hook", "codex")
    team.create_task(old.id, "Old task", "codex")
    dashboard = open_dashboard(team)

    pick_tab(dashboard, dashboard.overview_tab)
    team.create_task(latest.id, "Build the hook", "claude")
    dashboard.refresh_dashboard()
    after_new_task = current_tab(dashboard)
    select(dashboard, dashboard.goal_list, f"goal-{old.id}")

    assert after_new_task == "Overview"
    assert current_tab(dashboard) == "Overview"


def test_general_shows_overview_and_returning_restores_the_tab(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    team.create_task(goal.id, "Design the hook", "codex")
    dashboard = open_dashboard(team)

    pick_tab(dashboard, dashboard.tasks_tab)
    select(dashboard, dashboard.goal_list, "general")
    on_general = (current_tab(dashboard), dashboard.inspector.tab(dashboard.tasks_tab, "state"))
    select(dashboard, dashboard.goal_list, f"goal-{goal.id}")

    assert on_general == ("Overview", "disabled")
    assert current_tab(dashboard) == "Tasks 0/1"
    assert dashboard.inspector.tab(dashboard.tasks_tab, "state") == "normal"


def test_teardown_leaves_no_callbacks_behind(team, tmp_path):
    try:
        window = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"no display for tkinter: {error}")

    window.withdraw()
    dashboard = CoopDashboard(window, team, 50, workdir=tmp_path)
    team.ask_user("claude", "Which database?")
    dashboard.refresh_dashboard()
    dashboard.notify("hello")
    pending = window.tk.call("after", "info")
    window.destroy()

    assert pending
    assert window.tk.call("after", "info") == ""


def test_general_round_trip_keeps_overview_too(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    team.create_task(goal.id, "Design the hook", "codex")
    dashboard = open_dashboard(team)

    pick_tab(dashboard, dashboard.overview_tab)
    select(dashboard, dashboard.goal_list, "general")
    select(dashboard, dashboard.goal_list, f"goal-{goal.id}")

    assert current_tab(dashboard) == "Overview"


def swatch_color(dashboard: CoopDashboard, tree, iid: str) -> str:
    image = tree.item(iid, "image")[0]
    red, green, blue = (int(channel) for channel in dashboard.root.tk.splitlist(dashboard.root.tk.call(image, "get", 2, 2)))

    return f"#{red:02X}{green:02X}{blue:02X}"


def chat_color(dashboard: CoopDashboard, name: str) -> str:
    return str(dashboard.conversation.tag_cget(f"participant:{name}", "foreground")).upper()


def test_each_agent_has_its_own_color_everywhere(team, open_dashboard):
    team.register_agent("gemini", "writer")
    team.send_message("claude", "codex", "hello codex")
    question = team.ask_user("codex", "Which port?")
    dashboard = open_dashboard(team)

    colors = {name: dashboard.colors.color(name) for name in ("claude", "codex", "gemini")}

    assert len(set(colors.values())) == 3
    assert USER not in colors and dashboard.colors.color(USER) not in colors.values()
    assert swatch_color(dashboard, dashboard.team, "codex") == colors["codex"]
    assert swatch_color(dashboard, dashboard.question_list, str(question.id)) == colors["codex"]
    assert chat_color(dashboard, "codex") == colors["codex"]
    assert chat_color(dashboard, "claude") == colors["claude"]
    assert dashboard.team.item("codex", "text") == "codex"
    assert dashboard.team.set("codex", "presence")


def test_joining_and_leaving_keeps_existing_colors(team, open_dashboard):
    dashboard = open_dashboard(team)
    before = {name: dashboard.colors.color(name) for name in ("claude", "codex")}

    team.register_agent("aider", "helper")
    dashboard.refresh_dashboard()
    team.remove_agent("codex")
    dashboard.refresh_dashboard()

    assert {name: dashboard.colors.color(name) for name in ("claude", "codex")} == before
    assert dashboard.colors.color("aider") not in before.values()


@pytest.mark.parametrize("palette", [theme.LIGHT, theme.DARK], ids=["light", "dark"])
def test_more_agents_than_palette_colors_stay_distinct(palette):
    colors = [theme.identity_color(palette, index) for index in range(30)]

    assert len(set(colors)) == 30
    assert palette.user not in colors and palette.everyone not in colors


def test_shift_enter_replaces_the_selected_text(team, open_dashboard):
    dashboard = open_dashboard(team)

    typed(dashboard, "hello world")
    dashboard.composer.tag_add("sel", "1.6", "1.11")
    dashboard.composer.mark_set("insert", "1.11")
    typed(dashboard, "<Shift-Return>", "there")

    assert draft(dashboard) == "hello \nthere"
    assert sent_by_user(team) == []


def test_the_first_task_does_not_switch_the_tab(team, open_dashboard):
    goal = team.create_goal("Grappling hook")
    dashboard = open_dashboard(team)

    opened_on = current_tab(dashboard)
    team.create_task(goal.id, "Design the hook", "codex")
    dashboard.refresh_dashboard()

    assert opened_on == "Overview"
    assert current_tab(dashboard) == "Overview"


def choose(dashboard: CoopDashboard, label: str) -> None:
    dashboard.appearance_choice.set(label)
    dashboard.appearance_choice.event_generate("<<ComboboxSelected>>")
    dashboard.root.update()


def background(widget) -> str:
    return str(widget.cget("background")).upper()


def popdown_background(combobox) -> str:
    popdown = combobox.tk.call("ttk::combobox::PopdownWindow", str(combobox))

    return str(combobox.tk.call(f"{popdown}.f.l", "cget", "-background")).upper()


def stored_state(store) -> tuple:
    return (
        [(message.id, message.body) for message in store.recent_messages(500)],
        [(goal.id, goal.status) for goal in store.list_goals(include_closed=True)],
        [(task.id, task.status) for task in store.list_tasks()],
        [question.id for question in store.open_questions()],
    )


def test_dashboard_opens_in_light_without_writing_preferences(team, open_dashboard, tmp_path):
    dashboard = open_dashboard(team)

    assert dashboard.appearance == "light"
    assert dashboard.appearance_choice.get() == "Light"
    assert background(dashboard.conversation) == theme.LIGHT.surface
    assert not (team.path.parent / "ui.json").exists()


def test_saved_dark_appearance_is_used_at_startup(team, open_dashboard):
    (team.path.parent / "ui.json").write_text('{"appearance": "dark"}', encoding="utf-8")

    dashboard = open_dashboard(team)

    assert dashboard.appearance == "dark"
    assert dashboard.appearance_choice.get() == "Dark"
    assert background(dashboard.conversation) == theme.DARK.surface
    assert background(dashboard.root) == theme.DARK.background


def test_a_broken_preference_file_opens_light(team, open_dashboard):
    (team.path.parent / "ui.json").write_text("{oops", encoding="utf-8")

    dashboard = open_dashboard(team)

    assert dashboard.appearance == "light"


def test_choosing_dark_recolors_everything_and_is_remembered(team, open_dashboard):
    question = team.ask_user("codex", "Which port?")
    team.send_message("claude", "codex", "hello codex")
    dashboard = open_dashboard(team)

    popdown_before = popdown_background(dashboard.recipient)
    choose(dashboard, "Dark")

    assert popdown_before == theme.LIGHT.surface
    assert popdown_background(dashboard.recipient) == theme.DARK.surface
    assert background(dashboard.root) == theme.DARK.background
    assert background(dashboard.composer) == theme.DARK.surface
    assert background(dashboard.agent_details.text) == theme.DARK.surface
    assert str(dashboard.conversation.tag_cget("question", "background")).upper() == theme.DARK.question_background
    assert str(dashboard.team.tag_configure("busy", "foreground")).upper() == theme.DARK.warning
    assert dashboard.root.tk.call("ttk::style", "lookup", "TFrame", "-background").upper() == theme.DARK.background
    assert chat_color(dashboard, "codex") == dashboard.colors.color("codex") == theme.DARK.identities[1]
    assert swatch_color(dashboard, dashboard.team, "codex") == theme.DARK.identities[1]
    assert swatch_color(dashboard, dashboard.question_list, str(question.id)) == theme.DARK.identities[1]
    assert preferences.load_appearance(team.path.parent / "ui.json") == "dark"


def test_returning_to_light_restores_the_original_colors(team, open_dashboard):
    team.send_message("claude", "codex", "hello codex")
    dashboard = open_dashboard(team)
    light = (chat_color(dashboard, "claude"), swatch_color(dashboard, dashboard.team, "claude"), background(dashboard.composer))

    choose(dashboard, "Dark")
    choose(dashboard, "Light")

    assert (chat_color(dashboard, "claude"), swatch_color(dashboard, dashboard.team, "claude"), background(dashboard.composer)) == light
    assert light == (theme.LIGHT.identities[0], theme.LIGHT.identities[0], theme.LIGHT.surface)


def test_switching_appearance_keeps_everything_the_operator_was_doing(team, open_dashboard):
    goal, dashboard = scroll_back_with_history(team, open_dashboard)
    task = team.create_task(goal.id, "Design the hook", "codex", description="Rope physics")
    first = team.ask_user("claude", "Which database?", goal_id=goal.id)
    second = team.ask_user("codex", "Which port?", goal_id=goal.id)
    team.send_message("codex", EVERYONE, "newest", goal_id=goal.id)
    dashboard.refresh_dashboard()

    typed(dashboard, "line one", "<Shift-Return>", "line two")
    dashboard.composer.edit_separator()
    typed(dashboard, " more")
    select(dashboard, dashboard.question_list, str(second.id))
    dashboard.answer_box.insert(0, "8080")
    select(dashboard, dashboard.task_list, str(task.id))
    pick_tab(dashboard, dashboard.overview_tab)
    dashboard.workspace.sashpos(0, 300)
    dashboard.column_placer.mark_moved()
    dashboard.root.update()

    before = (
        draft(dashboard),
        dashboard.selected_question(),
        dashboard.answer_box.get(),
        dashboard.task_list.selection(),
        current_tab(dashboard),
        dashboard.workspace.sashpos(0),
        dashboard.conversation.yview()[0],
        dashboard.new_below,
        dashboard.goal_id,
    )
    stored = stored_state(team)

    choose(dashboard, "Dark")
    after = (
        draft(dashboard),
        dashboard.selected_question(),
        dashboard.answer_box.get(),
        dashboard.task_list.selection(),
        current_tab(dashboard),
        dashboard.workspace.sashpos(0),
        dashboard.conversation.yview()[0],
        dashboard.new_below,
        dashboard.goal_id,
    )
    dashboard.composer.edit_undo()

    assert first.id != second.id
    assert after == before
    assert before[7] == 3 and before[0] == "line one\nline two more"
    assert draft(dashboard) == "line one\nline two"
    assert stored_state(team) == stored


def test_a_failed_save_keeps_the_chosen_appearance(team, open_dashboard, monkeypatch):
    dashboard = open_dashboard(team)

    def refuse(path, appearance):
        raise PermissionError("read-only")

    monkeypatch.setattr(preferences, "save_appearance", refuse)
    choose(dashboard, "Dark")

    assert dashboard.appearance == "dark"
    assert background(dashboard.conversation) == theme.DARK.surface
    assert "could not save appearance" in dashboard.notice.cget("text")


def test_open_and_new_dialogs_follow_the_appearance(team, open_dashboard):
    dashboard = open_dashboard(team)
    dialog = dashboard.new_goal()
    dialog.description.insert("1.0", "Project: ~/code/arena")
    dialog.submit()

    choose(dashboard, "Dark")
    agent_dialog = dashboard.new_agent()

    assert background(dialog) == theme.DARK.background
    assert background(dialog.description) == theme.DARK.surface
    assert dialog.description.get("1.0", "end-1c") == "Project: ~/code/arena"
    assert dialog.error.cget("text") == "Give the goal a title."
    assert background(agent_dialog) == theme.DARK.background
    assert popdown_background(agent_dialog.provider) == theme.DARK.surface
