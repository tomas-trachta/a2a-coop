from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Agent:
    name: str
    role: str
    status: str
    activity: str
    joined_at: float
    last_seen: float
    provider: str = ""
    workdir: str = ""
    current_goal_id: Optional[int] = None


@dataclass(frozen=True)
class Goal:
    id: int
    title: str
    description: str
    status: str
    created_at: float


@dataclass(frozen=True)
class Task:
    id: int
    goal_id: int
    title: str
    description: str
    assignee: Optional[str]
    status: str
    result: str
    created_by: str
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class Message:
    id: int
    sender: str
    recipient: str
    body: str
    kind: str
    created_at: float
    handled_at: Optional[float] = None
    goal_id: Optional[int] = None
