from pathlib import Path
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from folderscribe.domain.models import ExclusionRule, RuleSource
from folderscribe.domain.ocr import OcrMode
from folderscribe.ui.composition import resolve_db_path
from folderscribe.ui.extract_worker import ExtractWorker
from folderscribe.ui.hash_worker import HashWorker
from folderscribe.ui.ocr_worker import OcrWorker
from folderscribe.ui.scan_worker import ScanWorker
from folderscribe.ui.table_model import ScanFilterProxyModel, ScanTableModel
from folderscribe.ui.view_model import DisplayRow, ViewModel

_DUPLICATE_HEADERS = [
    "Grupo",
    "Hash",
    "Tamaño",
    "Archivos",
    "Espacio redundante",
    "Rutas",
]


class MainWindow(QMainWindow):
    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("FolderScribe Scan")
        self.resize(1100, 700)

        self._worker: ScanWorker | None = None
        self._hash_worker: HashWorker | None = None
        self._extract_worker: ExtractWorker | None = None
        self._ocr_worker: OcrWorker | None = None
        self._session_id: str | None = None
        self._thread: Any = None
        self._db_path = resolve_db_path(db_path)
        self._view_model: ViewModel | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addLayout(self._build_source_group())
        layout.addLayout(self._build_db_group())
        layout.addLayout(self._build_exclusion_group())
        layout.addLayout(self._build_action_group())
        self._warning_label = QLabel(
            "FolderScribe solo analizará e indexará los archivos. "
            "No moverá, renombrará ni eliminará ningún elemento."
        )
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet(
            "color: #666; font-style: italic; padding: 4px;"
        )
        layout.addWidget(self._warning_label)
        layout.addWidget(self._build_splitter())

    def _build_source_group(self) -> QHBoxLayout:
        row = QHBoxLayout()
        lbl = QLabel("Carpeta origen:")
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("/home/usuario/Descargas")
        self._path_edit.setMinimumWidth(300)
        browse_btn = QPushButton("Examinar…")
        browse_btn.clicked.connect(self._browse_source)
        row.addWidget(lbl)
        row.addWidget(self._path_edit, 1)
        row.addWidget(browse_btn)
        return row

    def _build_db_group(self) -> QHBoxLayout:
        row = QHBoxLayout()
        lbl = QLabel("Base de datos:")
        self._db_path_edit = QLineEdit()
        self._db_path_edit.setReadOnly(True)
        self._db_path_edit.setText(str(self._db_path))
        row.addWidget(lbl)
        row.addWidget(self._db_path_edit, 1)
        return row

    def _build_exclusion_group(self) -> QVBoxLayout:
        group = QVBoxLayout()
        input_row = QHBoxLayout()
        self._exclude_edit = QLineEdit()
        self._exclude_edit.setPlaceholderText("*.tmp")
        self._exclude_edit.returnPressed.connect(self._add_exclusion)
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(32)
        add_btn.setToolTip("Añadir patrón de exclusión")
        add_btn.clicked.connect(self._add_exclusion)
        input_row.addWidget(QLabel("Excluir patrón:"))
        input_row.addWidget(self._exclude_edit, 1)
        input_row.addWidget(add_btn)
        group.addLayout(input_row)

        self._exclude_list = QListWidget()
        self._exclude_list.setMaximumHeight(100)
        group.addWidget(self._exclude_list)
        return group

    def _build_action_group(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._scan_btn = QPushButton("Escanear")
        self._scan_btn.clicked.connect(self._start_scan)

        self._hash_btn = QPushButton("Calcular huellas")
        self._hash_btn.setEnabled(False)
        self._hash_btn.clicked.connect(self._start_hashing)

        self._extract_btn = QPushButton("Extraer texto")
        self._extract_btn.setEnabled(False)
        self._extract_btn.clicked.connect(self._start_extraction)

        self._ocr_btn = QPushButton("OCR")
        self._ocr_btn.setEnabled(False)
        self._ocr_btn.setToolTip("OCR para PDFs escaneados")
        self._ocr_btn.clicked.connect(self._start_ocr)

        self._ocr_mode_combo = QComboBox()
        self._ocr_mode_combo.setEnabled(False)
        self._ocr_mode_combo.addItem("Rápido", OcrMode.FAST)
        self._ocr_mode_combo.addItem("Completo", OcrMode.FULL)
        self._ocr_mode_combo.setToolTip(
            "Rápido: 150 DPI. Completo: 300 DPI (más lento, más preciso)."
        )

        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel_operation)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFixedWidth(160)
        self._progress_bar.hide()

        self._status_label = QLabel()
        row.addWidget(self._scan_btn)
        row.addWidget(self._hash_btn)
        row.addWidget(self._extract_btn)
        row.addWidget(self._ocr_btn)
        row.addWidget(self._ocr_mode_combo)
        row.addWidget(self._cancel_btn)
        row.addWidget(self._progress_bar)
        row.addWidget(self._status_label, 1)
        return row

    def _build_splitter(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Vertical)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self._summary_label = QLabel()
        top_layout.addWidget(self._summary_label)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtro:"))
        self._filter_combo = QComboBox()
        for opt in ScanFilterProxyModel.FILTER_OPTIONS:
            self._filter_combo.addItem(opt, opt)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._filter_combo)
        filter_row.addStretch()
        top_layout.addLayout(filter_row)

        self._table_model = ScanTableModel()
        self._proxy_model = ScanFilterProxyModel()
        self._proxy_model.setSourceModel(self._table_model)
        self._table_view = QTableView()
        self._table_view.setModel(self._proxy_model)
        self._table_view.setSortingEnabled(True)
        self._table_view.setAlternatingRowColors(True)
        self._table_view.horizontalHeader().setStretchLastSection(True)
        self._table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        top_layout.addWidget(self._table_view)
        splitter.addWidget(top)

        self._error_tab = QPlainTextEdit()
        self._error_tab.setReadOnly(True)
        self._error_tab.setPlaceholderText("No hay errores.")
        self._error_tab.setMaximumBlockCount(1000)

        self._duplicate_table = QTableView()
        self._duplicate_table.setSortingEnabled(True)
        self._duplicate_table.setAlternatingRowColors(True)
        self._duplicate_table.horizontalHeader().setStretchLastSection(True)
        self._duplicate_model = _DuplicateTableModel()
        self._duplicate_table.setModel(self._duplicate_model)

        self._content_panel = QPlainTextEdit()
        self._content_panel.setReadOnly(True)
        self._content_panel.setPlaceholderText(
            "Selecciona un archivo compatible para ver su contenido extraído."
        )
        self._content_panel.setMaximumBlockCount(1000)

        tabs = QTabWidget()
        tabs.addTab(self._table_view, "Resultados")
        tabs.addTab(self._duplicate_table, "Duplicados")
        tabs.addTab(self._content_panel, "Contenido")
        tabs.addTab(self._error_tab, "Errores")

        self._table_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        splitter.addWidget(tabs)

        return splitter

    def _browse_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta")
        if path:
            self._path_edit.setText(path)

    def _add_exclusion(self) -> None:
        pattern = self._exclude_edit.text().strip()
        if not pattern:
            return
        try:
            ExclusionRule(pattern=pattern, source=RuleSource.USER)
        except Exception:
            return
        item = QListWidgetItem(pattern)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        btn = QPushButton("×")
        btn.setFixedWidth(24)
        btn.clicked.connect(lambda: self._remove_exclusion(item))
        self._exclude_list.addItem(item)
        self._exclude_list.setItemWidget(item, btn)
        self._exclude_edit.clear()

    def _remove_exclusion(self, item: QListWidgetItem) -> None:
        row = self._exclude_list.row(item)
        self._exclude_list.takeItem(row)

    def _collect_exclusions(self) -> tuple[ExclusionRule, ...]:
        rules: list[ExclusionRule] = []
        for i in range(self._exclude_list.count()):
            item = self._exclude_list.item(i)
            if item:
                rules.append(ExclusionRule(pattern=item.text(), source=RuleSource.USER))
        return tuple(rules)

    def _flush_pending_exclusion(self) -> None:
        text = self._exclude_edit.text().strip()
        if text:
            self._exclude_edit.setText(text)
            self._add_exclusion()

    def _start_scan(self) -> None:
        if self._worker is not None:
            return

        path_text = self._path_edit.text().strip()
        if not path_text:
            self._status_label.setText("Selecciona una carpeta origen.")
            return

        root = Path(path_text)
        if not root.exists():
            self._status_label.setText("La carpeta no existe.")
            return
        if not root.is_dir():
            self._status_label.setText("La ruta no es un directorio.")
            return

        self._flush_pending_exclusion()
        exclusion_rules = self._collect_exclusions()

        self._scan_btn.setEnabled(False)
        self._hash_btn.setEnabled(False)
        self._extract_btn.setEnabled(False)
        self._ocr_btn.setEnabled(False)
        self._ocr_mode_combo.setEnabled(False)
        self._progress_bar.show()
        self._progress_bar.setRange(0, 0)
        self._status_label.setText("Analizando…")
        self._summary_label.setText("")
        self._table_model.set_rows([])
        self._error_tab.clear()
        self._duplicate_model.set_rows([])
        self._session_id = None

        self._worker = ScanWorker(
            root=root,
            database_path=self._db_path,
            exclusion_rules=exclusion_rules,
        )
        self._worker.scan_finished.connect(self._on_scan_finished)
        self._worker.scan_failed.connect(self._on_scan_failed)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _on_scan_finished(self, result: object) -> None:
        from folderscribe.application.scan_folder import ScanResult

        assert isinstance(result, ScanResult)
        self._view_model = ViewModel.from_inventory(result.inventory)
        self._table_model.set_rows(self._view_model.rows)
        self._update_summary()
        self._update_errors()
        self._session_id = result.session.session_id if result.session else None
        status = "Completado"
        if result.session and result.session.status.value == "completed_with_errors":
            status = "Completado con errores"
        self._status_label.setText(status)
        self._hash_btn.setEnabled(self._session_id is not None)
        self._extract_btn.setEnabled(self._session_id is not None)
        self._ocr_btn.setEnabled(self._session_id is not None)
        self._ocr_mode_combo.setEnabled(self._session_id is not None)

    def _on_scan_failed(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self._scan_btn.setEnabled(True)
        self._progress_bar.hide()

    def _start_hashing(self) -> None:
        if self._hash_worker is not None:
            return
        if self._session_id is None:
            return

        self._hash_btn.setEnabled(False)
        self._scan_btn.setEnabled(False)
        self._extract_btn.setEnabled(False)
        self._ocr_btn.setEnabled(False)
        self._ocr_mode_combo.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.show()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._status_label.setText("Calculando huellas…")

        self._hash_worker = HashWorker(
            session_id=self._session_id,
            database_path=self._db_path,
        )
        self._hash_worker.progress_changed.connect(self._on_hash_progress)
        self._hash_worker.stage_changed.connect(self._on_hash_stage)
        self._hash_worker.hash_finished.connect(self._on_hash_finished)
        self._hash_worker.hash_failed.connect(self._on_hash_failed)
        self._hash_worker.finished.connect(self._cleanup_hash_worker)
        self._hash_worker.start()

    def _cancel_hashing(self) -> None:
        self._cancel_operation()
        if self._hash_worker is not None:
            self._hash_worker.request_cancel()
            self._status_label.setText("Cancelando…")

    def _on_hash_progress(self, current: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(current)

    def _on_hash_stage(self, stage: str) -> None:
        self._status_label.setText(stage)

    def _on_hash_finished(self, result: object) -> None:
        from folderscribe.domain.hashing import HashResult

        assert isinstance(result, HashResult)
        if self._view_model is not None:
            self._view_model.apply_hash_result(result)
            self._table_model.set_rows(self._view_model.rows)
            self._duplicate_model.set_rows(self._view_model.duplicate_groups)

        parts = []
        if self._view_model is not None:
            total = self._view_model.total_files + self._view_model.total_skipped
            parts.append(f"Total: {total}")
            parts.append(f"Indexados: {self._view_model.total_indexed}")
            parts.append(f"Compatibles: {self._view_model.total_compatible}")
            parts.append(f"No compatibles: {self._view_model.total_not_compatible}")
            parts.append(f"Omitidos: {self._view_model.total_skipped}")
            parts.append(f"Errores: {self._view_model.total_errors}")
        parts.append(f"Huellas calculadas: {result.computed_count}")
        parts.append(f"Huellas reutilizadas: {result.reused_count}")
        parts.append(f"Duplicados: {len(result.duplicate_groups)} grupos")
        self._summary_label.setText(" | ".join(parts))

        self._status_label.setText(
            f"Huellas completadas. {result.computed_count} calculadas, "
            f"{result.reused_count} reutilizadas."
        )

    def _on_hash_failed(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _on_selection_changed(self) -> None:
        if self._view_model is None:
            return
        indexes = self._table_view.selectedIndexes()
        if not indexes:
            self._content_panel.clear()
            self._content_panel.setPlaceholderText(
                "Selecciona un archivo compatible para ver su contenido extraído."
            )
            return
        proxy_index = indexes[0]
        source_index = self._proxy_model.mapToSource(proxy_index)
        row_idx = source_index.row()
        if row_idx < 0 or row_idx >= len(self._view_model.rows):
            return
        row = self._view_model.rows[row_idx]
        status = row.extraction_status
        if not status:
            self._content_panel.setPlainText(
                "Este archivo no ha sido procesado para extracción de texto."
            )
            return
        if status == "skipped_privacy":
            self._content_panel.setPlainText(
                "Contenido omitido por política de privacidad."
            )
            return
        if status == "unsupported":
            self._content_panel.setPlainText(
                "Formato no compatible para extracción de texto."
            )
            return
        if status == "encrypted":
            self._content_panel.setPlainText(
                "El archivo PDF está cifrado. No se pudo extraer texto."
            )
            return
        if status == "needs_ocr":
            self._content_panel.setPlainText(
                "El archivo parece ser un PDF escaneado sin capa de texto.\n"
                "Pulsa el botón 'OCR' para extraer su contenido."
            )
            return
        if status == "error":
            err = row.extraction_error or "Error desconocido"
            self._content_panel.setPlainText(f"Error de extracción: {err}")
            return
        if status in ("extracted", "extracted_empty", "partial"):
            self._load_content_from_db(row)
            return
        self._content_panel.setPlainText(f"Estado: {status}")

    def _load_content_from_db(self, row: DisplayRow) -> None:
        from folderscribe.infrastructure.database import SqliteScanSessionRepository

        if self._session_id is None:
            return
        try:
            repo = SqliteScanSessionRepository(self._db_path)
            try:
                extraction = repo.get_text_extraction_by_path(
                    self._session_id, Path(row.absolute_path)
                )
                if extraction is not None and extraction.content is not None:
                    preview = extraction.content[:5000]
                    if len(extraction.content) > 5000:
                        preview += "\n\n[... contenido truncado a 5.000 caracteres ...]"
                    self._content_panel.setPlainText(preview)
                else:
                    self._content_panel.setPlainText(
                        "No hay contenido extraído disponible."
                    )
            finally:
                repo.close()
        except Exception:
            self._content_panel.setPlainText(
                "Error al cargar el contenido desde la base de datos."
            )

    def _start_extraction(self) -> None:
        if self._extract_worker is not None:
            return
        if self._session_id is None:
            return

        self._extract_btn.setEnabled(False)
        self._hash_btn.setEnabled(False)
        self._scan_btn.setEnabled(False)
        self._ocr_btn.setEnabled(False)
        self._ocr_mode_combo.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.show()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._status_label.setText("Extrayendo texto…")

        self._extract_worker = ExtractWorker(
            session_id=self._session_id,
            database_path=self._db_path,
        )
        self._extract_worker.progress_changed.connect(self._on_extract_progress)
        self._extract_worker.stage_changed.connect(self._on_extract_stage)
        self._extract_worker.extract_finished.connect(self._on_extract_finished)
        self._extract_worker.extract_failed.connect(self._on_extract_failed)
        self._extract_worker.finished.connect(self._cleanup_extract_worker)
        self._extract_worker.start()

    def _start_ocr(self) -> None:
        if self._ocr_worker is not None:
            return
        if self._session_id is None:
            return

        mode = self._ocr_mode_combo.currentData()
        if not isinstance(mode, OcrMode):
            mode = OcrMode.FAST

        self._ocr_btn.setEnabled(False)
        self._ocr_mode_combo.setEnabled(False)
        self._extract_btn.setEnabled(False)
        self._hash_btn.setEnabled(False)
        self._scan_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.show()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._status_label.setText(
            f"Ejecutando OCR ({'rápido' if mode == OcrMode.FAST else 'completo'})…"
        )

        self._ocr_worker = OcrWorker(
            session_id=self._session_id,
            database_path=self._db_path,
            mode=mode,
        )
        self._ocr_worker.progress_changed.connect(self._on_extract_progress)
        self._ocr_worker.stage_changed.connect(self._on_extract_stage)
        self._ocr_worker.ocr_finished.connect(self._on_ocr_finished)
        self._ocr_worker.ocr_failed.connect(self._on_ocr_failed)
        self._ocr_worker.finished.connect(self._cleanup_ocr_worker)
        self._ocr_worker.start()

    def _on_ocr_finished(self, result: object) -> None:
        from folderscribe.domain.ocr import OcrResult

        assert isinstance(result, OcrResult)
        if self._view_model is not None:
            self._view_model.apply_ocr_result(result)
            self._table_model.set_rows(self._view_model.rows)

        parts = []
        if self._view_model is not None:
            total = self._view_model.total_files + self._view_model.total_skipped
            parts.append(f"Total: {total}")
            parts.append(f"Indexados: {self._view_model.total_indexed}")
            parts.append(f"Compatibles: {self._view_model.total_compatible}")
            parts.append(f"No compatibles: {self._view_model.total_not_compatible}")
            parts.append(f"Omitidos: {self._view_model.total_skipped}")
            parts.append(f"Errores: {self._view_model.total_errors}")
        parts.append(f"OCR: {result.ocr_count}")
        parts.append(f"Reutilizados: {result.reused_count}")
        parts.append(f"Parciales: {result.partial_count}")
        parts.append(f"Omitidos: {result.skipped_count}")
        parts.append(f"Errores OCR: {result.error_count}")
        self._summary_label.setText(" | ".join(parts))

        self._status_label.setText(
            f"OCR completado. {result.ocr_count} procesados, "
            f"{result.reused_count} reutilizados."
        )

    def _on_ocr_failed(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _cancel_operation(self) -> None:
        self._status_label.setText("Cancelando…")
        if self._hash_worker is not None:
            self._hash_worker.request_cancel()
        if self._extract_worker is not None:
            self._extract_worker.request_cancel()
        if self._ocr_worker is not None:
            self._ocr_worker.request_cancel()

    def _on_extract_progress(self, current: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(current)

    def _on_extract_stage(self, stage: str) -> None:
        self._status_label.setText(stage)

    def _on_extract_finished(self, result: object) -> None:
        from folderscribe.domain.extraction import ExtractionResult

        assert isinstance(result, ExtractionResult)
        if self._view_model is not None:
            self._view_model.apply_extraction_result(result)
            self._table_model.set_rows(self._view_model.rows)

        parts = []
        if self._view_model is not None:
            total = self._view_model.total_files + self._view_model.total_skipped
            parts.append(f"Total: {total}")
            parts.append(f"Indexados: {self._view_model.total_indexed}")
            parts.append(f"Compatibles: {self._view_model.total_compatible}")
            parts.append(f"No compatibles: {self._view_model.total_not_compatible}")
            parts.append(f"Omitidos: {self._view_model.total_skipped}")
            parts.append(f"Errores: {self._view_model.total_errors}")
        parts.append(f"Extraídos: {result.extracted_count}")
        parts.append(f"Reutilizados: {result.reused_count}")
        parts.append(f"Parciales: {result.partial_count}")
        parts.append(f"Needs OCR: {result.needs_ocr_count}")
        parts.append(f"Errores: {result.error_count}")
        self._summary_label.setText(" | ".join(parts))

        self._status_label.setText(
            f"Extracción completada. {result.extracted_count} extraídos, "
            f"{result.reused_count} reutilizados."
        )

    def _on_extract_failed(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _cleanup_extract_worker(self) -> None:
        if self._extract_worker is not None:
            self._extract_worker.deleteLater()
            self._extract_worker = None
        self._extract_btn.setEnabled(True)
        self._hash_btn.setEnabled(True)
        self._ocr_btn.setEnabled(True)
        self._ocr_mode_combo.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._scan_btn.setEnabled(True)
        self._progress_bar.hide()

    def _cleanup_ocr_worker(self) -> None:
        if self._ocr_worker is not None:
            self._ocr_worker.deleteLater()
            self._ocr_worker = None
        self._ocr_btn.setEnabled(True)
        self._ocr_mode_combo.setEnabled(True)
        self._extract_btn.setEnabled(True)
        self._hash_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._scan_btn.setEnabled(True)
        self._progress_bar.hide()

    def _cleanup_hash_worker(self) -> None:
        if self._hash_worker is not None:
            self._hash_worker.deleteLater()
            self._hash_worker = None
        self._hash_btn.setEnabled(True)
        self._extract_btn.setEnabled(True)
        self._ocr_btn.setEnabled(True)
        self._ocr_mode_combo.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._scan_btn.setEnabled(True)
        self._progress_bar.hide()

    def _on_filter_changed(self, index: int) -> None:
        mode = self._filter_combo.itemData(index)
        if mode:
            self._proxy_model.set_filter_mode(str(mode))

    def _update_summary(self) -> None:
        if self._view_model is None:
            return
        vm = self._view_model
        parts = [
            f"Total: {vm.total_files + vm.total_skipped}",
            f"Indexados: {vm.total_indexed}",
            f"Compatibles: {vm.total_compatible}",
            f"No compatibles: {vm.total_not_compatible}",
            f"Omitidos: {vm.total_skipped}",
            f"Errores: {vm.total_errors}",
        ]
        self._summary_label.setText(" | ".join(parts))

    def _update_errors(self) -> None:
        if self._view_model is None:
            return
        if not self._view_model.errors:
            self._error_tab.setPlaceholderText("No hay errores.")
            return
        lines = []
        for err in self._view_model.errors:
            lines.append(f"[{err.code}] {err.path}: {err.message}")
        self._error_tab.setPlainText("\n".join(lines))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            if not self._worker.wait(3000):
                self._worker.terminate()
                self._worker.wait()
        if self._hash_worker is not None and self._hash_worker.isRunning():
            self._hash_worker.request_cancel()
            if not self._hash_worker.wait(3000):
                self._hash_worker.terminate()
                self._hash_worker.wait()
        if self._extract_worker is not None and self._extract_worker.isRunning():
            self._extract_worker.request_cancel()
            if not self._extract_worker.wait(3000):
                self._extract_worker.terminate()
                self._extract_worker.wait()
        if self._ocr_worker is not None and self._ocr_worker.isRunning():
            self._ocr_worker.request_cancel()
            if not self._ocr_worker.wait(3000):
                self._ocr_worker.terminate()
                self._ocr_worker.wait()
        super().closeEvent(event)


class _DuplicateTableModel(QAbstractTableModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[Any] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # type: ignore[override]
        return len(_DUPLICATE_HEADERS)

    def data(  # type: ignore[override]
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.group_id
            if col == 1:
                h = row.hash_value
                return h[:16] if len(h) > 16 else h
            if col == 2:
                return self._format_size(row.file_size)
            if col == 3:
                return str(row.file_count)
            if col == 4:
                return self._format_size(row.wasted_space)
            if col == 5:
                return row.file_paths
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
            if 0 <= section < len(_DUPLICATE_HEADERS):
                return _DUPLICATE_HEADERS[section]
        return None

    def _format_size(self, size: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}" if unit != "B" else f"{size} B"
            size //= 1024
        return f"{size:.1f} TB"

    def set_rows(self, rows: list[Any]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()
