import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QColorDialog
from app.core.model import Project, Track
from app.ui.widgets import Fields, ColorField
from app.services.files import save, load
from app.exporters.render import render


def inspector_form(w):
    return next(
        w.props.itemAt(i).widget()
        for i in range(w.props.count())
        if isinstance(w.props.itemAt(i).widget(), Fields)
    )


def test_delete_guides_of_hidden_and_locked_clocks(editor, tmp_path):
    w = editor
    tracks = [
        Track("legacy", "clock"),
        Track("hidden", "clock", visible=False, guide_modes=["cycle"]),
        Track(
            "locked",
            "clock",
            locked=True,
            guide_modes=["rising", "falling"],
            hidden_guides=["2/0"],
        ),
        Track("folded", "clock", group="group", guide_modes=["cycle"]),
    ]
    w.replace(Project(tracks=tracks, guides=["cycle"], collapsed=["group"]), None)
    for ident in [t.id for t in tracks]:
        before = w.p.data()
        others = {s.id: list(w.p.guides_for(s)) for s in w.p.tracks if s.id != ident}
        w.set_clock_cycle_guides(False, ident)
        assert w.p.guides_for(w.p.track(ident)) == []
        assert not w.p.track(ident).hidden_guides
        assert {
            s.id: list(w.p.guides_for(s)) for s in w.p.tracks if s.id != ident
        } == others
        file = tmp_path / "clock-guides.wfg"
        save(w.p, file)
        assert load(file).track(ident).guide_modes == []
        w.history.undo()
        assert w.p.data() == before
        w.history.redo()
        assert w.p.guides_for(w.p.track(ident)) == []


@pytest.mark.parametrize("row", [0, 2, 4])
def test_palette_changes_clock_signal_and_bus(editor, row, tmp_path):
    w = editor
    track = w.p.tracks[row]
    before = w.p.data()
    w.select(track.id)
    field = inspector_form(w).controls["color"]
    assert isinstance(field, ColorField)

    def choose():
        picker = QApplication.activeModalWidget()
        assert isinstance(picker, QColorDialog)
        picker.setCurrentColor(QColor("#d642a6"))
        picker.accept()

    QTimer.singleShot(0, choose)
    field.button.click()
    assert field.text() == "#d642a6"
    assert w.p.track(track.id).color == before["tracks"][row]["color"]
    image = field.button.icon().pixmap(18, 18).toImage()
    assert image.pixelColor(image.width() // 2, image.height() // 2).name() == "#d642a6"
    w.props.itemAt(3).widget().click()
    assert w.p.track(track.id).color == "#d642a6"
    assert w.scene.items_by_id[track.id].s.color == "#d642a6"
    assert all(
        s.color == old["color"]
        for i, (s, old) in enumerate(zip(w.p.tracks, before["tracks"]))
        if i != row
    )
    path = tmp_path / "color.wfg"
    save(w.p, path)
    assert load(path).track(track.id).color == "#d642a6"
    svg = tmp_path / "color.svg"
    render(w.p, "svg", svg)
    assert "#d642a6" in svg.read_text(encoding="utf8")
    w.history.undo()
    assert w.p.track(track.id).color == before["tracks"][row]["color"]
    w.history.redo()
    assert w.p.track(track.id).color == "#d642a6"


def test_palette_cancel_keeps_previous_color(editor):
    w = editor
    w.select(w.p.tracks[0].id)
    field = inspector_form(w).controls["color"]
    before = w.p.data()
    text = field.text()

    def cancel():
        picker = QApplication.activeModalWidget()
        picker.setCurrentColor(QColor("#ff0000"))
        picker.reject()

    QTimer.singleShot(0, cancel)
    field.button.click()
    assert field.text() == text
    assert w.p.data() == before


def test_guide_palette_and_manual_hex_validation(editor, monkeypatch):
    w = editor
    w.select(w.p.tracks[0].id)
    form = inspector_form(w)
    assert isinstance(form.controls["guide_color"], ColorField)
    form.controls["guide_color"].setText("#123abc")
    w.props.itemAt(3).widget().click()
    assert w.p.tracks[0].guide_color == "#123abc"
    before = w.p.data()
    errors = []
    monkeypatch.setattr(w, "error", errors.append)
    inspector_form(w).controls["color"].setText("invalid")
    w.props.itemAt(3).widget().click()
    assert errors and w.p.data() == before
