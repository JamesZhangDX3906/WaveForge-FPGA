import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog
from app.ui.widgets import Fields
from app.services.files import save, load


def test_extend_duration_through_toolbar_dialog(editor, tmp_path):
    w = editor
    original = w.p.data()
    w.zoom(2)

    def enter_end_time():
        dlg = QApplication.activeModalWidget()
        assert isinstance(dlg, QDialog)
        fields = dlg.findChild(Fields)
        fields.controls["end"].setText("500")
        fields.controls["unit"].setCurrentText("ns")
        dlg.accept()

    QTimer.singleShot(0, enter_end_time)
    w.duration_action.trigger()
    assert w.p.duration == 500000
    assert w.zoom_factor == 1
    assert "500 ns" in w.duration_action.text()
    assert w.scene.axis.t(w.scene.axis.width) == 500000
    assert w.p.data()["tracks"] == original["tracks"]
    clk, _, valid, _, bus = w.p.tracks[:5]
    assert list(clk.clock_edges(490000, 500000))
    assert valid.state(490000) == valid.state(original["duration"] - 1)
    assert bus.state(490000) == bus.state(original["duration"] - 1)
    w.history.undo()
    assert w.p.duration == original["duration"]
    w.history.redo()
    assert w.p.duration == 500000
    # Exercise editing in the newly available time window.
    w.edit(
        "Late transition", lambda: w.p.track(valid.id).put(450000, "1", w.p.duration)
    )
    assert w.p.track(valid.id).state(450000) == "1"
    path = tmp_path / "extended.wfg"
    save(w.p, path)
    w.replace(load(path), path)
    assert w.p.duration == 500000
    assert w.p.track(valid.id).state(450000) == "1"


@pytest.mark.parametrize(
    "value,unit,expected", [("2", "μs", 2000000), ("500.001", "ns", 500001)]
)
def test_duration_units(editor, monkeypatch, value, unit, expected):
    monkeypatch.setattr(
        "app.ui.operations.dialog", lambda *a: {"end": value, "unit": unit}
    )
    editor.duration_action.trigger()
    assert editor.p.duration == expected


@pytest.mark.parametrize(
    "value", ["0", "-1", "NaN", "abc", "0.0001", "1000000000001", "10"]
)
def test_invalid_or_truncating_duration_preserves_project(editor, monkeypatch, value):
    original = editor.p.data()
    errors = []
    monkeypatch.setattr(editor, "error", errors.append)
    monkeypatch.setattr(
        "app.ui.operations.dialog", lambda *a: {"end": value, "unit": "ns"}
    )
    editor.duration_action.trigger()
    assert errors
    assert editor.p.data() == original
    assert editor.history.isClean()


def test_cancel_duration_dialog(editor, monkeypatch):
    original = editor.p.data()
    monkeypatch.setattr("app.ui.operations.dialog", lambda *a: None)
    editor.duration_action.trigger()
    assert editor.p.data() == original
