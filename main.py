import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.ui.main_window import Window


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("WaveForge")
    app.setApplicationName("WaveForge FPGA")
    app.setStyle("Fusion")
    w = Window()
    w.show()
    app.processEvents()
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        w.open_path(Path(sys.argv[1]))
    elif "--smoke-test" not in sys.argv:
        QTimer.singleShot(0, w.open_startup_project)
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(350, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
