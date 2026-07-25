import argparse
import sys
from pathlib import Path

from folderscribe.application.scan_folder import ScanFolderUseCase
from folderscribe.infrastructure.scanner import OsDirectoryScanner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="folderscribe")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Scan a folder")
    scan_parser.add_argument("path", type=str, help="Path to the folder")

    args = parser.parse_args(argv)

    if args.command is None:
        print("FolderScribe is ready.")
        return 0

    if args.command == "scan":
        root = Path(args.path)

        scanner = OsDirectoryScanner()
        use_case = ScanFolderUseCase(scanner)

        try:
            result = use_case.execute(root)
        except FileNotFoundError:
            print(f"Error: path does not exist: {root}", file=sys.stderr)
            return 2
        except NotADirectoryError:
            print(f"Error: path is not a directory: {root}", file=sys.stderr)
            return 2

        print("FolderScribe inventory")
        print(f"Root: {root}")
        print(f"Total files: {result.total_files}")
        print(f"Compatible files: {len(result.compatible_files)}")
        print(f"Unsupported files: {len(result.not_compatible_files)}")
        print(f"Skipped entries: {result.total_skipped}")
        print(f"Errors: {result.total_errors}")

        if result.compatible_files:
            print()
            for entry in result.compatible_files:
                print(f"  {entry.path.relative_to(root)}")

        if result.total_errors > 0:
            for error in result.errors:
                print(f"Error: {error.message}", file=sys.stderr)
            return 1

        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
