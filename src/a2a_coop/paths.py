import os
from pathlib import Path

DB_ENV_VAR = "A2A_COOP_DB"


def default_db_path() -> Path:
    override = os.environ.get(DB_ENV_VAR)

    if override:
        return Path(override).expanduser()

    return Path.home() / ".a2a_coop" / "coop.db"
