import argparse
import sys
from pathlib import Path

from folderscribe.application.compute_hashes import ComputeHashesUseCase
from folderscribe.application.extract_text import ExtractTextUseCase
from folderscribe.application.scan_folder import ScanFolderUseCase
from folderscribe.domain.models import (
    ExclusionRule,
    PersistenceError,
    RuleSource,
    SessionStatus,
)
from folderscribe.infrastructure.database import (
    SchemaError,
    SqliteScanSessionRepository,
    get_default_db_path,
)
from folderscribe.infrastructure.extraction_config import ExtractionConfig
from folderscribe.infrastructure.extractors.docx_extractor import DocxTextExtractor
from folderscribe.infrastructure.extractors.pdf_extractor import PdfTextExtractor
from folderscribe.infrastructure.extractors.plain_text import PlainTextExtractor
from folderscribe.infrastructure.extractors.registry import TextExtractorRegistry
from folderscribe.infrastructure.hasher import StreamingHasher
from folderscribe.infrastructure.scanner import OsDirectoryScanner


def _run_gui() -> int:
    try:
        from folderscribe.ui.qt_app import run_gui as _run_gui_impl
    except ImportError:
        print(
            "Error: la interfaz gráfica requiere PySide6.\n"
            "  pip install folderscribe[gui]",
            file=sys.stderr,
        )
        return 4
    return _run_gui_impl()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="folderscribe")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan a folder",
        description=(
            "Scan a folder: inventory, fingerprints, duplicates, text extraction, "
            "and optional OCR. "
            "FolderScribe never moves, renames, deletes, or modifies files. "
            "It only reads and analyzes."
        ),
    )
    scan_parser.add_argument("path", type=str, help="Path to the folder")
    scan_parser.add_argument(
        "--no-hash",
        action="store_true",
        default=False,
        help="Skip fingerprint (SHA-256) calculation and duplicate detection",
    )
    scan_parser.add_argument(
        "--no-text",
        action="store_true",
        default=False,
        help="Skip text extraction",
    )
    scan_parser.add_argument(
        "--ocr-mode",
        type=str,
        choices=["fast", "full"],
        default=None,
        help=(
            "Run OCR on scanned PDFs after text extraction "
            "(requires tesseract-ocr installed)"
        ),
    )
    scan_parser.add_argument(
        "--database",
        type=str,
        default=None,
        help="Path to the SQLite database (default: XDG data home / folderscribe.db)",
    )
    scan_parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        dest="exclude_patterns",
        help=(
            "Pattern to exclude (can be repeated). "
            "Patterns without '/' match filenames at any depth. "
            "Patterns with '/' match relative paths. "
            "Matching is case-sensitive."
        ),
    )

    _ = subparsers.add_parser("gui", help="Launch graphical interface")

    args = parser.parse_args(argv)

    if args.command is None:
        print("FolderScribe is ready.")
        return 0

    if args.command == "gui":
        return _run_gui()

    if args.command == "scan":
        root = Path(args.path)

        exclusion_rules: tuple[ExclusionRule, ...] = ()
        if args.exclude_patterns:
            for pattern in args.exclude_patterns:
                if not pattern:
                    print("Error: --exclude pattern cannot be empty.", file=sys.stderr)
                    return 2
                if pattern.startswith("/"):
                    msg = (
                        "Error: --exclude pattern cannot be"
                        f" an absolute path: {pattern}"
                    )
                    print(msg, file=sys.stderr)
                    return 2
            exclusion_rules = tuple(
                ExclusionRule(pattern=p, source=RuleSource.USER)
                for p in args.exclude_patterns
            )

        scanner = OsDirectoryScanner()

        if args.database is not None:
            db_path = Path(args.database)
        else:
            db_path = get_default_db_path()

        try:
            repository = SqliteScanSessionRepository(db_path)
        except SchemaError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 3

        use_case = ScanFolderUseCase(scanner, repository)

        try:
            result = use_case.execute(root, exclusion_rules)
        except FileNotFoundError:
            print(f"Error: path does not exist: {root}", file=sys.stderr)
            repository.close()
            return 2
        except NotADirectoryError:
            print(f"Error: path is not a directory: {root}", file=sys.stderr)
            repository.close()
            return 2
        except PersistenceError as e:
            print(f"Error: {e}", file=sys.stderr)
            repository.close()
            return 3

        inventory = result.inventory
        session_id = result.session.session_id if result.session else None

        print("FolderScribe scan")
        print(
            "FolderScribe only reads and analyzes files. "
            "No files are moved, renamed, deleted, or modified."
        )
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

        if session_id is not None and result.session is not None:
            print()
            status_text = _session_status_text(result.session.status)
            print(f"Session: {session_id} ({status_text})")
            print(f"Database: {db_path}")
            if result.session.status in (
                SessionStatus.COMPLETED,
                SessionStatus.COMPLETED_WITH_ERRORS,
            ):
                stored = inventory.total_files + inventory.total_skipped
                print(f"Entries stored: {stored}")
                print(f"Errors recorded: {inventory.total_errors}")

            if not args.no_hash:
                print()
                print("Calculating fingerprints (SHA-256)…")
                hasher = StreamingHasher()
                hash_use_case = ComputeHashesUseCase(hasher, repository)
                hash_result = hash_use_case.execute(session_id)
                print(f"  Computed: {hash_result.computed_count}")
                print(f"  Reused: {hash_result.reused_count}")
                print(f"  Skipped: {hash_result.skipped_count}")
                print(f"  Errors: {hash_result.error_count}")
                if len(hash_result.duplicate_groups) > 0:
                    print(f"  Duplicate groups: {len(hash_result.duplicate_groups)}")
                    for g in hash_result.duplicate_groups:
                        sz = g.file_size
                        print(
                            f"    {g.hash_sha256[:16]} "
                            f"({g.file_count} files, {sz} bytes each)"
                        )
                else:
                    print("  No duplicates found.")
            else:
                print()
                print("Fingerprint calculation skipped (--no-hash).")
                print("Duplicate detection not performed.")

            if not args.no_text:
                print()
                print("Extracting text…")
                registry = TextExtractorRegistry()
                registry.register(PlainTextExtractor())
                registry.register(DocxTextExtractor())
                registry.register(PdfTextExtractor())
                text_use_case = ExtractTextUseCase(
                    registry=registry,
                    repository=repository,
                    config=ExtractionConfig(),
                )
                text_result = text_use_case.execute(session_id)
                print(f"  Extracted: {text_result.extracted_count}")
                print(f"  Reused: {text_result.reused_count}")
                print(f"  Partial: {text_result.partial_count}")
                print(f"  Needs OCR: {text_result.needs_ocr_count}")
                print(f"  Skipped: {text_result.skipped_count}")
                print(f"  Errors: {text_result.error_count}")
            else:
                print()
                print("Text extraction skipped (--no-text).")

            if args.ocr_mode is not None:
                print()
                if args.no_text:
                    print("OCR skipped (--no-text).")
                else:
                    from folderscribe.application.ocr_text import OcrTextUseCase
                    from folderscribe.domain.ocr import OcrMode
                    from folderscribe.infrastructure.ocr import (
                        TesseractOcrEngine,
                    )

                    print(f"Running OCR ({args.ocr_mode})…")
                    ocr_use_case = OcrTextUseCase(
                        engine=TesseractOcrEngine(),
                        repository=repository,
                        config=ExtractionConfig(),
                    )
                    ocr_result = ocr_use_case.execute(
                        session_id,
                        mode=OcrMode(args.ocr_mode),
                    )
                    if not ocr_result.engine_available:
                        print(
                            "  OCR engine not available. Install tesseract-ocr:"
                            " sudo apt install tesseract-ocr tesseract-ocr-spa"
                        )
                    else:
                        print(f"  OCR complete: {ocr_result.ocr_count}")
                        print(f"  Reused: {ocr_result.reused_count}")
                        print(f"  Partial: {ocr_result.partial_count}")
                        print(f"  Skipped: {ocr_result.skipped_count}")
                        print(f"  Errors: {ocr_result.error_count}")

        repository.close()

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
