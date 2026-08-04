from PySide6.QtCore import Qt

from folderscribe.ui.table_model import ScanFilterProxyModel, ScanTableModel
from folderscribe.ui.view_model import DisplayRow


def make_row(
    name: str = "file.txt",
    status: str = "indexed",
    skip_reason: str | None = None,
    is_compatible: bool = True,
    element_type: str = "file",
    size: int | None = 100,
) -> DisplayRow:
    return DisplayRow(
        name=name,
        relative_path=name,
        status=status,
        skip_reason=skip_reason,
        skip_detail="",
        element_type=element_type,
        size=size,
        is_compatible=is_compatible,
    )


class TestScanTableModel:
    def test_empty_model(self) -> None:
        model = ScanTableModel()
        assert model.rowCount() == 0
        assert model.columnCount() == 14

    def test_column_names(self) -> None:
        model = ScanTableModel()
        assert model.headerData(0, Qt.Orientation.Horizontal) == "Nombre"
        assert model.headerData(1, Qt.Orientation.Horizontal) == "Ruta relativa"
        assert model.headerData(2, Qt.Orientation.Horizontal) == "Estado"
        assert model.headerData(6, Qt.Orientation.Horizontal) == "Tamaño"

    def test_set_rows(self) -> None:
        model = ScanTableModel()
        rows = [make_row(name="a.txt"), make_row(name="b.pdf")]
        model.set_rows(rows)
        assert model.rowCount() == 2

    def test_data_display(self) -> None:
        model = ScanTableModel()
        rows = [make_row(name="doc.pdf", status="indexed")]
        model.set_rows(rows)
        idx0 = model.index(0, 0)
        idx2 = model.index(0, 2)
        assert model.data(idx0) == "doc.pdf"
        assert model.data(idx2) == "indexed"

    def test_size_formatting(self) -> None:
        model = ScanTableModel()
        rows = [make_row(size=2048)]
        model.set_rows(rows)
        idx = model.index(0, 6)
        size_text = model.data(idx)
        assert isinstance(size_text, str)
        assert "2" in size_text
        assert "KB" in size_text

    def test_null_size(self) -> None:
        model = ScanTableModel()
        rows = [make_row(size=None)]
        model.set_rows(rows)
        idx = model.index(0, 6)
        assert model.data(idx) == ""


class TestScanFilterProxyModel:
    def test_all_passes_everything(self) -> None:
        model = ScanTableModel()
        proxy = ScanFilterProxyModel()
        proxy.setSourceModel(model)

        rows = [
            make_row(name="a.txt", status="indexed"),
            make_row(name="b.jpg", status="skipped"),
        ]
        model.set_rows(rows)

        proxy.set_filter_mode(ScanFilterProxyModel.FILTER_ALL)
        assert proxy.rowCount() == 2

    def test_compatible_filter(self) -> None:
        model = ScanTableModel()
        proxy = ScanFilterProxyModel()
        proxy.setSourceModel(model)

        rows = [
            make_row(name="compatible.pdf", is_compatible=True),
            make_row(name="not.jpg", is_compatible=False),
        ]
        model.set_rows(rows)

        proxy.set_filter_mode(ScanFilterProxyModel.FILTER_COMPATIBLE)
        assert proxy.rowCount() == 1
        idx = proxy.index(0, 0)
        assert proxy.data(idx) == "compatible.pdf"

    def test_not_compatible_filter(self) -> None:
        model = ScanTableModel()
        proxy = ScanFilterProxyModel()
        proxy.setSourceModel(model)

        rows = [
            make_row(name="compatible.pdf", is_compatible=True),
            make_row(name="not.jpg", is_compatible=False),
        ]
        model.set_rows(rows)

        proxy.set_filter_mode(ScanFilterProxyModel.FILTER_NOT_COMPATIBLE)
        assert proxy.rowCount() == 1
        idx = proxy.index(0, 0)
        assert proxy.data(idx) == "not.jpg"

    def test_skipped_filter(self) -> None:
        model = ScanTableModel()
        proxy = ScanFilterProxyModel()
        proxy.setSourceModel(model)

        rows = [
            make_row(name="indexed.txt", status="indexed"),
            make_row(name="skipped.link", status="skipped"),
        ]
        model.set_rows(rows)

        proxy.set_filter_mode(ScanFilterProxyModel.FILTER_SKIPPED)
        assert proxy.rowCount() == 1
        idx = proxy.index(0, 0)
        assert proxy.data(idx) == "skipped.link"

    def test_indexed_filter(self) -> None:
        model = ScanTableModel()
        proxy = ScanFilterProxyModel()
        proxy.setSourceModel(model)

        rows = [
            make_row(name="indexed.txt", status="indexed"),
            make_row(name="skipped.link", status="skipped"),
        ]
        model.set_rows(rows)

        proxy.set_filter_mode(ScanFilterProxyModel.FILTER_INDEXED)
        assert proxy.rowCount() == 1

    def test_excluded_filter(self) -> None:
        model = ScanTableModel()
        proxy = ScanFilterProxyModel()
        proxy.setSourceModel(model)

        rows = [
            make_row(name="normal.txt", status="indexed"),
            make_row(
                name="secret.tmp",
                status="skipped",
                skip_reason="excluded_by_user_pattern",
            ),
            make_row(name="link", status="skipped", skip_reason="symlink"),
        ]
        model.set_rows(rows)

        proxy.set_filter_mode(ScanFilterProxyModel.FILTER_EXCLUDED)
        assert proxy.rowCount() == 1
        idx = proxy.index(0, 0)
        assert proxy.data(idx) == "secret.tmp"

    def test_empty_model_after_filter(self) -> None:
        model = ScanTableModel()
        proxy = ScanFilterProxyModel()
        proxy.setSourceModel(model)

        proxy.set_filter_mode(ScanFilterProxyModel.FILTER_SKIPPED)
        assert proxy.rowCount() == 0
