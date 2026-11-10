from app.core.model import Project, Track, Edge, COLORS

TEMPLATES = (
    "AXI4-Stream",
    "Valid/Ready",
    "Synchronous reset",
    "Asynchronous reset",
    "Clock enable",
    "FIFO",
    "RAM",
    "SPI",
    "UART",
    "AXI4-Lite",
)


def template(name):
    p = Project(name=name, duration=120000)

    def add(n, kind="signal", times=(), values=(), width=1, group=""):
        s = Track(
            n, kind, width=width, color=COLORS[len(p.tracks) % len(COLORS)], group=group
        )
        if times:
            s.edges = [
                Edge(t * 1000, str(v)) for t, v in zip(times, values, strict=True)
            ]
        p.tracks.append(s)
        return s

    def bit(n, *changes):
        return add(
            n,
            times=(0, *changes),
            values=[i % 2 for i in range(len(changes) + 1)],
            group=name,
        )

    def bus(n, ts, vs):
        return add(n, "bus", ts, vs, 16, name)

    add("clk", "clock", group="System")
    reset = add(
        "rst_n",
        times=(0, 15 if name == "Asynchronous reset" else 20),
        values=(0, 1),
        group="System",
    )
    reset.active_low = True
    if name in ("AXI4-Stream", "Valid/Ready"):
        bit("valid", 25, 85, 95, 105)
        bit("ready", 35, 55, 75, 105)
        bus(
            "data",
            (0, 25, 45, 55, 85, 95, 105),
            ("X", 4660, 22136, 39612, "X", 57072, "X"),
        )
        if name == "AXI4-Stream":
            bit("tlast", 95, 105)
    elif name == "FIFO":
        bit("wr_en", 25, 55)
        bit("rd_en", 65, 95)
        bus("din", (0, 25, 35, 45), (0, 17, 34, 51))
        bus("dout", (0, 70, 80, 90), ("X", 17, 34, 51))
    elif name == "RAM":
        bit("wr_en", 25, 45)
        bus("addr", (0, 25, 35, 65, 75), (0, 16, 17, 16, 17))
        bus("din", (0, 25, 35), (0, 4660, 22136))
        bus("dout", (0, 70, 80), ("X", 4660, 22136))
    elif name == "SPI":
        add("cs_n", times=(0, 20, 100), values=(1, 0, 1))
        bit("sclk", *range(25, 105, 5))
        bit("mosi", 20, 40, 60, 70, 90, 100)
        bit("miso", 30, 50, 80, 90)
    elif name == "UART":
        add(
            "tx",
            times=(0, 10, 20, 30, 40, 50, 70, 90, 100),
            values=(1, 0, 1, 0, 1, 0, 1, 0, 1),
        )
    elif name == "AXI4-Lite":
        for n, ts in (
            ("awvalid", (25, 45)),
            ("awready", (35, 45)),
            ("wvalid", (25, 55)),
            ("wready", (45, 55)),
            ("bvalid", (55, 65)),
            ("bready", (55, 65)),
            ("arvalid", (65, 85)),
            ("arready", (75, 85)),
            ("rvalid", (85, 105)),
            ("rready", (95, 105)),
        ):
            bit(n, *ts)
        for n, v in (("awaddr", 16), ("wdata", 4660), ("araddr", 16), ("rdata", 4660)):
            bus(
                n,
                (0, {"awaddr": 25, "wdata": 25, "araddr": 65, "rdata": 85}[n]),
                (0, v),
            )
    elif name == "Clock enable":
        bit("enable", 25, 65)
        bit("q", 30, 40, 50, 60)
    else:
        reset.edges = [Edge(0, "1"), Edge(43000, "0"), Edge(68000, "1")]
        bit("d", 25, 95)
        bit("q", 30, 43 if name == "Asynchronous reset" else 50, 70, 100)
    return p


def example():
    from app.core.model import Anchor, Note

    p = template("AXI4-Stream")
    clk, _, valid, _, data = p.tracks[:5]
    p.notes = [
        Note(
            "Setup",
            Anchor(25000, valid.id, valid.edges[1].id),
            Anchor(30000, clk.id, "3/0"),
        ),
        Note(
            "Hold",
            Anchor(40000, clk.id, "4/0"),
            Anchor(45000, data.id, data.edges[2].id),
            color="#86aef3",
        ),
    ]
    return p
