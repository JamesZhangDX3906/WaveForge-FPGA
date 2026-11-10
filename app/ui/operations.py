from copy import deepcopy
from decimal import Decimal
from PySide6.QtWidgets import QInputDialog
from app.core.model import (
    Track,
    Note,
    COLORS,
    NOTE_TYPES,
    uid,
    STATES,
    UNITS,
    fmt,
    ticks,
)
from app.ui.widgets import Fields, dialog, label
from PySide6.QtWidgets import QPushButton


def options(value, choices):
    return [value, *[x for x in choices if x != value]]


class Operations:
    def set_duration(self):
        tr = self.tr2
        v = dialog(
            self,
            tr("设置波形结束时间", "Set waveform end time"),
            [
                ("end", tr("结束时间", "End time"), fmt(self.p.duration, self.p.unit)),
                ("unit", tr("时间单位", "Time unit"), options(self.p.unit, UNITS)),
            ],
        )
        if not v:
            return
        previous = self.p.duration

        def change():
            end = ticks(v["end"], v["unit"])
            if not 1 <= end <= 10**15:
                raise ValueError(
                    tr(
                        "结束时间须在 1 ps 到 1000 s 之间",
                        "End time must be between 1 ps and 1000 s",
                    )
                )
            self.p.duration = end

        self.edit("Set waveform end time", change)
        if self.p.duration != previous:
            self.fit()

    def tracks_selected(self):
        return [s for s in self.p.tracks if s.id in self.selected]

    def reorder_tracks(self, ids, target=None, after=False, group=None):
        self.edit(
            "Reorder channels", lambda: self.p.reorder_tracks(ids, target, after, group)
        )

    def toggle_clock_guide(self, mode):
        clocks = [
            s for s in self.tracks_selected() if s.kind == "clock" and not s.locked
        ]
        if not clocks:
            reference = self.p.reference_clock()
            clocks = [reference] if reference and not reference.locked else []

        def change():
            enable = not all(mode in self.p.guides_for(s) for s in clocks)
            colors = {s.id: self.p.guide_color_for(s) for s in clocks}
            for s in clocks:
                if not s.guide_color:
                    s.guide_color = colors[s.id]
                modes = list(self.p.guides_for(s))
                s.guide_modes = (
                    list(dict.fromkeys([*modes, mode]))
                    if enable
                    else [m for m in modes if m != mode]
                )

        self.edit("Clock guides", change)

    def set_clock_cycle_guides(self, enabled, ident=None):
        clocks = [s for s in self.p.tracks if s.kind == "clock"]
        if not clocks:
            return self.info("请先添加时钟", "Add a clock first")
        if ident is None:
            names = {f"{i + 1} · {s.name}": s.id for i, s in enumerate(clocks)}
            selected = next(
                (name for name, key in names.items() if key in self.selected),
                next(iter(names)),
            )
            choice = dialog(
                self,
                (
                    self.tr2("添加指定时钟的周期参考线", "Add cycle guides for a clock")
                    if enabled
                    else self.tr2(
                        "删除指定时钟的所有周期参考线",
                        "Delete all cycle guides for a clock",
                    )
                ),
                [("clock", self.tr2("指定时钟", "Clock"), options(selected, names))],
            )
            if not choice:
                return
            ident = names[choice["clock"]]
        track = self.p.track(ident)
        if track is None or track.kind != "clock":
            return

        def change():
            if enabled:
                if not track.guide_color:
                    track.guide_color = self.p.guide_color_for(track)
                track.guide_modes = list(
                    dict.fromkeys([*self.p.guides_for(track), "cycle"])
                )
            else:
                track.guide_modes = []
            track.hidden_guides.clear()

        self.edit(
            "Add clock cycle guides" if enabled else "Delete clock cycle guides", change
        )

    def add(self, kind):
        tr = self.tr2
        default = {"clock": "clk", "signal": "valid", "bus": "data"}[kind]
        name = default
        while any(s.name == name for s in self.p.tracks):
            name += "_1"
        fields = [("name", tr("名称", "Name"), name)]
        if kind == "clock":
            fields += [("freq", "MHz", "100"), ("duty", tr("占空比 %", "Duty %"), 50)]
        if kind == "bus":
            fields.append(("width", tr("位宽", "Width"), 16))
        v = dialog(self, tr("添加通道", "Add channel"), fields)
        if not v:
            return

        def change():
            s = Track(v["name"], kind, color=COLORS[len(self.p.tracks) % len(COLORS)])
            if kind == "clock":
                s.period = round(Decimal(1000000) / Decimal(v["freq"]))
                s.duty = int(v["duty"])
            if kind == "bus":
                s.width = int(v["width"])
            self.p.tracks.append(s)
            self.selected = [s.id]

        self.edit("Add channel", change)

    def edit_value(self, s, t, insert=False):
        if s.locked:
            return
        i = s.index(t)
        if s.kind == "bus":
            value, ok = QInputDialog.getText(
                self,
                s.name,
                self.tr2("区段数值", "Segment value"),
                text=s.display(s.edges[i].value),
            )
            if not ok:
                return
            if not insert:
                t = s.edges[i].t
            else:
                t = self.view.snap(t)
        else:
            value, ok = QInputDialog.getItem(
                self,
                s.name,
                self.tr2("逻辑状态", "Logic state"),
                STATES,
                0 if s.state(t) == "1" else 1,
                False,
            )
            if not ok:
                return
            if s.invert:
                value = {"1": "0", "0": "1", "H": "L", "L": "H"}.get(value, value)
            t = self.view.snap(t)
        self.edit("Set value", lambda: s.put(t, value, self.p.duration))

    def remove_edge(self, s, i):
        if s.locked or i == 0:
            return

        def change():
            e = s.edges.pop(i)
            for n in self.p.notes:
                for a in (n.a, n.b):
                    if a.track == s.id and a.edge == e.id:
                        a.t, a.edge = e.t, ""

        self.edit("Delete edge", change)

    def delete(self):
        if self.note_id:
            self.edit(
                "Delete annotation",
                lambda: setattr(
                    self.p, "notes", [n for n in self.p.notes if n.id != self.note_id]
                ),
            )
            return
        ids = {s.id for s in self.tracks_selected() if not s.locked}
        if self.edge_id and len(ids) == 1:
            s = self.p.track(next(iter(ids)))
            for i, e in enumerate(s.edges):
                if e.id == self.edge_id:
                    return self.remove_edge(s, i)

        def change():
            self.p.notes = [
                n for n in self.p.notes if n.a.track not in ids and n.b.track not in ids
            ]
            self.p.tracks = [s for s in self.p.tracks if s.id not in ids]

        self.edit("Delete channels", change)

    def copy(self):
        tracks = self.tracks_selected()
        ids = {s.id for s in tracks}
        notes = [
            n
            for n in self.p.notes
            if n.id == self.note_id
            or (
                (n.a.track in ids or n.b.track in ids)
                and all(not a.track or a.track in ids for a in (n.a, n.b))
            )
        ]
        self.clip = deepcopy((tracks, notes))
        for note in self.clip[1]:
            for a in (note.a, note.b):
                a.t = self.p.resolve(a)

    def paste(self):
        if not self.clip:
            return

        def change():
            tracks, notes = deepcopy(self.clip)
            self.selected = []
            self.note_id = ""
            track_ids = {}
            edge_ids = {}
            for s in tracks:
                old = s.id
                s.id = uid()
                track_ids[old] = s.id
                s.name += "_copy"
                for e in s.edges:
                    old = e.id
                    e.id = uid()
                    edge_ids[old] = e.id
                self.p.tracks.append(s)
                self.selected.append(s.id)
            for n in notes:
                n.id = uid()
                for a in (n.a, n.b):
                    a.track = track_ids.get(a.track, a.track)
                    a.edge = edge_ids.get(a.edge, a.edge)
                    s = self.p.track(a.track)
                    if not s or (
                        s.kind != "clock"
                        and a.edge
                        and not any(e.id == a.edge for e in s.edges)
                    ):
                        a.track = a.edge = ""
                    a.t = max(0, min(a.t, self.p.duration))
                self.p.notes.append(n)
                if not tracks:
                    self.note_id = n.id

        self.edit("Paste", change)

    def group(self):
        name, ok = QInputDialog.getText(
            self, self.tr2("信号分组", "Signal group"), self.tr2("组名", "Group name")
        )
        if ok:
            self.edit(
                "Group",
                lambda: [
                    setattr(s, "group", name.strip())
                    for s in self.tracks_selected()
                    if not s.locked
                ],
            )

    def lock(self):
        rows = self.tracks_selected()
        if rows:
            target = not all(s.locked for s in rows)
            self.edit("Lock", lambda: [setattr(s, "locked", target) for s in rows])

    def align(self):
        rows = [s for s in self.tracks_selected() if not s.locked]
        clocks = [s for s in self.p.tracks if s.kind == "clock"]
        if not rows:
            return self.info("请选择未锁定的通道", "Select unlocked channels")
        tr = self.tr2
        modes = [
            tr("对齐上升沿", "Rising edge"),
            tr("对齐下降沿", "Falling edge"),
            tr("按周期平移", "Shift by cycles"),
            tr("整体延迟", "Delay"),
        ]
        names = [f"{i+1} · {s.name}" for i, s in enumerate(clocks)]
        fields = [
            ("mode", tr("操作", "Action"), modes if clocks else modes[-1:]),
            ("offset", tr("偏移 ps", "Offset ps"), 0),
        ]
        if clocks:
            fields.insert(0, ("ref", tr("参考时钟", "Reference"), names))
            fields.append(("cycles", tr("周期数", "Cycles"), 1))
        v = dialog(self, tr("边沿对齐", "Align edges"), fields)
        if not v:
            return

        def change():
            ref = clocks[names.index(v["ref"])] if clocks else None
            mode = modes.index(v["mode"])
            offset = int(v["offset"])
            for s in rows:
                if mode < 2 and s.kind == "clock":
                    continue
                delta = offset + (int(v["cycles"]) * ref.cycle if mode == 2 else 0)
                if s.kind == "clock":
                    s.phase += delta
                else:
                    for e in s.edges[1:]:
                        if (
                            self.edge_id
                            and len(rows) == 1
                            and mode < 2
                            and e.id != self.edge_id
                        ):
                            continue
                        if mode >= 2:
                            e.t += delta
                        else:
                            origin = ref.phase + (
                                0
                                if (ref.start_high ^ ref.invert) == (mode == 0)
                                else ref.high
                            )
                            e.t = (
                                origin
                                + ((e.t - origin + ref.cycle // 2) // ref.cycle)
                                * ref.cycle
                                + offset
                            )

        self.edit("Align / shift", change)

    def hide_clock_guide(self, ident, key):
        track = self.p.track(ident)
        if track and not track.locked:
            self.edit(
                "Delete clock guide",
                lambda: setattr(
                    track,
                    "hidden_guides",
                    list(dict.fromkeys([*track.hidden_guides, key])),
                ),
            )

    def restore_clock_guides(self, ident):
        track = self.p.track(ident)
        if track and not track.locked:
            self.edit("Restore clock guides", lambda: track.hidden_guides.clear())

    def cursor(self, t, index=None):
        if index is None and t in self.p.cursors:
            self.view.active_cursor = self.p.cursors.index(t)
            return
        if index is None and len(self.p.cursors) == 2:
            index = min(range(2), key=lambda i: abs(self.p.cursors[i] - t))

        def change():
            if index is None:
                self.p.cursors.append(t)
                self.view.active_cursor = len(self.p.cursors) - 1
            else:
                self.p.cursors[index] = t
                self.view.active_cursor = index

        self.edit(
            "Measure",
            change,
        )

    def add_note(self, a, b):
        tr = self.tr2
        v = dialog(
            self,
            tr("添加标注", "Add annotation"),
            [
                ("kind", tr("类型", "Type"), list(NOTE_TYPES)),
                ("text", tr("文字", "Text"), ""),
            ],
        )
        if v:
            n = Note(v["kind"], a, b, v["text"])
            self.note_id = n.id
            self.edit("Add annotation", lambda: self.p.notes.append(n))

    def inspector(self):
        box = self.props
        while box.count():
            item = box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        tr = self.tr2
        n = next((n for n in self.p.notes if n.id == self.note_id), None)
        grid_modes = {
            "clock": tr("跟随首个可见时钟", "Follow first visible clock"),
            "manual": tr("固定时间间隔", "Fixed interval"),
        }
        rows = self.tracks_selected()
        s = rows[0] if rows else None
        if n:
            fields = [
                ("kind", tr("类型", "Type"), options(n.kind, NOTE_TYPES)),
                ("text", tr("文字", "Text"), n.text),
                ("a", "A · ps", self.p.resolve(n.a)),
                ("b", "B · ps", self.p.resolve(n.b)),
                ("font", tr("字体", "Font"), n.font),
                ("size", tr("字号", "Size"), n.size),
                ("weight", tr("线宽", "Line width"), n.weight),
                ("color", tr("颜色", "Color"), n.color),
                (
                    "arrows",
                    tr("箭头", "Arrows"),
                    options(n.arrows, ["both", "end", "none"]),
                ),
            ]
            title = n.kind
        elif s:
            title = s.name
            fields = [
                ("name", tr("名称", "Name"), s.name),
                ("group", tr("分组", "Group"), s.group),
                ("color", tr("颜色", "Color"), s.color),
            ]
            if s.kind == "clock":
                fields.extend(
                    [
                        ("period", tr("周期 ps", "Period ps"), s.period),
                        ("freq", "MHz", str(Decimal(1000000) / s.period)),
                        ("phase", tr("相位 ps", "Phase ps"), s.phase),
                        ("duty", tr("占空比 %", "Duty %"), s.duty),
                        ("divider", tr("分频", "Divider"), s.divider),
                        ("start_high", tr("起始高电平", "Starts high"), s.start_high),
                        (
                            "guide_rising",
                            tr("上升沿参考线", "Rising edge guides"),
                            "rising" in self.p.guides_for(s),
                        ),
                        (
                            "guide_falling",
                            tr("下降沿参考线", "Falling edge guides"),
                            "falling" in self.p.guides_for(s),
                        ),
                        (
                            "guide_cycle",
                            tr("周期参考线", "Cycle guides"),
                            "cycle" in self.p.guides_for(s),
                        ),
                        (
                            "guide_color",
                            tr("参考线颜色", "Guide color"),
                            self.p.guide_color_for(s),
                        ),
                    ]
                )
            elif s.kind == "bus":
                fields.extend(
                    [
                        ("width", tr("位宽", "Width"), s.width),
                        ("radix", tr("进制", "Radix"), options(s.radix, [2, 10, 16])),
                    ]
                )
            else:
                fields.extend(
                    [
                        ("slope", tr("边沿斜率时长 ps", "Slew time ps"), s.slope),
                        ("active_low", tr("低有效", "Active low"), s.active_low),
                    ]
                )
            if s.kind != "bus":
                fields.append(("invert", tr("反相", "Invert"), s.invert))
            if s.kind != "clock":
                e = next(
                    (e for e in s.edges if e.id == self.edge_id),
                    s.edges[s.index(self.mouse_t)],
                )
                fields.extend(
                    [
                        ("time", tr("区段起点 ps", "Segment start ps"), e.t),
                        ("value", tr("区段数值", "Segment value"), s.display(e.value)),
                    ]
                )
            fields.append(("locked", tr("锁定", "Locked"), s.locked))
        else:
            title = self.p.name
            fields = [
                ("name", tr("工程名称", "Project name"), self.p.name),
                ("duration", tr("结束 ps", "End ps"), self.p.duration),
                (
                    "grid_mode",
                    tr("网格基准", "Grid source"),
                    options(grid_modes[self.p.grid_mode], grid_modes.values()),
                ),
                ("step", tr("固定网格 ps", "Fixed grid ps"), self.p.step),
                (
                    "unit",
                    tr("单位", "Unit"),
                    options(self.p.unit, ["ps", "ns", "μs", "ms", "s"]),
                ),
                (
                    "style",
                    tr("绘图主题", "Plot style"),
                    options(self.p.style, ["engineering", "paper", "datasheet"]),
                ),
            ]
        box.addWidget(label(title, "heading"))
        box.addWidget(label(tr("对象参数", "OBJECT PROPERTIES"), "muted"))
        form = Fields(fields)
        box.addWidget(form)

        def apply():
            v = form.values()
            if s and not n and s.locked:
                if not v["locked"]:
                    return self.edit("Unlock", lambda: setattr(s, "locked", False))
                return

            def change():
                obj = n or s or self.p
                if not n and not s:
                    v["grid_mode"] = next(
                        key
                        for key, title in grid_modes.items()
                        if title == v["grid_mode"]
                    )
                if n:
                    for k in ("a", "b"):
                        t = int(v.pop(k))
                        anchor = getattr(n, k)
                        if t != self.p.resolve(anchor):
                            anchor.edge, anchor.t = "", t
                if s and not n and s.kind == "clock":
                    v["guide_modes"] = [
                        mode
                        for mode in ("rising", "falling", "cycle")
                        if v.pop("guide_" + mode)
                    ]
                    freq = v.pop("freq")
                    if Decimal(freq) != Decimal(1000000) / s.period:
                        v["period"] = round(Decimal(1000000) / Decimal(freq))
                if s and not n and s.kind != "clock":
                    t = int(v.pop("time"))
                    if e != s.edges[0] or t == 0:
                        e.t = t
                    val = v.pop("value")
                    if val != s.display(e.value):
                        e.value = s.normalize(val)
                for k, value in v.items():
                    current = getattr(obj, k)
                    setattr(obj, k, int(value) if type(current) is int else value)

            self.edit("Properties", change)

        button = QPushButton(tr("应用更改", "Apply changes"))
        button.clicked.connect(apply)
        box.addWidget(button)
        box.addStretch()
