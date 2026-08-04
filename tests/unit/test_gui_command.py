from pathlib import Path

import pytest

from folderscribe.main import main


def test_gui_command_without_pyside6(
    capsys: pytest.CaptureFixture[str],
) -> None:
    try:
        import PySide6  # noqa: F401

        pytest.skip(
            "PySide6 está instalado; probar sin él no es posible en este entorno"
        )
    except ImportError:
        exit_code = main(["gui"])
        assert exit_code == 4
        captured = capsys.readouterr()
        assert "PySide6" in captured.err


def test_scan_command_still_works(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    exit_code = main(["scan", str(root)])
    assert exit_code == 0
