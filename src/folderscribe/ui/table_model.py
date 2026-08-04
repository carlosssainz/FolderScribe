from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtCore import QAbstractTableModel
from PySide6.QtCore import QObject

from folderscribe.ui.view_model import DisplayRow


class ScanTableModel(QAbstractTableModel):
    COLUMNS = [
        "Nombre",
        "Ruta relativa",
        "Estado",
        "Motivo",
        "Detalle",
        "Tipo",
        "Tamaño",
        "Huella",
        "Hash status",
        "Extracción",
        "Caracteres",
        "Páginas",
        "Truncado",
        "Needs OCR",
    ]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[DisplayRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        return len(self.COLUMNS)

    def data(  # type: ignore[override]
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._format(row, col)
        if role == Qt.ItemDataRole.UserRole:
            return self._sort_value(row, col)

        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
        ):
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        return None

    def _format(self, row: DisplayRow, col: int) -> str:
        if col == 0:
            return row.name
        if col == 1:
            return row.relative_path
        if col == 2:
            return row.status
        if col == 3:
            return row.skip_reason or ""
        if col == 4:
            return row.skip_detail
        if col == 5:
            return row.element_type
        if col == 6:
            if row.size is None:
                return ""
            return self._format_size(row.size)
        if col == 7:
            return row.hash_value
        if col == 8:
            return row.hash_status
        if col == 9:
            return row.extraction_status
        if col == 10:
            return str(row.extraction_chars) if row.extraction_chars else ""
        if col == 11:
            return str(row.extraction_pages) if row.extraction_pages else ""
        if col == 12:
            return "Sí" if row.extraction_truncated else ""
        if col == 13:
            return "Sí" if row.extraction_needs_ocr else ""
        return ""

    def _sort_value(self, row: DisplayRow, col: int) -> object:
        if col == 6:
            return row.size if row.size is not None else -1
        if col == 10:
            return row.extraction_chars
        return self._format(row, col)

    def _format_size(self, size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
            size //= 1024
        return f"{size:.1f} TB"

    def set_rows(self, rows: list[DisplayRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rows(self) -> list[DisplayRow]:
        return list(self._rows)


class ScanFilterProxyModel(QSortFilterProxyModel):
    FILTER_ALL = "todos"
    FILTER_COMPATIBLE = "compatible"
    FILTER_NOT_COMPATIBLE = "no_compatible"
    FILTER_INDEXED = "indexado"
    FILTER_SKIPPED = "omitido"
    FILTER_EXCLUDED = "excluido"
    FILTER_DUPLICATES = "duplicados"

    FILTER_EXTRACTED = "extraído"
    FILTER_NEEDS_OCR = "needs_ocr"
    FILTER_PARTIAL = "parcial"

    FILTER_OPTIONS = [
        FILTER_ALL,
        FILTER_COMPATIBLE,
        FILTER_NOT_COMPATIBLE,
        FILTER_INDEXED,
        FILTER_SKIPPED,
        FILTER_EXCLUDED,
        FILTER_DUPLICATES,
        FILTER_EXTRACTED,
        FILTER_NEEDS_OCR,
        FILTER_PARTIAL,
    ]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._filter_mode: str = self.FILTER_ALL

    def set_filter_mode(self, mode: str) -> None:
        self._filter_mode = mode
        self.invalidateFilter()

    def filterAcceptsRow(  # type: ignore[override]
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        rows = model.rows() if hasattr(model, "rows") else []
        if source_row < 0 or source_row >= len(rows):
            return True
        row = rows[source_row]

        if self._filter_mode == self.FILTER_ALL:
            return True
        if self._filter_mode == self.FILTER_COMPATIBLE:
            return bool(row.status == "indexed" and row.is_compatible)
        if self._filter_mode == self.FILTER_NOT_COMPATIBLE:
            return bool(row.status == "indexed" and not row.is_compatible)
        if self._filter_mode == self.FILTER_INDEXED:
            return bool(row.status == "indexed")
        if self._filter_mode == self.FILTER_SKIPPED:
            return bool(row.status == "skipped")
        if self._filter_mode == self.FILTER_EXCLUDED:
            return bool(row.skip_reason == "excluded_by_user_pattern")
        if self._filter_mode == self.FILTER_DUPLICATES:
            return bool(
                row.hash_status in ("computed", "reused") and row.hash_value != ""
            )
        if self._filter_mode == self.FILTER_EXTRACTED:
            return bool(
                row.extraction_status in ("extracted", "extracted_empty")
                and row.is_compatible
            )
        if self._filter_mode == self.FILTER_NEEDS_OCR:
            return bool(row.extraction_status == "needs_ocr")
        if self._filter_mode == self.FILTER_PARTIAL:
            return bool(row.extraction_status == "partial")

        return True
