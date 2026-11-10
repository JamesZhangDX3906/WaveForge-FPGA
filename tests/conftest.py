import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTEST_QT_API", "pyside6")
import pytest
from app.ui.main_window import Window


@pytest.fixture
def editor(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("WAVEFORGE_DATA_DIR", str(tmp_path))
    window = Window()
    qtbot.addWidget(window, before_close_func=lambda w: w.history.setClean())
    window.show()
    qtbot.wait(30)
    yield window
    window.history.setClean()
