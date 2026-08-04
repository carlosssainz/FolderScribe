from pathlib import Path

from pytestqt.qtbot import QtBot

from folderscribe.domain.ocr import OcrMode, OcrResult
from folderscribe.ui.ocr_worker import OcrWorker

from tests.conftest import FakeOcrEngine


class TestOcrWorker:
    def test_ocr_worker_finished(
        self,
        qtbot: QtBot,
        scanned_session: tuple[Path, str],
        fake_ocr_engine: FakeOcrEngine,
    ) -> None:
        db_path, session_id = scanned_session
        worker = OcrWorker(
            session_id=session_id,
            database_path=db_path,
            mode=OcrMode.FAST,
            engine=fake_ocr_engine,
        )

        with qtbot.wait_signal(worker.ocr_finished, timeout=10000) as blocker:
            worker.start()

        result = blocker.args[0]
        assert isinstance(result, OcrResult)
        assert result.engine_available
        assert result.ocr_count == 1
        assert fake_ocr_engine.calls == 1

        qtbot.wait_until(lambda: worker.isFinished(), timeout=5000)

    def test_ocr_worker_engine_unavailable(
        self,
        qtbot: QtBot,
        scanned_session: tuple[Path, str],
    ) -> None:
        db_path, session_id = scanned_session
        engine = FakeOcrEngine(available=False)
        worker = OcrWorker(
            session_id=session_id,
            database_path=db_path,
            mode=OcrMode.FAST,
            engine=engine,
        )

        with qtbot.wait_signal(worker.ocr_failed, timeout=10000) as blocker:
            worker.start()

        msg = blocker.args[0]
        assert "tesseract" in msg
        assert engine.calls == 0

        qtbot.wait_until(lambda: worker.isFinished(), timeout=5000)
