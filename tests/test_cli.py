from a2a_coop.cli import main
from a2a_coop.store import CoopStore


def run(db, *arguments: str) -> None:
    main(["--db", str(db), *arguments])


def test_task_lifecycle_from_the_cli(tmp_path, capsys):
    db = tmp_path / "coop.db"
    run(db, "goal", "add", "Grappling hook")
    run(db, "task", "add", "1", "Design")
    run(db, "task", "add", "1", "Prototype")
    run(db, "task", "set", "1", "--title", "Game design", "--status", "in_progress")
    run(db, "task", "rm", "2")

    store = CoopStore(db)
    tasks = store.list_tasks(goal_id=1)
    events = [message.body for message in store.recent_messages()]

    assert [(task.id, task.title, task.status) for task in tasks] == [(1, "Game design", "in_progress")]
    assert "user removed task #2: Prototype" in events
    assert "Removed Task #2" in capsys.readouterr().out


def test_goal_edit_and_remove_from_the_cli(tmp_path):
    db = tmp_path / "coop.db"
    run(db, "goal", "add", "Draft")
    run(db, "task", "add", "1", "Some task")
    run(db, "goal", "set", "1", "--title", "Grappling hook")
    run(db, "goal", "add", "Other")
    run(db, "goal", "rm", "1")

    store = CoopStore(db)
    events = [message.body for message in store.recent_messages()]

    assert [goal.title for goal in store.list_goals()] == ["Other"]
    assert store.list_tasks() == []
    assert "user removed goal #1 and its 1 task(s): Grappling hook" in events
