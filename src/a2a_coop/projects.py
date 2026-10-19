import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .errors import CoopError
from .preferences import write_atomically

REGISTRY_FILE = "projects.json"
PROJECTS_DIR = "projects"
DB_FILE = "coop.db"
DEFAULT_PROJECT = "Default"
MAX_NAME_LENGTH = 40


@dataclass(frozen=True)
class Project:
    name: str
    db: Path
    folder: str = ""


def default_project(home: Path) -> Project:
    return Project(DEFAULT_PROJECT, Path(home) / DB_FILE)


def list_projects(home: Path) -> list[Project]:
    registered = [registered_project(home, entry) for entry in read_registry(home)]

    return [default_project(home), *sorted(registered, key=lambda project: project.name.lower())]


def registered_project(home: Path, entry: dict) -> Project:
    return Project(entry["name"], Path(home) / PROJECTS_DIR / entry["slug"] / DB_FILE, entry.get("folder", ""))


def get_project(home: Path, name: str) -> Project:
    project = find_project(home, name)

    if project is None:
        known = ", ".join(project.name for project in list_projects(home))
        raise CoopError(f"There is no project called {name!r}. Known projects: {known}.")

    return project


def find_project(home: Path, name: str) -> Optional[Project]:
    return next((project for project in list_projects(home) if project.name.lower() == name.strip().lower()), None)


def project_for_db(home: Path, db: Path) -> Optional[Project]:
    resolved = Path(db).expanduser().resolve()

    return next((project for project in list_projects(home) if project.db.resolve() == resolved), None)


def add_project(home: Path, name: str, folder: str = "") -> Project:
    name = validated_name(home, name)
    entries = read_registry(home)
    entry = {"name": name, "slug": unique_slug(name, {item["slug"] for item in entries}), "folder": folder}

    write_atomically(registry_path(home), {"projects": [*entries, entry]})

    return registered_project(home, entry)


def validated_name(home: Path, name: str) -> str:
    name = " ".join(name.split())

    if not name:
        raise CoopError("Give the project a name.")

    if len(name) > MAX_NAME_LENGTH:
        raise CoopError(f"Keep the project name under {MAX_NAME_LENGTH} characters.")

    if find_project(home, name) is not None:
        raise CoopError(f"A project called {name!r} already exists.")

    return name


def unique_slug(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"

    if base not in taken:
        return base

    return next(f"{base}-{number}" for number in range(2, 10000) if f"{base}-{number}" not in taken)


def registry_path(home: Path) -> Path:
    return Path(home) / REGISTRY_FILE


def read_registry(home: Path) -> list[dict]:
    try:
        loaded = json.loads(registry_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    entries = loaded.get("projects", []) if isinstance(loaded, dict) else []

    return [entry for entry in entries if isinstance(entry, dict) and entry.get("name") and entry.get("slug")]
