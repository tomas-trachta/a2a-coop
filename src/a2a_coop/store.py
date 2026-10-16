import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence

from .errors import CoopError
from .models import Agent, Goal, Message, Task

USER = "user"
EVERYONE = "all"

CHAT = "chat"
EVENT = "event"
QUESTION = "question"

GOAL_STATUSES = ("active", "paused", "done", "cancelled")
OPEN_GOAL_STATUSES = ("active", "paused")
TASK_STATUSES = ("todo", "in_progress", "blocked", "done")

ACTIVE = "active"
WAITING = "waiting"
OFFLINE = "offline"

AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$")
BUSY_TIMEOUT_SECONDS = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    activity TEXT NOT NULL DEFAULT 'active',
    joined_at REAL NOT NULL,
    last_seen REAL NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    workdir TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    assignee TEXT,
    status TEXT NOT NULL DEFAULT 'todo',
    result TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    body TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'chat',
    created_at REAL NOT NULL,
    handled_at REAL
);

CREATE TABLE IF NOT EXISTS cursors (
    reader TEXT PRIMARY KEY,
    last_read_id INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS messages_by_recipient ON messages(recipient, id);
CREATE INDEX IF NOT EXISTS tasks_by_goal ON tasks(goal_id);
"""

ADDED_COLUMNS = {
    "agents": {
        "provider": "TEXT NOT NULL DEFAULT ''",
        "workdir": "TEXT NOT NULL DEFAULT ''",
    },
    "messages": {
        "handled_at": "REAL",
    },
}

BACKFILLS = {
    ("messages", "handled_at"): "UPDATE messages SET handled_at = created_at",
}

UPSERT_AGENT = """
INSERT INTO agents (name, role, status, activity, joined_at, last_seen)
VALUES (?, ?, '', 'active', ?, ?)
ON CONFLICT(name) DO UPDATE SET
    role = CASE WHEN excluded.role != '' THEN excluded.role ELSE agents.role END,
    activity = 'active',
    last_seen = excluded.last_seen
"""

UPSERT_CURSOR = """
INSERT INTO cursors (reader, last_read_id) VALUES (?, ?)
ON CONFLICT(reader) DO UPDATE SET last_read_id = excluded.last_read_id
"""

UNREAD_MESSAGES = """
SELECT * FROM messages
WHERE id > ? AND sender != ? AND recipient IN (?, ?)
ORDER BY id
"""

CLAIM_TASK = """
UPDATE tasks SET assignee = ?, status = 'in_progress', updated_at = ?
WHERE id = ? AND status != 'done' AND (assignee IS NULL OR assignee = ?)
"""

OPEN_QUESTIONS = f"""
SELECT * FROM messages
WHERE recipient = '{USER}' AND kind = '{QUESTION}' AND handled_at IS NULL
ORDER BY id
"""

INSERT_AGENT = """
INSERT INTO agents (name, role, status, activity, joined_at, last_seen, provider, workdir)
VALUES (?, ?, '', 'offline', ?, ?, ?, ?)
"""

RECENT_MESSAGES = """
SELECT * FROM (
    SELECT * FROM messages
    WHERE ? IS NULL OR sender = ? OR recipient = ?
    ORDER BY id DESC
    LIMIT ?
) ORDER BY id
"""


class CoopStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._create_schema()

    def register_agent(self, name: str, role: str) -> Agent:
        validate_agent_name(name)
        now = time.time()

        with self._connect() as connection:
            connection.execute(UPSERT_AGENT, (name, role.strip(), now, now))
            connection.execute(
                "INSERT OR IGNORE INTO cursors (reader, last_read_id) VALUES (?, ?)",
                (name, self._latest_message_id(connection)),
            )

        return self.get_agent(name)

    def define_agent(self, name: str, provider: str, role: str = "", workdir: str = "") -> Agent:
        validate_agent_name(name)
        require_text(provider, "Provider")

        if self._fetch_one("SELECT name FROM agents WHERE name = ?", (name,)) is not None:
            raise CoopError(f"An agent named {name!r} already exists.")

        now = time.time()

        with self._connect() as connection:
            connection.execute(INSERT_AGENT, (name, role.strip(), now, now, provider.strip(), workdir.strip()))
            connection.execute(
                "INSERT OR IGNORE INTO cursors (reader, last_read_id) VALUES (?, ?)",
                (name, self._latest_message_id(connection)),
            )

        return self.get_agent(name)

    def update_agent(
        self,
        name: str,
        role: Optional[str] = None,
        provider: Optional[str] = None,
        workdir: Optional[str] = None,
    ) -> Agent:
        self.get_agent(name)
        changes = {
            column: value.strip()
            for column, value in (("role", role), ("provider", provider), ("workdir", workdir))
            if value is not None
        }

        if not changes:
            raise CoopError("Nothing to update: pass a role, provider or working directory.")

        assignments = ", ".join(f"{column} = ?" for column in changes)
        self._execute(f"UPDATE agents SET {assignments} WHERE name = ?", (*changes.values(), name))

        return self.get_agent(name)

    def get_agent(self, name: str) -> Agent:
        row = self._fetch_one("SELECT * FROM agents WHERE name = ?", (name,))

        if row is None:
            raise CoopError(f"Unknown agent {name!r}. Known agents: {self._agent_names_text()}.")

        return Agent(**row)

    def list_agents(self) -> list[Agent]:
        return [Agent(**row) for row in self._fetch_all("SELECT * FROM agents ORDER BY name")]

    def touch_agent(self, name: str, activity: str = ACTIVE) -> None:
        self._execute(
            "UPDATE agents SET activity = ?, last_seen = ? WHERE name = ?",
            (activity, time.time(), name),
        )

    def set_agent_status(self, name: str, status: str) -> Agent:
        self._execute(
            "UPDATE agents SET status = ?, activity = 'active', last_seen = ? WHERE name = ?",
            (status.strip(), time.time(), name),
        )

        return self.get_agent(name)

    def remove_agent(self, name: str) -> None:
        self.get_agent(name)

        with self._connect() as connection:
            connection.execute("DELETE FROM agents WHERE name = ?", (name,))
            connection.execute("DELETE FROM cursors WHERE reader = ?", (name,))
            connection.execute(
                "UPDATE messages SET handled_at = ? WHERE recipient = ? AND sender = ? AND handled_at IS NULL",
                (time.time(), USER, name),
            )

    def create_goal(self, title: str, description: str = "") -> Goal:
        require_text(title, "Goal title")

        cursor = self._execute(
            "INSERT INTO goals (title, description, status, created_at) VALUES (?, ?, 'active', ?)",
            (title.strip(), description.strip(), time.time()),
        )

        return self.get_goal(cursor.lastrowid)

    def get_goal(self, goal_id: int) -> Goal:
        row = self._fetch_one("SELECT * FROM goals WHERE id = ?", (goal_id,))

        if row is None:
            raise CoopError(f"Goal #{goal_id} does not exist.")

        return Goal(**row)

    def list_goals(self, include_closed: bool = False) -> list[Goal]:
        statuses = GOAL_STATUSES if include_closed else OPEN_GOAL_STATUSES

        rows = self._fetch_all(
            f"SELECT * FROM goals WHERE status IN ({placeholders(statuses)}) ORDER BY id",
            statuses,
        )

        return [Goal(**row) for row in rows]

    def set_goal_status(self, goal_id: int, status: str) -> Goal:
        require_choice(status, GOAL_STATUSES, "goal status")
        self.get_goal(goal_id)

        self._execute("UPDATE goals SET status = ? WHERE id = ?", (status, goal_id))

        return self.get_goal(goal_id)

    def update_goal(
        self,
        goal_id: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Goal:
        self.get_goal(goal_id)
        changes = text_changes("Goal", title=title, description=description)

        if not changes:
            raise CoopError("Nothing to update: pass a title or description.")

        assignments = ", ".join(f"{column} = ?" for column in changes)
        self._execute(f"UPDATE goals SET {assignments} WHERE id = ?", (*changes.values(), goal_id))

        return self.get_goal(goal_id)

    def remove_goal(self, goal_id: int) -> tuple[Goal, list[Task]]:
        goal = self.get_goal(goal_id)
        tasks = self.list_tasks(goal_id=goal_id)

        with self._connect() as connection:
            connection.execute("DELETE FROM tasks WHERE goal_id = ?", (goal_id,))
            connection.execute("DELETE FROM goals WHERE id = ?", (goal_id,))

        return goal, tasks

    def create_task(
        self,
        goal_id: int,
        title: str,
        created_by: str,
        description: str = "",
        assignee: Optional[str] = None,
    ) -> Task:
        require_text(title, "Task title")
        self.get_goal(goal_id)
        self._require_assignable(assignee)
        now = time.time()

        cursor = self._execute(
            """
            INSERT INTO tasks (goal_id, title, description, assignee, status, result, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'todo', '', ?, ?, ?)
            """,
            (goal_id, title.strip(), description.strip(), assignee, created_by, now, now),
        )

        return self.get_task(cursor.lastrowid)

    def get_task(self, task_id: int) -> Task:
        row = self._fetch_one("SELECT * FROM tasks WHERE id = ?", (task_id,))

        if row is None:
            raise CoopError(f"Task #{task_id} does not exist.")

        return Task(**row)

    def list_tasks(
        self,
        goal_id: Optional[int] = None,
        assignee: Optional[str] = None,
        include_done: bool = True,
    ) -> list[Task]:
        where, params = task_filter(goal_id, assignee, include_done)
        rows = self._fetch_all(f"SELECT * FROM tasks {where} ORDER BY id", params)

        return [Task(**row) for row in rows]

    def claim_task(self, task_id: int, agent: str) -> Task:
        cursor = self._execute(CLAIM_TASK, (agent, time.time(), task_id, agent))

        if cursor.rowcount == 0:
            raise CoopError(self._claim_refusal(task_id))

        return self.get_task(task_id)

    def update_task(
        self,
        task_id: int,
        status: Optional[str] = None,
        result: Optional[str] = None,
        assignee: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        unassign: bool = False,
    ) -> Task:
        current = self.get_task(task_id)
        changes = {
            **status_change(status),
            **text_changes("Task", title=title, description=description, result=result),
            **self._assignee_change(current, assignee, unassign, status),
        }

        if not changes:
            raise CoopError("Nothing to update: pass a status, assignee, title, description or result.")

        assignments = ", ".join(f"{column} = ?" for column in changes)

        self._execute(
            f"UPDATE tasks SET {assignments}, updated_at = ? WHERE id = ?",
            (*changes.values(), time.time(), task_id),
        )

        return self.get_task(task_id)

    def remove_task(self, task_id: int) -> Task:
        task = self.get_task(task_id)

        self._execute("DELETE FROM tasks WHERE id = ?", (task_id,))

        return task

    def send_message(self, sender: str, recipient: str, body: str, kind: str = CHAT) -> Message:
        require_text(body, "Message")
        self._require_recipient(recipient, sender)

        cursor = self._execute(
            "INSERT INTO messages (sender, recipient, body, kind, created_at) VALUES (?, ?, ?, ?, ?)",
            (sender, recipient, body.strip(), kind, time.time()),
        )

        return self.get_message(cursor.lastrowid)

    def announce(self, sender: str, text: str) -> Message:
        return self.send_message(sender, EVERYONE, text, EVENT)

    def ask_user(self, sender: str, question: str) -> Message:
        return self.send_message(sender, USER, question, QUESTION)

    def open_questions(self) -> list[Message]:
        return [Message(**row) for row in self._fetch_all(OPEN_QUESTIONS)]

    def answer_question(self, message_id: int, text: str) -> Message:
        question = self._open_question(message_id)
        reply = self.send_message(USER, question.sender, reply_body(question, text))
        self._mark_handled(message_id)

        return reply

    def dismiss_question(self, message_id: int) -> Message:
        question = self._open_question(message_id)
        self._mark_handled(message_id)

        return question

    def get_message(self, message_id: int) -> Message:
        row = self._fetch_one("SELECT * FROM messages WHERE id = ?", (message_id,))

        if row is None:
            raise CoopError(f"Message #{message_id} does not exist.")

        return Message(**row)

    def take_unread(self, reader: str) -> list[Message]:
        with self._connect() as connection:
            rows = self._unread_rows(connection, reader)

            if rows:
                connection.execute(UPSERT_CURSOR, (reader, rows[-1]["id"]))

        return [Message(**dict(row)) for row in rows]

    def count_unread(self, reader: str) -> int:
        with self._connect() as connection:
            return len(self._unread_rows(connection, reader))

    def recent_messages(self, limit: int = 30, involving: Optional[str] = None) -> list[Message]:
        rows = self._fetch_all(RECENT_MESSAGES, (involving, involving, involving, limit))

        return [Message(**row) for row in rows]

    def messages_after(self, message_id: int) -> list[Message]:
        rows = self._fetch_all("SELECT * FROM messages WHERE id > ? ORDER BY id", (message_id,))

        return [Message(**row) for row in rows]

    def latest_message_id(self) -> int:
        with self._connect() as connection:
            return self._latest_message_id(connection)

    def reset(self) -> None:
        with self._connect() as connection:
            for table in ("messages", "tasks", "goals", "cursors", "agents", "sqlite_sequence"):
                connection.execute(f"DELETE FROM {table}")

    def _create_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)
            add_missing_columns(connection)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_SECONDS)
        connection.row_factory = sqlite3.Row

        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._connect() as connection:
            return connection.execute(sql, params)

    def _fetch_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(sql, params).fetchone()

        return dict(row) if row is not None else None

    def _fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()

        return [dict(row) for row in rows]

    def _latest_message_id(self, connection: sqlite3.Connection) -> int:
        return connection.execute("SELECT COALESCE(MAX(id), 0) FROM messages").fetchone()[0]

    def _last_read_id(self, connection: sqlite3.Connection, reader: str) -> int:
        row = connection.execute("SELECT last_read_id FROM cursors WHERE reader = ?", (reader,)).fetchone()

        return row[0] if row is not None else 0

    def _unread_rows(self, connection: sqlite3.Connection, reader: str) -> list[sqlite3.Row]:
        last_read_id = self._last_read_id(connection, reader)

        return connection.execute(UNREAD_MESSAGES, (last_read_id, reader, reader, EVERYONE)).fetchall()

    def _open_question(self, message_id: int) -> Message:
        message = self.get_message(message_id)

        if message.kind != QUESTION or message.recipient != USER:
            raise CoopError(f"Message #{message_id} is not a question for you.")

        if message.handled_at is not None:
            raise CoopError(f"Message #{message_id} was already answered or dismissed.")

        return message

    def _mark_handled(self, message_id: int) -> None:
        self._execute("UPDATE messages SET handled_at = ? WHERE id = ?", (time.time(), message_id))

    def _agent_names_text(self) -> str:
        names = [agent.name for agent in self.list_agents()]

        return ", ".join(names) if names else "none yet"

    def _require_assignable(self, assignee: Optional[str]) -> None:
        if assignee is not None:
            self.get_agent(assignee)

    def _require_recipient(self, recipient: str, sender: str) -> None:
        if recipient == sender:
            raise CoopError("You cannot send a message to yourself.")

        if recipient not in (USER, EVERYONE):
            self.get_agent(recipient)

    def _claim_refusal(self, task_id: int) -> str:
        task = self.get_task(task_id)

        if task.status == "done":
            return f"Task #{task_id} is already done."

        return f"Task #{task_id} is already assigned to {task.assignee}."

    def _assignee_change(
        self,
        current: Task,
        assignee: Optional[str],
        unassign: bool,
        status: Optional[str],
    ) -> dict[str, Any]:
        if assignee is not None and unassign:
            raise CoopError("Pass either an assignee or unassign, not both.")

        if unassign:
            return unassignment(current, status)

        if assignee is None:
            return {}

        self._require_assignable(assignee)

        return {"assignee": assignee}


def add_missing_columns(connection: sqlite3.Connection) -> None:
    for table, columns in ADDED_COLUMNS.items():
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}

        for column, definition in columns.items():
            if column in existing:
                continue

            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            backfill = BACKFILLS.get((table, column))

            if backfill:
                connection.execute(backfill)


def reply_body(question: Message, text: str) -> str:
    require_text(text, "Answer")
    first_line = question.body.strip().splitlines()[0]
    quoted = first_line if len(first_line) <= 80 else first_line[:77] + "..."

    return f"Answer to #{question.id} (\"{quoted}\"):\n{text.strip()}"


def validate_agent_name(name: str) -> None:
    if name in (USER, EVERYONE):
        raise CoopError(f"{name!r} is reserved and cannot be used as an agent name.")

    if not AGENT_NAME_PATTERN.match(name):
        raise CoopError("Agent names must be 1-32 characters: letters, digits, '.', '_' or '-'.")


def require_text(value: str, label: str) -> None:
    if not value or not value.strip():
        raise CoopError(f"{label} must not be empty.")


def require_choice(value: str, choices: Sequence[str], label: str) -> None:
    if value not in choices:
        raise CoopError(f"Invalid {label} {value!r}. Choose one of: {', '.join(choices)}.")


def status_change(status: Optional[str]) -> dict[str, Any]:
    if status is None:
        return {}

    require_choice(status, TASK_STATUSES, "task status")

    return {"status": status}


def text_changes(entity: str, **fields: Optional[str]) -> dict[str, Any]:
    changes = {column: value.strip() for column, value in fields.items() if value is not None}

    if "title" in changes:
        require_text(changes["title"], f"{entity} title")

    return changes


def unassignment(current: Task, status: Optional[str]) -> dict[str, Any]:
    if status is None and current.status == "in_progress":
        return {"assignee": None, "status": "todo"}

    return {"assignee": None}


def placeholders(values: Sequence[Any]) -> str:
    return ", ".join("?" for _ in values)


def task_filter(
    goal_id: Optional[int],
    assignee: Optional[str],
    include_done: bool,
) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    if goal_id is not None:
        conditions.append("goal_id = ?")
        params.append(goal_id)

    if assignee is not None:
        conditions.append("assignee = ?")
        params.append(assignee)

    if not include_done:
        conditions.append("status != 'done'")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    return where, params
