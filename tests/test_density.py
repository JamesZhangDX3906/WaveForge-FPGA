from PySide6.QtCore import Qt, QPointF
from app.core.model import Project, Track, Edge
from app.exporters.render import render
from app.graphics.scene import HEADER, ROW


def test_drag_with_128_channels(editor, qtbot):
    rows = [Track("clk", "clock")] + [
        Track(f"signal_{i}", edges=[Edge(0, "0"), Edge(25000, "1")]) for i in range(127)
    ]
    editor.replace(Project(tracks=rows), None)
    editor.fit()
    w = editor
    points = [
        w.view.mapFromScene(QPointF(w.scene.axis.x(t), HEADER + ROW * 2 + 29))
        for t in (25000, 30000)
    ]
    qtbot.mousePress(w.view.viewport(), Qt.LeftButton, pos=points[0])
    qtbot.mouseMove(w.view.viewport(), pos=points[1])
    qtbot.mouseRelease(w.view.viewport(), Qt.LeftButton, pos=points[1])
    assert w.p.tracks[2].edges[1].t == 30000
    assert w.p.tracks[3].edges[1].t == 25000
    w.history.undo()
    assert w.p.tracks[2].edges[1].t == 25000


def test_dense_and_cropped_export(qapp):
    p = Project(
        duration=10**12,
        step=10,
        tracks=[
            Track("clk", "clock", period=10),
            Track("dense", edges=[Edge(i, str(i % 2)) for i in range(40000)]),
        ],
    )
    for lo, hi in [(0, p.duration), (0, 40000), (p.duration - 100, p.duration)]:
        image = render(p, "clipboard", lo=lo, hi=hi, width=800)
        assert image.width() == 800 and not image.isNull()
