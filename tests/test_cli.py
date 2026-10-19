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


def test_agents_and_questions_from_the_cli(tmp_path, capsys):
    db = tmp_path / "coop.db"
    run(db, "agent", "add", "--provider", "codex", "--role", "test writer", "--dir", str(tmp_path))

    store = CoopStore(db)
    question = store.ask_user("codex-test-writer", "Which framework?")
    run(db, "questions")
    run(db, "answer", str(question.id), "pytest", "please")

    added = store.get_agent("codex-test-writer")
    output = capsys.readouterr().out

    assert (added.provider, added.role, added.workdir) == ("codex", "test writer", str(tmp_path))
    assert "Which framework?" in output
    assert store.open_questions() == []
    assert store.take_unread("codex-test-writer")[-1].body.endswith("pytest please")


def test_no_command_opens_the_dashboard():
    from a2a_coop.cli import build_parser, watch_messages

    assert build_parser().parse_args([]).handler is watch_messages


def test_projects_keep_their_own_team_and_goals(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("a2a_coop.launch.ensure_default_agents", lambda store: [])
    db = tmp_path / "coop.db"
    run(db, "project", "add", "Web shop", "--dir", str(tmp_path))
    run(db, "--project", "web shop", "agent", "add", "--provider", "codex", "--role", "shop dev")
    run(db, "--project", "Web shop", "goal", "add", "Checkout")
    run(db, "project", "list")

    shop = CoopStore(tmp_path / "projects" / "web-shop" / "coop.db")
    output = capsys.readouterr().out

    assert [agent.name for agent in shop.list_agents()] == ["codex-shop-dev"]
    assert [goal.title for goal in shop.list_goals()] == ["Checkout"]
    assert CoopStore(db).list_agents() == [] and CoopStore(db).list_goals() == []
    assert f"Web shop  ({tmp_path}): codex-shop-dev" in output
    assert "Default: no agents yet" in output
