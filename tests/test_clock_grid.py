import pytest
from PySide6.QtCore import Qt, QPointF
from app.graphics.scene import HEADER
from app.core.model import Project, Track
from app.ui.widgets import Fields
from app.services.files import save, load


def form(editor):
    return next(
        editor.props.itemAt(i).widget()
        for i in range(editor.props.count())
        if isinstance(editor.props.itemAt(i).widget(), Fields)
    )


def apply(editor):
    editor.props.itemAt(3).widget().click()


def major_times(editor):
    return [t for t, major, _ in editor.scene.grid_ticks(0, 60000) if major]


@pytest.mark.parametrize("field,value", [("period", "20000"), ("freq", "50")])
def test_clock_properties_update_grid(editor, field, value, tmp_path):
    w = editor
    w.fit()
    clk = w.p.tracks[0]
    w.select(clk.id)
    assert w.p.grid_parameters() == (5000, 0, 10000)
    form(w).controls[field].setText(value)
    apply(w)
    assert w.p.track(clk.id).period == 20000
    assert w.p.grid_parameters() == (10000, 0, 20000)
    assert major_times(w) == [0, 20000, 40000, 60000]
    assert w.view.snap(13000) == 10000
    w.history.undo()
    assert w.p.grid_parameters() == (5000, 0, 10000)
    w.history.redo()
    form(w).controls["divider"].setText("2")
    form(w).controls["phase"].setText("3000")
    apply(w)
    assert w.p.grid_parameters() == (20000, 3000, 40000)
    assert 43000 in major_times(w)
    path = tmp_path / "grid.wfg"
    save(w.p, path)
    assert load(path).grid_parameters() == (20000, 3000, 40000)


def test_manual_grid_and_legacy_project(editor):
    w = editor
    w.select("")
    form(w).controls["grid_mode"].setCurrentIndex(1)
    form(w).controls["step"].setText("7000")
    apply(w)
    assert w.p.grid_parameters() == (7000, 0, 7000)
    w.select(w.p.tracks[0].id)
    form(w).controls["freq"].setText("50")
    apply(w)
    assert w.p.grid_parameters() == (7000, 0, 7000)
    data = w.p.data()
    data.pop("grid_mode")
    assert Project.parse(data).grid_parameters() == (10000, 0, 20000)


def test_grid_reference_follows_visibility_and_integer_time():
    first = Track("clk_a", "clock", period=11001, phase=101)
    second = Track("clk_b", "clock", period=16000, divider=2, phase=200)
    p = Project(tracks=[first, second])
    assert p.grid_parameters() == (11001, 101, 11001)
    first.visible = False
    assert p.grid_parameters() == (16000, 200, 32000)
    second.group = "hidden"
    p.collapsed = ["hidden"]
    assert p.grid_parameters() == (p.step, 0, p.step)


def test_phase_drag_uses_updated_grid(editor, qtbot):
    w = editor
    w.replace(Project(tracks=[Track("clk", "clock", period=20000)]), None)
    w.fit()

    def point(t):
        return w.view.mapFromScene(QPointF(w.scene.axis.x(t), HEADER + 29))

    qtbot.mousePress(w.view.viewport(), Qt.LeftButton, pos=point(20000))
    qtbot.mouseMove(w.view.viewport(), pos=point(33000))
    qtbot.mouseRelease(w.view.viewport(), Qt.LeftButton, pos=point(33000))
    assert w.p.tracks[0].phase == 10000
    assert w.p.grid_parameters() == (10000, 10000, 20000)
    w.history.undo()
    assert w.p.grid_parameters() == (10000, 0, 20000)
