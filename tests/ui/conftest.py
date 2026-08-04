import pytest
from pytestqt.qtbot import QtBot


@pytest.fixture
def qt_app(qapp: QtBot) -> QtBot:
    return qapp
