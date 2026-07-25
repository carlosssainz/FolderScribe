from abc import ABC, abstractmethod
from pathlib import Path

from folderscribe.domain.models import InventoryResult


class DirectoryScanner(ABC):
    @abstractmethod
    def scan(self, root: Path) -> InventoryResult: ...
