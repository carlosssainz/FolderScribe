from pathlib import Path

from folderscribe.infrastructure.database import get_default_db_path


def resolve_db_path(db_path: Path | None = None) -> Path:
    if db_path is None:
        return get_default_db_path()
    return db_path
