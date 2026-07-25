from pathlib import Path

from folderscribe.domain.interfaces import DirectoryScanner
from folderscribe.domain.models import InventoryResult


class ScanFolderUseCase:
    def __init__(self, scanner: DirectoryScanner) -> None:
        self._scanner = scanner

    def execute(self, root: Path) -> InventoryResult:
        if not root.exists():
            raise FileNotFoundError(f"Path does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {root}")
        return self._scanner.scan(root)
