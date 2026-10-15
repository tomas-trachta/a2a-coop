import pytest

from a2a_coop.errors import CoopError
from a2a_coop.store import EVERYONE, USER


def test_direct_message_reaches_only_its_recipient(team):
    team.send_message("claude", "codex", "hi codex")

    assert [message.body for message in team.take_unread("codex")] == ["hi codex"]
    assert team.take_unread("claude") == []
    assert team.take_unread(USER) == []


def test_broadcast_reaches_everyone_but_the_sender(team):
    team.send_message("claude", EVERYONE, "hello team")

    assert len(team.take_unread("codex")) == 1
    assert len(team.take_unread(USER)) == 1
    assert team.take_unread("claude") == []


def test_messages_are_delivered_once(team):
    team.send_message(USER, "codex", "first")

    assert len(team.take_unread("codex")) == 1
    assert team.take_unread("codex") == []
    assert team.count_unread("codex") == 0


def test_new_agent_does_not_receive_old_broadcasts(team):
    team.send_message(USER, EVERYONE, "before you joined")
    team.register_agent("gemini", "")

    assert team.take_unread("gemini") == []


def test_sending_to_unknown_agent_fails(team):
    with pytest.raises(CoopError, match="Unknown agent"):
        team.send_message("claude", "nobody", "hello?")


def test_reserved_names_cannot_register(store):
    for name in (USER, EVERYONE):
        with pytest.raises(CoopError, match="reserved"):
            store.register_agent(name, "")


def test_claiming_a_task_twice_is_refused(team):
    goal = team.create_goal("Ship it")
    task = team.create_task(goal.id, "Write code", "claude")

    claimed = team.claim_task(task.id, "codex")

    assert claimed.assignee == "codex"
    assert claimed.status == "in_progress"

    with pytest.raises(CoopError, match="already assigned to codex"):
        team.claim_task(task.id, "claude")


def test_update_task_validates_status(team):
    goal = team.create_goal("Ship it")
    task = team.create_task(goal.id, "Write code", "claude")

    with pytest.raises(CoopError, match="Invalid task status"):
        team.update_task(task.id, status="finished")

    done = team.update_task(task.id, status="done", result="merged")

    assert (done.status, done.result) == ("done", "merged")
    assert team.list_tasks(goal_id=goal.id, include_done=False) == []


def test_removed_task_is_gone(team):
    goal = team.create_goal("Ship it")
    task = team.create_task(goal.id, "Obsolete idea", "user")

    removed = team.remove_task(task.id)

    assert removed.title == "Obsolete idea"
    assert team.list_tasks(goal_id=goal.id) == []

    with pytest.raises(CoopError, match="does not exist"):
        team.remove_task(task.id)


def test_unassigning_a_task_in_progress_frees_it(team):
    goal = team.create_goal("Ship it")
    task = team.create_task(goal.id, "Write code", "user")
    team.claim_task(task.id, "codex")

    freed = team.update_task(task.id, unassign=True)

    assert (freed.assignee, freed.status) == (None, "todo")
    assert team.claim_task(task.id, "claude").assignee == "claude"


def test_task_title_and_description_can_be_edited(team):
    goal = team.create_goal("Ship it")
    task = team.create_task(goal.id, "Draft", "user")

    edited = team.update_task(task.id, title="Final title", description="More detail")

    assert (edited.title, edited.description) == ("Final title", "More detail")

    with pytest.raises(CoopError, match="must not be empty"):
        team.update_task(task.id, title="  ")


def test_assign_and_unassign_together_is_refused(team):
    goal = team.create_goal("Ship it")
    task = team.create_task(goal.id, "Draft", "user")

    with pytest.raises(CoopError, match="either an assignee or unassign"):
        team.update_task(task.id, assignee="codex", unassign=True)


def test_goal_can_be_edited(store):
    goal = store.create_goal("Draft goal")

    edited = store.update_goal(goal.id, title="Real goal", description="Details")

    assert (edited.title, edited.description) == ("Real goal", "Details")

    with pytest.raises(CoopError, match="Goal title must not be empty"):
        store.update_goal(goal.id, title="")


def test_removing_a_goal_removes_its_tasks(team):
    kept = team.create_goal("Keep")
    dropped = team.create_goal("Drop")
    team.create_task(kept.id, "Kept task", "user")
    team.create_task(dropped.id, "Dropped task", "user")

    goal, tasks = team.remove_goal(dropped.id)

    assert goal.title == "Drop"
    assert [task.title for task in tasks] == ["Dropped task"]
    assert [task.title for task in team.list_tasks()] == ["Kept task"]
    assert [goal.id for goal in team.list_goals()] == [kept.id]


def test_closed_goals_are_hidden_by_default(store):
    open_goal = store.create_goal("Keep going")
    closed_goal = store.create_goal("Old news")
    store.set_goal_status(closed_goal.id, "done")

    assert [goal.id for goal in store.list_goals()] == [open_goal.id]
    assert len(store.list_goals(include_closed=True)) == 2


def test_recent_messages_are_oldest_first(team):
    for number in range(5):
        team.send_message("claude", "codex", f"message {number}")

    assert [message.body for message in team.recent_messages(limit=2)] == ["message 3", "message 4"]
