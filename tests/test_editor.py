import time
from xml.etree import ElementTree as ET
from PySide6.QtWidgets import QApplication, QInputDialog
from PySide6.QtGui import QImage
from PySide6.QtCore import Qt, QPointF
from app.core.model import Track, Project
from app.graphics.scene import ROW, HEADER
from app.exporters.render import render
from app.services.files import save, load


def point(w, row, t):
    return w.view.mapFromScene(QPointF(w.scene.axis.x(t), HEADER + row * ROW + 29))


def test_mouse_edit_measure_annotation_save(editor, qtbot, monkeypatch, tmp_path):
    w = editor
    clk, rst, valid, ready, bus = w.p.tracks[:5]
    assert clk.period == 10000 and clk.duty == 50 and bus.width == 16
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **kw: ("1", True))
    qtbot.mouseDClick(w.view.viewport(), Qt.LeftButton, pos=point(w, 1, 10000))
    assert w.p.track(rst.id).state(10000) == "1"
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("0xAA55", True))
    qtbot.mouseDClick(w.view.viewport(), Qt.LeftButton, pos=point(w, 4, 30000))
    assert w.p.track(bus.id).state(30000) == str(0xAA55)
    monkeypatch.setattr(
        "app.ui.operations.dialog", lambda *args: {"kind": "Setup", "text": "tSU"}
    )
    w.mode("note")
    qtbot.mouseClick(w.view.viewport(), Qt.LeftButton, pos=point(w, 2, 25000))
    qtbot.mouseClick(w.view.viewport(), Qt.LeftButton, pos=point(w, 0, 30000))
    assert w.p.notes[-1].a.edge == valid.edges[1].id
    w.mode("select")
    a, b = point(w, 2, 25000), point(w, 2, 30000)
    qtbot.mousePress(w.view.viewport(), Qt.LeftButton, pos=a)
    qtbot.mouseMove(w.view.viewport(), pos=b)
    qtbot.mouseRelease(w.view.viewport(), Qt.LeftButton, pos=b)
    assert w.p.resolve(w.p.notes[-1].a) == 30000
    w.history.undo()
    assert w.p.resolve(w.p.notes[-1].a) == 25000
    w.history.redo()
    w.mode("measure")
    for row, t in [(2, 30000), (3, 35000)]:
        qtbot.mouseClick(w.view.viewport(), Qt.LeftButton, pos=point(w, row, t))
    assert w.p.cursors == [30000, 35000]
    f = tmp_path / "mouse.wfg"
    save(w.p, f)
    assert load(f).data() == w.p.data()
    w.select(valid.id)
    w.delete()
    assert all(n.a.track != valid.id for n in w.p.notes)
    w.history.undo()
    assert w.p.resolve(w.p.notes[-1].a) == 30000


def test_exports(editor, tmp_path):
    p = editor.p
    for ext in ("svg", "pdf", "png"):
        f = tmp_path / ("diagram." + ext)
        render(p, ext, f, 1200, 5000, 60000, "white")
        assert f.stat().st_size > 1000
        if ext == "pdf":
            assert f.read_bytes().startswith(b"%PDF")
        if ext == "svg":
            root = ET.parse(f)
            assert root.findall(
                ".//{http://www.w3.org/2000/svg}polyline"
            ) or root.findall(".//{http://www.w3.org/2000/svg}path")
            assert "valid" in "".join(root.getroot().itertext())
        if ext == "png":
            assert QImage(str(f)).width() == 1200
    img = render(p, "clipboard", background="transparent")
    assert img.pixelColor(0, 0).alpha() == 0


def test_large_scene_and_theme(editor, qtbot):
    w = editor
    p = Project(
        tracks=[
            Track(f"ch{i}", "clock" if i % 4 == 0 else "signal") for i in range(128)
        ]
    )
    w.replace(p, None)
    assert len(w.scene.items()) == 128
    start = time.monotonic()
    for _ in range(20):
        w.zoom(1.1)
        w.zoom(1 / 1.1)
        QApplication.processEvents()
    assert time.monotonic() - start < 8
    for light in [True, False]:
        w.light = light
        w.build()
        qtbot.wait(10)
        assert w.scene.paper == light
        assert not w.grab().isNull()
