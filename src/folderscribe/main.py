import argparse
import sys
from pathlib import Path

from folderscribe.application.scan_folder import ScanFolderUseCase
from folderscribe.domain.models import PersistenceError, SessionStatus
from folderscribe.infrastructure.database import (
    SqliteScanSessionRepository,
    get_default_db_path,
)
from folderscribe.infrastructure.scanner import OsDirectoryScanner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="folderscribe")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Scan a folder")
    scan_parser.add_argument("path", type=str, help="Path to the folder")
    scan_parser.add_argument(
        "--database",
        type=str,
        default=None,
        help="Path to the SQLite database (default: XDG data home / folderscribe.db)",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        print("FolderScribe is ready.")
        return 0

    if args.command == "scan":
        root = Path(args.path)

        scanner = OsDirectoryScanner()

        if args.database is not None:
            db_path = Path(args.database)
        else:
            db_path = get_default_db_path()

        repository = SqliteScanSessionRepository(db_path)
        use_case = ScanFolderUseCase(scanner, repository)

        try:
            result = use_case.execute(root)
        except FileNotFoundError:
            print(f"Error: path does not exist: {root}", file=sys.stderr)
            return 2
        except NotADirectoryError:
            print(f"Error: path is not a directory: {root}", file=sys.stderr)
            return 2
        except PersistenceError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 3
        finally:
            repository.close()

        inventory = result.inventory

        print("FolderScribe inventory")
        print(f"Root: {root}")
        print(f"Total files: {inventory.total_files}")
        print(f"Compatible files: {len(inventory.compatible_files)}")
        print(f"Unsupported files: {len(inventory.not_compatible_files)}")
        print(f"Skipped entries: {inventory.total_skipped}")
        print(f"Errors: {inventory.total_errors}")

        if inventory.compatible_files:
            print()
            for entry in inventory.compatible_files:
                print(f"  {entry.path.relative_to(root)}")

        if result.session is not None:
            print()
            status_text = _session_status_text(result.session.status)
            print(f"Session: {result.session.session_id} ({status_text})")
            print(f"Database: {db_path}")
            if result.session.status in (
                SessionStatus.COMPLETED,
                SessionStatus.COMPLETED_WITH_ERRORS,
            ):
                stored = inventory.total_files + inventory.total_skipped
                print(f"Entries stored: {stored}")
                print(f"Errors recorded: {inventory.total_errors}")

        if inventory.total_errors > 0:
            for error in inventory.errors:
                print(f"Error: {error.message}", file=sys.stderr)
            return 1

        return 0

    return 0


def _session_status_text(status: SessionStatus) -> str:
    mapping = {
        SessionStatus.COMPLETED: "saved",
        SessionStatus.COMPLETED_WITH_ERRORS: "saved with errors",
        SessionStatus.FAILED: "failed",
        SessionStatus.RUNNING: "running",
        SessionStatus.CANCELLED: "cancelled",
    }
    return mapping.get(status, status.value)


if __name__ == "__main__":
    sys.exit(main())
