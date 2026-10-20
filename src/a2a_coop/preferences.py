import json
import os
import tempfile
from pathlib import Path

FILE_NAME = "ui.json"
APPEARANCE_KEY = "appearance"
PROJECT_KEY = "project"
TEAMS_KEY = "teams"
APPEARANCES = ("light", "dark")
DEFAULT_APPEARANCE = "light"


def preferences_path(db_path: Path) -> Path:
    return Path(db_path).parent / FILE_NAME


def load_appearance(path: Path) -> str:
    appearance = read_preferences(path).get(APPEARANCE_KEY)

    return appearance if appearance in APPEARANCES else DEFAULT_APPEARANCE


def save_appearance(path: Path, appearance: str) -> None:
    if appearance not in APPEARANCES:
        raise ValueError(f"Unknown appearance {appearance!r}.")

    write_atomically(path, {**read_preferences(path), APPEARANCE_KEY: appearance})


def load_project(path: Path) -> str:
    project = read_preferences(path).get(PROJECT_KEY)

    return project if isinstance(project, str) else ""


def save_project(path: Path, project: str) -> None:
    write_atomically(path, {**read_preferences(path), PROJECT_KEY: project})


def load_team(path: Path, project: str) -> str:
    team = saved_teams(read_preferences(path)).get(project)

    return team if isinstance(team, str) else ""


def save_team(path: Path, project: str, team: str) -> None:
    preferences = read_preferences(path)

    write_atomically(path, {**preferences, TEAMS_KEY: {**saved_teams(preferences), project: team}})


def saved_teams(preferences: dict) -> dict:
    teams = preferences.get(TEAMS_KEY)

    return teams if isinstance(teams, dict) else {}


def read_preferences(path: Path) -> dict:
    try:
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    return loaded if isinstance(loaded, dict) else {}


def write_atomically(path: Path, preferences: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    handle, temporary = tempfile.mkstemp(prefix=".ui-", suffix=".json", dir=path.parent)

    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(preferences, file, indent=2)

        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
