from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from folderscribe.domain.interfaces import DirectoryScanner, ScanSessionRepository
from folderscribe.domain.models import (
    Compatibility,
    ExclusionRule,
    InventoryResult,
    PersistenceError,
    ScanEntry,
    ScanError,
    ScanSession,
    SessionStatus,
)


@dataclass
class ScanResult:
    inventory: InventoryResult
    session: ScanSession | None = None


class ScanFolderUseCase:
    def __init__(
        self,
        scanner: DirectoryScanner,
        repository: ScanSessionRepository | None = None,
    ) -> None:
        self._scanner = scanner
        self._repository = repository

    def execute(
        self,
        root: Path,
        exclusion_rules: tuple[ExclusionRule, ...] = (),
    ) -> ScanResult:
        if not root.exists():
            raise FileNotFoundError(f"Path does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {root}")

        session: ScanSession | None = None

        if self._repository is not None:
            session = ScanSession(
                session_id=str(uuid4()),
                root_path=root,
                started_at=datetime.now(timezone.utc),
                status=SessionStatus.RUNNING,
            )
            self._repository.create_session(session)
            self._repository.save_exclusion_rules(session.session_id, exclusion_rules)

        inventory = self._scanner.scan(root, exclusion_rules)

        if self._repository is not None and session is not None:
            session = self._save_results(session, root, inventory)

        return ScanResult(inventory=inventory, session=session)

    def _save_results(
        self,
        session: ScanSession,
        root: Path,
        inventory: InventoryResult,
    ) -> ScanSession:
        assert self._repository is not None
        try:
            entries = _map_to_entries(session.session_id, root, inventory)
            errors = [
                ScanError(
                    path=e.path,
                    code=e.code,
                    message=e.message,
                    session_id=session.session_id,
                    occurred_at=e.occurred_at or datetime.now(timezone.utc),
                )
                for e in inventory.errors
            ]
            finished_at = datetime.now(timezone.utc)
            status = (
                SessionStatus.COMPLETED_WITH_ERRORS
                if inventory.total_errors > 0
                else SessionStatus.COMPLETED
            )
            completed_session = ScanSession(
                session_id=session.session_id,
                root_path=session.root_path,
                started_at=session.started_at,
                finished_at=finished_at,
                status=status,
                is_recursive=session.is_recursive,
                total_files=inventory.total_files,
                total_compatible=len(inventory.compatible_files),
                total_not_compatible=len(inventory.not_compatible_files),
                total_skipped=inventory.total_skipped,
                total_errors=inventory.total_errors,
            )
            self._repository.complete_session(completed_session, entries, errors)
            return completed_session
        except Exception as exc:
            try:
                self._repository.mark_session_failed(
                    session.session_id,
                    datetime.now(timezone.utc),
                    str(exc),
                )
            except Exception:
                pass
            raise PersistenceError(f"Failed to persist scan session: {exc}") from exc


def _map_to_entries(
    session_id: str, root: Path, inventory: InventoryResult
) -> list[ScanEntry]:
    entries: list[ScanEntry] = []
    for f in inventory.files:
        try:
            relative = f.path.relative_to(root)
        except ValueError:
            relative = Path(f.path.name)
        entries.append(
            ScanEntry(
                session_id=session_id,
                absolute_path=f.path,
                relative_path=str(relative),
                name=f.path.name,
                extension=f.path.suffix,
                element_type="file",
                size=f.size,
                modified_at=f.modified_at,
                is_compatible=f.compatibility == Compatibility.COMPATIBLE,
                status="indexed",
            )
        )
    for s in inventory.skipped:
        try:
            relative = s.path.relative_to(root)
        except ValueError:
            relative = Path(s.path.name)
        entries.append(
            ScanEntry(
                session_id=session_id,
                absolute_path=s.path,
                relative_path=str(relative),
                name=s.path.name,
                extension=s.path.suffix,
                element_type="directory" if s.path.is_dir() else "other",
                is_compatible=False,
                status="skipped",
                skip_reason=s.reason,
                is_code_project=s.reason == "code_project",
                skip_detail=s.details,
            )
        )
    return entries
