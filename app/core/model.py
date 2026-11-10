"""Editable timing model. All stored times are integer picoseconds."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from math import ceil
from uuid import uuid4
from colorsys import hsv_to_rgb
import re

UNITS = {"ps": 1, "ns": 1000, "μs": 10**6, "ms": 10**9, "s": 10**12}
STATES = ("0", "1", "X", "Z", "H", "L", "C", "G")
COLORS = ["#5dd9bf", "#f3b471", "#83afff", "#bc9afa", "#5dd9bf", "#e58dae"]


def uid():
    return uuid4().hex


def fmt(t, unit="ns"):
    return (
        f"{Decimal(t) / UNITS[unit]:f}".rstrip("0").rstrip(".")
        if t % UNITS[unit]
        else str(t // UNITS[unit])
    )


def ticks(value, unit):
    n = Decimal(str(value)) * UNITS[unit]
    if not n.is_finite() or n != n.to_integral_value():
        raise ValueError("时间精度为 1 ps / Resolution is 1 ps")
    return int(n)


@dataclass
class Edge:
    t: int = 0
    value: str = "0"
    id: str = field(default_factory=uid)


@dataclass
class Track:
    name: str
    kind: str = "signal"
    id: str = field(default_factory=uid)
    color: str = COLORS[0]
    edges: list[Edge] = field(default_factory=lambda: [Edge()])
    width: int = 1
    radix: int = 16
    period: int = 10000
    duty: int = 50
    phase: int = 0
    divider: int = 1
    invert: bool = False
    start_high: bool = True
    active_low: bool = False
    slope: int = 0
    locked: bool = False
    visible: bool = True
    group: str = ""
    guide_modes: list[str] | None = None
    guide_color: str = ""
    hidden_guides: list[str] = field(default_factory=list)

    @property
    def cycle(self):
        return self.period * self.divider

    @property
    def high(self):
        width = max(1, min(self.cycle - 1, self.cycle * self.duty // 100))
        return width if self.start_high else self.cycle - width

    def clock_edges(self, lo, hi):
        for i in range(
            (lo - self.phase) // self.cycle, (hi - self.phase) // self.cycle + 1
        ):
            for j, delta in enumerate((0, self.high)):
                t = self.phase + i * self.cycle + delta
                if lo <= t <= hi:
                    yield t, str(
                        int(self.start_high ^ self.invert ^ bool(j))
                    ), f"{i}/{j}"

    def index(self, t):
        return max(0, bisect_right(self.edges, t, key=lambda e: e.t) - 1)

    def state(self, t):
        if self.kind == "clock":
            return str(
                int(
                    (((t - self.phase) % self.cycle < self.high) == self.start_high)
                    ^ self.invert
                )
            )
        v = self.edges[self.index(t)].value
        return (
            {"0": "1", "1": "0", "L": "H", "H": "L"}.get(v, v)
            if self.invert and self.kind == "signal"
            else v
        )

    def normalize(self, value):
        s = str(value).strip().upper()
        if self.kind != "bus":
            if s not in STATES:
                raise ValueError("非法逻辑状态 / Invalid logic state")
            return s
        if s in ("X", "Z", "INVALID"):
            return s
        base = 0 if s.startswith(("0X", "0B")) else self.radix
        number = int(s, base)
        if not 0 <= number < 1 << self.width:
            raise ValueError("数值超出总线位宽 / Value exceeds bus width")
        return str(number)

    def display(self, value):
        if self.kind != "bus" or not value.isdecimal():
            return value
        n = int(value)
        return {
            16: lambda: f"0x{n:0{ceil(self.width/4)}X}",
            2: lambda: f"0b{n:0{self.width}b}",
            10: lambda: str(n),
        }[self.radix]()

    def put(self, t, value, end):
        if self.locked or self.kind == "clock" or not 0 <= t < end:
            raise ValueError("无法在此位置编辑 / Position is not editable")
        v = self.normalize(value)
        i = bisect_left(self.edges, t, key=lambda e: e.t)
        if i < len(self.edges) and self.edges[i].t == t:
            self.edges[i].value = v
        else:
            self.edges.insert(i, Edge(t, v))

    def move(self, i, t, end):
        if self.locked or i <= 0:
            return
        hi = self.edges[i + 1].t if i + 1 < len(self.edges) else end
        self.edges[i].t = max(self.edges[i - 1].t + 1, min(t, hi - 1))


@dataclass
class Anchor:
    t: int
    track: str = ""
    edge: str = ""


@dataclass
class Note:
    kind: str
    a: Anchor
    b: Anchor
    text: str = ""
    color: str = "#e9b977"
    size: int = 10
    weight: int = 2
    font: str = "Segoe UI"
    arrows: str = "both"
    id: str = field(default_factory=uid)


@dataclass
class Project:
    name: str = "Untitled"
    duration: int = 100000
    step: int = 5000
    unit: str = "ns"
    tracks: list[Track] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    cursors: list[int] = field(default_factory=list)
    collapsed: list[str] = field(default_factory=list)
    breaks: list[list[int]] = field(default_factory=list)
    grid: bool = True
    snap: bool = True
    style: str = "engineering"
    zoom: float = 1.0
    viewport_start: int = 0
    guides: list[str] = field(default_factory=list)
    version: int = 1
    grid_mode: str = "clock"

    def grid_parameters(self):
        """Return integer subdivision, origin and major period for the time grid."""
        if self.grid_mode == "clock":
            reference = self.reference_clock()
            if reference:
                cycle = reference.cycle
                subdivision = cycle // 2 if cycle % 2 == 0 else cycle
                return subdivision, reference.phase, cycle
        return self.step, 0, self.step

    def reference_clock(self):
        return next(
            (
                s
                for s in self.tracks
                if s.kind == "clock" and s.visible and s.group not in self.collapsed
            ),
            None,
        )

    def track(self, ident):
        return next((s for s in self.tracks if s.id == ident), None)

    def guides_for(self, track):
        if track.guide_modes is not None:
            return track.guide_modes
        return self.guides if track is self.reference_clock() else []

    def guide_color_for(self, track):
        used = {s.guide_color.lower() for s in self.tracks if s.guide_color}
        for index, s in enumerate(s for s in self.tracks if s.kind == "clock"):
            color = s.guide_color or s.color
            if not s.guide_color and color.lower() in used:
                color = next((c for c in COLORS if c.lower() not in used), "")
                if not color:
                    rgb = hsv_to_rgb((index * 0.61803398875) % 1, 0.55, 0.95)
                    color = "#" + "".join(f"{round(c * 255):02x}" for c in rgb)
            used.add(color.lower())
            if s is track:
                return color
        return track.color

    def reorder_tracks(self, identifiers, target=None, after=False, group=None):
        ids = set(identifiers)
        moving = [s for s in self.tracks if s.id in ids]
        if len(moving) != len(ids) or (target and not self.track(target)):
            raise ValueError("无效的排序目标 / Invalid reorder target")
        if not moving or target in ids or any(s.locked for s in moving):
            return
        remaining = [s for s in self.tracks if s.id not in ids]
        if target:
            index = next(i for i, s in enumerate(remaining) if s.id == target) + int(
                after
            )
        elif group is not None:
            index = next(
                (
                    i + 1
                    for i in range(len(remaining) - 1, -1, -1)
                    if remaining[i].group == group
                ),
                len(remaining),
            )
        else:
            index = len(remaining)
        if group is not None:
            for s in moving:
                s.group = group
        self.tracks = remaining[:index] + moving + remaining[index:]

    def resolve(self, a):
        s = self.track(a.track)
        if s and a.edge:
            if s.kind == "clock":
                cycle, half = map(int, a.edge.split("/"))
                return s.phase + cycle * s.cycle + half * s.high
            return next((e.t for e in s.edges if e.id == a.edge), a.t)
        return a.t

    def validate(self):
        def require(condition):
            if not condition:
                raise ValueError("工程数据无效 / Invalid project data")

        def integer(v, lo, hi):
            return type(v) is int and lo <= v <= hi

        require(self.version == 1 and isinstance(self.name, str) and self.unit in UNITS)
        require(integer(self.duration, 1, 10**15) and integer(self.step, 1, 10**15))
        require(self.grid_mode in ("clock", "manual"))
        require(
            isinstance(self.zoom, (int, float))
            and 0.25 <= self.zoom <= 4096
            and integer(self.viewport_start, 0, 10**15)
        )
        require(
            isinstance(self.guides, list)
            and all(x in ("rising", "falling", "cycle") for x in self.guides)
        )
        require(
            isinstance(self.collapsed, list)
            and all(isinstance(x, str) for x in self.collapsed)
        )
        require(self.style in ("engineering", "paper", "datasheet"))
        require(type(self.grid) is bool and type(self.snap) is bool)
        ids = set()
        for s in self.tracks:
            require(s.id not in ids and isinstance(s.name, str) and s.name.strip())
            require(
                isinstance(s.id, str)
                and all(
                    type(v) is bool
                    for v in (s.visible, s.locked, s.active_low, s.invert, s.start_high)
                )
            )
            ids.add(s.id)
            require(
                s.kind in ("signal", "clock", "bus")
                and integer(s.width, 1, 1024)
                and s.radix in (2, 10, 16)
            )
            require(
                integer(s.period, 2, 10**15)
                and integer(s.divider, 1, 10**9)
                and integer(s.duty, 1, 99)
            )
            require(integer(s.phase, -(10**15), 10**15) and integer(s.slope, 0, 10**15))
            require(
                re.fullmatch(r"#[a-fA-F0-9]{6}", s.color) and isinstance(s.group, str)
            )
            require(
                s.guide_modes is None
                or (
                    isinstance(s.guide_modes, list)
                    and all(
                        mode in ("rising", "falling", "cycle") for mode in s.guide_modes
                    )
                )
            )
            require(
                isinstance(s.guide_color, str)
                and (
                    not s.guide_color or re.fullmatch(r"#[a-fA-F0-9]{6}", s.guide_color)
                )
            )
            require(
                isinstance(s.hidden_guides, list)
                and all(
                    isinstance(key, str) and re.fullmatch(r"-?\d{1,16}/[01]", key)
                    for key in s.hidden_guides
                )
            )
            require(s.edges and s.edges[0].t == 0)
            last = -1
            for e in s.edges:
                if not integer(e.t, last + 1, self.duration - 1):
                    raise ValueError(
                        f"{s.name}: 跳变时间须严格递增且在工程范围内 / Transitions must increase within the timeline"
                    )
                require(isinstance(e.id, str) and e.id not in ids)
                ids.add(e.id)
                last = e.t
                if s.kind == "bus":
                    require(
                        e.value in ("X", "Z", "INVALID")
                        or (e.value.isdecimal() and int(e.value) < 1 << s.width)
                    )
                else:
                    require(e.value in STATES)
        require(
            len(self.cursors) <= 2
            and all(integer(t, 0, self.duration) for t in self.cursors)
        )
        require(isinstance(self.cursors, list) and isinstance(self.breaks, list))
        last = -1
        for a, b in self.breaks:
            require(
                integer(a, last + 1, self.duration - 1)
                and integer(b, a + 1, self.duration)
            )
            last = b
        for n in self.notes:
            require(
                isinstance(n.font, str)
                and n.arrows in ("none", "end", "both")
                and isinstance(n.id, str)
                and n.id not in ids
            )
            ids.add(n.id)
            require(
                n.kind in NOTE_TYPES
                and isinstance(n.text, str)
                and integer(n.size, 5, 72)
                and integer(n.weight, 1, 12)
            )
            require(re.fullmatch(r"#[a-fA-F0-9]{6}", n.color))
            for a in (n.a, n.b):
                require(isinstance(a.track, str) and isinstance(a.edge, str))
                s = self.track(a.track)
                require(integer(a.t, 0, self.duration) and (not a.track or s))
                if a.edge:
                    require(
                        s
                        and (
                            re.fullmatch(r"-?\d{1,16}/[01]", a.edge)
                            if s.kind == "clock"
                            else any(e.id == a.edge for e in s.edges)
                        )
                    )

    def data(self):
        return asdict(self)

    @classmethod
    def parse(cls, data):
        raw = dict(data)
        if raw.get("version") != 1:
            raise ValueError("不支持的文件版本 / Unsupported file version")
        raw["tracks"] = [
            Track(**{**s, "edges": [Edge(**e) for e in s["edges"]]})
            for s in raw["tracks"]
        ]
        raw["notes"] = [
            Note(**{**n, "a": Anchor(**n["a"]), "b": Anchor(**n["b"])})
            for n in raw.get("notes", [])
        ]
        p = cls(**raw)
        p.validate()
        return p


NOTE_TYPES = (
    "Setup",
    "Hold",
    "Clock-to-Q",
    "Interval",
    "Arrow",
    "Polyline",
    "Bezier",
    "Text",
    "Invalid",
    "Separator",
    "Omission",
)
