from pathlib import Path
from types import SimpleNamespace

import pytest

import folderscribe.infrastructure.ocr.tesseract_engine as engine_module
from folderscribe.domain.ocr import OcrError, OcrMode
from folderscribe.infrastructure.ocr import TesseractOcrEngine


class FakePixmap:
    def __init__(self, width: int, height: int, samples: bytes) -> None:
        self.width = width
        self.height = height
        self.samples = samples


class FakePage:
    def __init__(self, dpi_seen: list[int | None]) -> None:
        self._dpi_seen = dpi_seen

    def get_pixmap(self, dpi: int | None = None) -> FakePixmap:
        self._dpi_seen.append(dpi)
        return FakePixmap(10, 10, b"\x00" * 300)


class FakeFitzDoc:
    def __init__(self, page_count: int, dpi_seen: list[int | None]) -> None:
        self.page_count = page_count
        self._dpi_seen = dpi_seen
        self.closed = False

    def load_page(self, index: int) -> FakePage:
        return FakePage(self._dpi_seen)

    def close(self) -> None:
        self.closed = True


class FakePytesseract:
    def __init__(self, fail_on_call: int | None = None) -> None:
        self.config_calls: list[str] = []
        self._fail_on_call = fail_on_call

    def get_tesseract_version(self) -> str:
        return "fake 5.0"

    def image_to_string(
        self,
        image: object,
        lang: str | None = None,
        config: str | None = None,
    ) -> str:
        self.config_calls.append(config or "")
        if (
            self._fail_on_call is not None
            and len(self.config_calls) > self._fail_on_call
        ):
            raise RuntimeError("tesseract failure")
        return f"FAKE TEXT {len(self.config_calls)}"


def _patch_fitz(
    monkeypatch: pytest.MonkeyPatch, doc: FakeFitzDoc | None = None
) -> None:
    if doc is None:
        doc = FakeFitzDoc(2, [])

    def _open(path: str) -> FakeFitzDoc:
        return doc

    monkeypatch.setattr(engine_module, "fitz", SimpleNamespace(open=_open))
    monkeypatch.setattr(
        engine_module,
        "Image",
        SimpleNamespace(frombytes=lambda *args, **kwargs: object()),
    )
    return doc  # type: ignore[return-value]


def _patch_pytesseract(
    monkeypatch: pytest.MonkeyPatch, fake: FakePytesseract | None = None
) -> FakePytesseract:
    if fake is None:
        fake = FakePytesseract()
    monkeypatch.setattr(engine_module, "pytesseract", fake)
    return fake


@pytest.fixture
def engine() -> TesseractOcrEngine:
    return TesseractOcrEngine(binary="tesseract")


class TestIsAvailable:
    def test_false_without_binary(
        self, engine: TesseractOcrEngine, monkeypatch
    ) -> None:
        _patch_pytesseract(monkeypatch)
        monkeypatch.setattr(engine_module.shutil, "which", lambda _: None)
        assert engine.is_available() is False

    def test_false_without_pytesseract(
        self, engine: TesseractOcrEngine, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            engine_module.shutil, "which", lambda _: "/usr/bin/tesseract"
        )
        monkeypatch.setattr(engine_module, "pytesseract", None)
        assert engine.is_available() is False

    def test_false_when_version_check_fails(
        self, engine: TesseractOcrEngine, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            engine_module.shutil, "which", lambda _: "/usr/bin/tesseract"
        )

        class Broken(FakePytesseract):
            def get_tesseract_version(self) -> str:
                raise RuntimeError("broken")

        _patch_pytesseract(monkeypatch, Broken())
        assert engine.is_available() is False

    def test_true_when_ready(self, engine: TesseractOcrEngine, monkeypatch) -> None:
        monkeypatch.setattr(
            engine_module.shutil, "which", lambda _: "/usr/bin/tesseract"
        )
        _patch_pytesseract(monkeypatch)
        assert engine.is_available() is True


