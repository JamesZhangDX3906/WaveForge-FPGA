import pytest
from app.core.model import Track, Project, Anchor, Note, fmt, ticks
from app.services.templates import TEMPLATES, template
from app.services.files import save, load
from app.graphics.scene import Axis
from app.importers.digital import read_csv, read_vcd


@pytest.mark.parametrize("name", TEMPLATES)
def test_templates_roundtrip(name, tmp_path):
    p = template(name)
    f = tmp_path / "diagram.wfg"
    save(p, f)
    assert load(f).data() == p.data()


def test_bus_width_and_edges():
    s = Track("data", "bus", width=16)
    s.put(10, "0x1234", 100)
    s.put(20, "0x5678", 100)
    edge = s.edges[1].id
    s.move(1, 50, 100)
    assert (s.edges[1].t, s.edges[1].id) == (19, edge)
    assert s.display(s.state(20)) == "0x5678"
    with pytest.raises(ValueError):
        s.put(25, "0x10000", 100)
    s.locked = True
    with pytest.raises(ValueError):
        s.put(2, "10", 100)
    assert s.state(2) == "0"


def test_binding_and_break_coordinates(tmp_path):
    p = template("AXI4-Stream")
    s = p.tracks[2]
    a = Anchor(s.edges[1].t, s.id, s.edges[1].id)
    b = Anchor(30000, p.tracks[0].id, "3/0")
    p.notes.append(Note("Setup", a, b))
    s.move(1, 28000, p.duration)
    assert p.resolve(a) == 28000
    p.breaks = [[31000, 50000], [65000, 100000]]
    axis = Axis(p, 1610)
    assert all(axis.t(axis.x(t)) == t for t in range(0, p.duration, 83))
    f = tmp_path / "bound.wfg"
    save(p, f)
    loaded = load(f)
    assert loaded.resolve(loaded.notes[0].a) == 28000
    assert ticks("0.000001", "ms") == 1000 and fmt(1500) == "1.5"


def test_failed_save_preserves_file(tmp_path):
    p = Project()
    f = tmp_path / "safe.wfg"
    save(p, f)
    p.duration = -1
    with pytest.raises(ValueError):
        save(p, f)
    assert load(f).duration == 100000


def test_csv_and_cropped_vcd(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("time_ns,valid,data[15:0]\n0,0,0x1234\n10,1,0x5678\n")
    p = read_csv(f)
    assert p.tracks[1].state(10000) == "22136"
    v = tmp_path / "clock.vcd"
    v.write_text(
        "$timescale 1 ns $end\n$scope module main $end\n$var wire 1 ! clk $end\n$var wire 2 @ bus $end\n$upscope $end\n$enddefinitions $end\n$dumpvars\n0! b10 @\n$end\n#5 1! #10 0! #15 1! #20 0! #25 1!\n"
    )
    p = read_vcd(v)
    assert p.tracks[0].kind == "clock" and p.tracks[0].state(5000) == "1"
    p = read_vcd(v, 6000, 14000)
    assert (
        p.duration == 8001
        and p.tracks[0].state(0) == "1"
        and p.tracks[0].state(4000) == "0"
    )


def test_malformed_bindings_rejected():
    from app.services.templates import example

    data = example().data()
    data["notes"][0]["a"]["track"] = []
    with pytest.raises(ValueError):
        Project.parse(data)
    data = example().data()
    data["notes"][0]["b"]["edge"] = "9" * 5000 + "/0"
    with pytest.raises(ValueError):
        Project.parse(data)
