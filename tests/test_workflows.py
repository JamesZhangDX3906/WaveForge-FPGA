from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog
from app.core.model import Track
from app.ui.widgets import Fields
from app.services.files import load


def test_new_add_properties_save_reopen(editor, monkeypatch, tmp_path):
    w = editor
    w.new()
    settings = iter(
        [
            {"name": "clk", "freq": "100", "duty": "50"},
            {"name": "rst_n"},
            {"name": "valid"},
            {"name": "ready"},
            {"name": "data", "width": "16"},
        ]
    )
    monkeypatch.setattr("app.ui.operations.dialog", lambda *args: next(settings))
    for kind in ("clock", "signal", "signal", "signal", "bus"):
        w.add(kind)
    assert [s.name for s in w.p.tracks] == ["clk", "rst_n", "valid", "ready", "data"]
    assert w.p.tracks[0].cycle == 10000
    s = w.p.tracks[-1]
    form = next(
        w.props.itemAt(i).widget()
        for i in range(w.props.count())
        if isinstance(w.props.itemAt(i).widget(), Fields)
    )
    form.controls["value"].setText("0x1234")
    w.props.itemAt(3).widget().click()
    assert w.p.track(s.id).edges[0].value == "4660"
    w.edit("Add segment", lambda: w.p.track(s.id).put(20000, "0x5678", w.p.duration))
    f = tmp_path / "acceptance.wfg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(f), ""))
    assert w.save_file()
    saved = w.p.data()
    w.new()
    w.open_path(f)
    assert w.p.data() == saved
    assert w.history.isClean()


def test_groups_visibility_and_paste(editor, qtbot):
    w = editor
    group = w.tree.topLevelItem(0)
    group.setExpanded(False)
    assert len(w.scene.rows) == 4
    w.history.undo()
    assert len(w.scene.rows) == 6
    child = w.tree.topLevelItem(0).child(0)
    child.setCheckState(0, Qt.Unchecked)
    assert len(w.scene.rows) == 5
    w.history.undo()
    w.selected = [s.id for s in w.p.tracks]
    w.copy()
    w.paste()
    assert len(w.p.tracks) == 12 and len(w.p.notes) == 4
    assert all(a.track in w.selected for n in w.p.notes[-2:] for a in (n.a, n.b))
    w.p.validate()
    w.history.undo()
    assert len(w.p.tracks) == 6


def test_measurement_and_auto_recovery(editor):
    w = editor
    w.cursor(123)
    w.cursor(987)
    w.autosave()
    assert load(w.recovery).cursors == [123, 987]
    w.history.undo()
    w.history.undo()
    w.autosave()
    assert not w.recovery.exists()


def test_asymmetric_clock():
    s = Track("clk", "clock", period=100, duty=25, start_high=False)
    assert sum(s.state(t) == "1" for t in range(100)) == 25
    s.invert = True
    s.divider = 2
    assert list(s.clock_edges(0, 199)) == [(0, "1", "0/0"), (150, "0", "0/1")]


def test_delay_without_reference_clock(editor, monkeypatch):
    from app.core.model import Project, Track, Edge

    s = Track("valid", edges=[Edge(0, "0"), Edge(100, "1")])
    editor.replace(Project(tracks=[s]), None)
    editor.select(s.id)
    monkeypatch.setattr(
        "app.ui.operations.dialog",
        lambda *args: {
            "mode": editor.tr2("整体延迟", "Delay"),
            "offset": "20",
            "cycles": "1",
        },
    )
    editor.align()
    assert editor.p.tracks[0].edges[1].t == 120
