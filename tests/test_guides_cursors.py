from PySide6.QtCore import Qt, QPoint, QPointF, QTimer
from PySide6.QtWidgets import QMenu, QApplication
from app.core.model import Project, Track
from app.graphics.scene import HEADER
from app.services.files import save, load


def point(w, t, y=HEADER + 90):
    return w.view.mapFromScene(QPointF(w.scene.axis.x(t), y))


def test_click_existing_cursor_does_not_add_duplicate(editor, qtbot):
    w = editor
    w.mode("measure")
    p = point(w, 20000)
    qtbot.mouseClick(w.view.viewport(), Qt.LeftButton, pos=p)
    count = w.history.count()
    qtbot.mouseClick(w.view.viewport(), Qt.LeftButton, pos=p)
    assert w.p.cursors == [20000]
    assert w.history.count() == count
    qtbot.mouseClick(w.view.viewport(), Qt.LeftButton, pos=point(w, 50000))
    qtbot.mouseClick(w.view.viewport(), Qt.LeftButton, pos=p)
    assert w.p.cursors == [20000, 50000]
    w.cursor(20000)
    assert w.p.cursors == [20000, 50000]


def test_cursor_drag_only_moves_one_and_undoes(editor, qtbot, tmp_path):
    w = editor
    w.cursor(20000)
    w.cursor(50000)
    w.mode("measure")
    before = w.history.index()
    qtbot.mousePress(w.view.viewport(), Qt.LeftButton, pos=point(w, 20000))
    qtbot.mouseMove(w.view.viewport(), pos=point(w, 30000))
    qtbot.mouseMove(w.view.viewport(), pos=point(w, 35000))
    assert w.p.cursors == [35000, 50000]
    qtbot.mouseRelease(w.view.viewport(), Qt.LeftButton, pos=point(w, 35000))
    assert w.history.index() == before + 1
    w.history.undo()
    assert w.p.cursors == [20000, 50000]
    w.history.redo()
    assert w.p.cursors == [35000, 50000]
    file = tmp_path / "cursors.wfg"
    save(w.p, file)
    assert load(file).cursors == [35000, 50000]


def test_overlapping_cursor_handles_can_be_separated(editor, qtbot):
    w = editor
    w.p.cursors = [20000, 20000]  # Also exercise old projects with overlapped cursors.
    w.refresh()
    w.mode("select")
    x = w.view.mapFromScene(QPointF(w.scene.axis.x(20000), 0)).x()
    pos = QPoint(x, 37)  # B's handle is below A's.
    assert w.view.cursor_at(pos) == 1
    qtbot.mousePress(w.view.viewport(), Qt.LeftButton, pos=pos)
    qtbot.mouseMove(w.view.viewport(), pos=QPoint(point(w, 40000).x(), 37))
    qtbot.mouseRelease(
        w.view.viewport(), Qt.LeftButton, pos=QPoint(point(w, 40000).x(), 37)
    )
    assert w.p.cursors == [20000, 40000]


def test_drag_cursor_after_vertical_scroll_and_cancel(editor, qtbot):
    w = editor
    w.replace(Project(tracks=[Track(str(i)) for i in range(30)]), None)
    w.cursor(20000)
    w.cursor(50000)
    w.view.verticalScrollBar().setValue(300)
    qtbot.wait(5)
    x = w.view.mapFromScene(QPointF(w.scene.axis.x(20000), 0)).x()
    pos = QPoint(x, 24)
    assert w.view.cursor_at(pos) == 0
    qtbot.mousePress(w.view.viewport(), Qt.LeftButton, pos=pos)
    qtbot.mouseMove(w.view.viewport(), pos=QPoint(point(w, 30000).x(), 24))
    assert w.p.cursors == [30000, 50000]
    qtbot.keyClick(w.view, Qt.Key_Escape)
    qtbot.mouseRelease(w.view.viewport(), Qt.LeftButton, pos=pos)
    assert w.p.cursors == [20000, 50000]


def test_delete_one_overlapping_clock_guide_via_context_menu(
    editor, monkeypatch, tmp_path
):
    w = editor
    a = Track("clk_a", "clock", guide_modes=["cycle"])
    b = Track("clk_b", "clock", period=20000, guide_modes=["cycle"])
    w.replace(Project(tracks=[a, b]), None)

    def execute():
        menu = QApplication.activePopupWidget()
        assert isinstance(menu, QMenu)
        try:
            action = next(
                a for a in menu.actions() if "clk_a" in a.text() and "20" in a.text()
            )
            action.trigger()
        finally:
            menu.close()

    QTimer.singleShot(0, execute)

    class Event:
        def pos(self):
            return point(w, 20000)

        def globalPos(self):
            return w.view.viewport().mapToGlobal(self.pos())

    w.view.contextMenuEvent(Event())
    assert w.p.track(a.id).hidden_guides == ["2/0"]
    lines = [(s.id, t) for s, t, key in w.scene.guide_lines(0, 60000)]
    assert (a.id, 20000) not in lines and (b.id, 20000) in lines
    assert (a.id, 10000) in lines and (a.id, 30000) in lines
    w.history.undo()
    assert not w.p.track(a.id).hidden_guides
    w.history.redo()
    w.edit("Change clock", lambda: setattr(w.p.track(a.id), "period", 12000))
    assert (a.id, 24000) not in [
        (s.id, t) for s, t, key in w.scene.guide_lines(0, 60000)
    ]
    file = tmp_path / "deleted-line.wfg"
    save(w.p, file)
    assert load(file).track(a.id).hidden_guides == ["2/0"]
    w.restore_clock_guides(a.id)
    assert not w.p.track(a.id).hidden_guides
    w.history.undo()
    assert w.p.track(a.id).hidden_guides == ["2/0"]


def test_locked_clock_guide_is_preserved(editor):
    w = editor
    track = w.p.tracks[0]
    track.locked = True
    w.hide_clock_guide(track.id, "2/0")
    assert not track.hidden_guides
