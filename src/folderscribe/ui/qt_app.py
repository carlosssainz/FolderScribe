from PySide6.QtWidgets import QApplication

from folderscribe.ui.main_window import MainWindow


def run_gui() -> int:
    app = QApplication([])

    window = MainWindow()
    window.show()
    app.exec()
    return 0
