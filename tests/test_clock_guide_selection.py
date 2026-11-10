from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog
from app.core.model import Project, Track
from app.ui.widgets import Fields


def choose_clock(name):
    dlg = QApplication.activeModalWidget()
    assert isinstance(dlg, QDialog)
    combo = dlg.findChild(Fields).controls["clock"]
    combo.setCurrentIndex(combo.findText(name))
    dlg.accept()


def test_menu_explicit_clock_choice_and_idempotent_add(editor):
    w = editor
    a = Track("clk", "clock", guide_modes=["cycle"], guide_color="#ff0000")
    b = Track("clk", "clock", period=16000, hidden_guides=["2/0"])
    w.replace(Project(tracks=[a, b]), None)
    w.select(a.id)
    original_a = w.p.data()["tracks"][0]
    QTimer.singleShot(0, lambda: choose_clock("2 · clk"))
    w.add_clock_guides_action.trigger()
    assert w.p.track(b.id).guide_modes == ["cycle"]
    assert w.p.track(b.id).hidden_guides == []
    assert w.p.data()["tracks"][0] == original_a
    before = w.p.data()
    count = w.history.count()
    QTimer.singleShot(0, lambda: choose_clock("2 · clk"))
    w.add_clock_guides_action.trigger()
    assert w.p.data() == before and w.history.count() == count
    QTimer.singleShot(0, lambda: choose_clock("2 · clk"))
    w.delete_clock_guides_action.trigger()
    assert w.p.track(b.id).guide_modes == []
    assert w.p.data()["tracks"][0] == original_a
    assert {s.id for s, t, key in w.scene.guide_lines(0, 50000)} == {a.id}
    w.history.undo()
    assert w.p.data() == before


def test_cancel_clock_choice_and_empty_project(editor, monkeypatch):
    w = editor
    before = w.p.data()
    monkeypatch.setattr("app.ui.operations.dialog", lambda *args: None)
    w.add_clock_guides_action.trigger()
    w.delete_clock_guides_action.trigger()
    assert w.p.data() == before
    w.replace(Project(), None)
    messages = []
    monkeypatch.setattr(w, "info", lambda *args: messages.append(args))
    w.add_clock_guides_action.trigger()
    assert messages and w.history.isClean()