class TestOcrPdf:
    def test_fast_mode_settings(
        self, engine: TesseractOcrEngine, monkeypatch, tmp_path: Path
    ) -> None:
        doc = _patch_fitz(monkeypatch)
        fake = _patch_pytesseract(monkeypatch)
        pdf = tmp_path / "s.pdf"
        pdf.write_bytes(b"%PDF")

        result = engine.ocr_pdf(pdf, OcrMode.FAST)

        assert doc.closed
        assert result.total_pages == 2
        assert result.processed_pages == 2
        assert doc._dpi_seen == [150, 150]  # noqa: SLF001
        assert fake.config_calls == ["--psm 3", "--psm 3"]
        assert "FAKE TEXT 1" in result.pages[0].text

    def test_full_mode_settings(
        self, engine: TesseractOcrEngine, monkeypatch, tmp_path: Path
    ) -> None:
        doc = _patch_fitz(monkeypatch)
        fake = _patch_pytesseract(monkeypatch)
        pdf = tmp_path / "s.pdf"
        pdf.write_bytes(b"%PDF")

        engine.ocr_pdf(pdf, OcrMode.FULL)

        assert doc._dpi_seen == [300, 300]  # noqa: SLF001
        assert fake.config_calls == ["--psm 6", "--psm 6"]

    def test_page_error_captured(
        self, engine: TesseractOcrEngine, monkeypatch, tmp_path: Path
    ) -> None:
        _patch_fitz(monkeypatch)
        _patch_pytesseract(monkeypatch, FakePytesseract(fail_on_call=1))
        pdf = tmp_path / "s.pdf"
        pdf.write_bytes(b"%PDF")

        result = engine.ocr_pdf(pdf, OcrMode.FAST)

        assert result.processed_pages == 2
        assert result.pages[0].error_message is None
        assert result.pages[1].error_message is not None

    def test_missing_fitz_raises(
        self, engine: TesseractOcrEngine, monkeypatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(engine_module, "fitz", None)
        _patch_pytesseract(monkeypatch)
        pdf = tmp_path / "s.pdf"
        pdf.write_bytes(b"%PDF")

        with pytest.raises(OcrError) as exc_info:
            engine.ocr_pdf(pdf, OcrMode.FAST)
        assert exc_info.value.code == "missing_dependency"

    def test_open_error_raises(
        self, engine: TesseractOcrEngine, monkeypatch, tmp_path: Path
    ) -> None:
        def _open(path: str) -> object:
            raise RuntimeError("cannot open")

        monkeypatch.setattr(engine_module, "fitz", SimpleNamespace(open=_open))
        _patch_pytesseract(monkeypatch)
        pdf = tmp_path / "s.pdf"
        pdf.write_bytes(b"%PDF")

        with pytest.raises(OcrError) as exc_info:
            engine.ocr_pdf(pdf, OcrMode.FAST)
        assert exc_info.value.code == "pdf_open_error"

    def test_cancel_stops_early(
        self, engine: TesseractOcrEngine, monkeypatch, tmp_path: Path
    ) -> None:
        _patch_fitz(monkeypatch)
        _patch_pytesseract(monkeypatch)
        pdf = tmp_path / "s.pdf"
        pdf.write_bytes(b"%PDF")

        calls = 0

        def cancel() -> bool:
            nonlocal calls
            calls += 1
            return calls >= 2

        result = engine.ocr_pdf(pdf, OcrMode.FAST, cancel_check=cancel)

        assert result.processed_pages == 1
        assert result.total_pages == 2

    def test_cancel_before_loop(
        self, engine: TesseractOcrEngine, monkeypatch, tmp_path: Path
    ) -> None:
        _patch_fitz(monkeypatch)
        _patch_pytesseract(monkeypatch)
        pdf = tmp_path / "s.pdf"
        pdf.write_bytes(b"%PDF")

        result = engine.ocr_pdf(pdf, OcrMode.FAST, cancel_check=lambda: True)

        assert result.processed_pages == 0
