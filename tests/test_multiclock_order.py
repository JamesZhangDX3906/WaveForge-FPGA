import json
from PySide6.QtCore import Qt, QPoint, QPointF, QMimeData
from app.core.model import Project, Track
from app.graphics.scene import TimingScene, HEADER, ROW
from app.ui.widgets import Fields, Tree
from app.services.files import save, load
from app.exporters.render import render


def test_multiple_clock_guides_follow_independent_edges(qapp, tmp_path):
    a = Track("clk_a", "clock", color="#ff0000", guide_modes=["rising"])
    b = Track(
        "clk_b",
        "clock",
        period=16000,
        phase=3000,
        color="#00ff00",
        guide_modes=["falling"],
    )
    p = Project(duration=50000, tracks=[a, b])
    scene = TimingScene(p, 1000)

    class Painter:
        def __init__(self):
            self.lines = []

        def setPen(self, pen):
            self.color = pen.color().name()

        def drawLine(self, line):
            self.lines.append((self.color, scene.axis.t(line.x1())))

    painter = Painter()
    scene.drawForeground(painter, scene.sceneRect())
    assert [t for color, t in painter.lines if color == "#ff0000"] == [
        0,
        10000,
        20000,
        30000,
        40000,
        50000,
    ]
    assert [t for color, t in painter.lines if color == "#00ff00"] == [
        11000,
        27000,
        43000,
    ]
    file = tmp_path / "clocks.wfg"
    save(p, file)
    assert load(file).data() == p.data()
    svg = tmp_path / "clocks.svg"
    render(p, "svg", svg)
    text = svg.read_text(encoding="utf8")
    assert "#ff0000" in text and "#00ff00" in text


def test_clock_inspector_and_multiselect_menu(editor):
    w = editor
    a = w.p.tracks[0]
    b = Track("clk_b", "clock", period=16000, color="#f3b471")
    w.edit("Add clock", lambda: w.p.tracks.append(b))
    w.select(b.id)
    form = next(
        w.props.itemAt(i).widget()
        for i in range(w.props.count())
        if isinstance(w.props.itemAt(i).widget(), Fields)
    )
    form.controls["guide_rising"].setChecked(True)
    form.controls["guide_color"].setText("#ec70df")
    w.props.itemAt(3).widget().click()
    assert w.p.track(b.id).guide_modes == ["rising"]
    assert w.p.track(b.id).guide_color == "#ec70df"
    w.select(a.id, True)
    w.toggle_clock_guide("cycle")
    assert "cycle" in w.p.guides_for(w.p.track(a.id))
    assert "cycle" in w.p.guides_for(w.p.track(b.id))
    w.history.undo()
    assert w.p.track(b.id).guide_modes == ["rising"]
    w.history.undo()
    assert w.p.track(b.id).guide_modes is None


def test_legacy_guides_and_hidden_clock():
    a, b = Track("a", "clock"), Track("b", "clock")
    p = Project(tracks=[a, b], guides=["cycle"])
    data = p.data()
    for s in data["tracks"]:
        s.pop("guide_modes")
        s.pop("guide_color")
    p = Project.parse(data)
    assert p.guides_for(p.tracks[0]) == ["cycle"]
    assert p.guides_for(p.tracks[1]) == []
    p.tracks[0].guide_modes = []
    assert p.guides_for(p.tracks[0]) == []


def test_same_waveform_colors_get_distinct_persistent_guides(editor):
    w = editor
    a = Track("a", "clock")
    b = Track("b", "clock", period=16000)
    w.replace(Project(tracks=[a, b]), None)
    w.select(a.id)
    w.select(b.id, True)
    w.toggle_clock_guide("rising")
    first, second = w.p.tracks
    assert first.guide_color != second.guide_color
    colors = {s.id: s.guide_color for s in w.p.tracks}
    w.reorder_tracks([second.id], first.id)
    assert {s.id: s.guide_color for s in w.p.tracks} == colors


def test_name_column_mouse_reorders_preserving_bindings(editor, qtbot, tmp_path):
    w = editor
    before = w.p.data()
    ident = w.p.tracks[2].id
    qtbot.mousePress(w.names, Qt.LeftButton, pos=QPoint(35, HEADER + 2 * ROW + 25))
    qtbot.mouseMove(w.names, pos=QPoint(35, HEADER + 3))
    qtbot.mouseRelease(w.names, Qt.LeftButton, pos=QPoint(35, HEADER + 3))
    assert w.p.tracks[0].id == ident
    assert w.scene.rows[0].id == ident
    assert w.p.resolve(w.p.notes[0].a) == 25000
    assert "cycle" not in w.p.guides_for(w.p.tracks[1])
    path = tmp_path / "ordered.wfg"
    save(w.p, path)
    assert load(path).tracks[0].id == ident
    w.history.undo()
    assert w.p.data() == before
    w.history.redo()
    assert w.p.tracks[0].id == ident


def test_tree_drop_moves_selected_block_without_deleting_rows(editor):
    w = editor
    original = [s.id for s in w.p.tracks]
    ids = original[2:4]
    target = w.tree.topLevelItem(0).child(0)
    pos = w.tree.visualItemRect(target).topLeft() + QPoint(15, 2)
    mime = QMimeData()
    mime.setData(Tree.TRACK_MIME, json.dumps(ids).encode())

    class Drop:
        def source(self):
            return w.tree

        def mimeData(self):
            return mime

        def position(self):
            return QPointF(pos)

        def setDropAction(self, action):
            pass

        def accept(self):
            pass

    w.tree.dropEvent(Drop())
    assert [s.id for s in w.p.tracks] == ids + original[:2] + original[4:]
    assert len(w.scene.rows) == len(original)
    w.history.undo()
    assert [s.id for s in w.p.tracks] == original


def test_model_reorder_multi_and_locked():
    rows = [Track(str(i)) for i in range(5)]
    p = Project(tracks=rows.copy())
    p.reorder_tracks([rows[3].id, rows[1].id], rows[4].id, after=True)
    assert [s.name for s in p.tracks] == ["0", "2", "4", "1", "3"]
    rows[1].locked = True
    original = p.data()
    p.reorder_tracks([rows[1].id], rows[0].id)
    assert p.data() == original
