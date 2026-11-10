from bisect import bisect_left
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtWidgets import QGraphicsView, QRubberBand, QMenu, QApplication
from PySide6.QtGui import QPainter
from app.graphics.scene import HEADER, ROW
from app.core.model import Anchor, fmt
from app.commands.history import MoveEdge


class TimingView(QGraphicsView):
    def __init__(self, w, scene):
        super().__init__(scene)
        self.w = w
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.drag = self.pan = self.start = self.pending = self.note_drag = None
        self.band = QRubberBand(QRubberBand.Rectangle, self.viewport())
        self.mode = "select"
        self.cursor_drag = None
        self.active_cursor = 0
        self.setMinimumWidth(240)

    def cursor_at(self, pos):
        x = self.mapToScene(pos).x()
        candidates = []
        for i, t in enumerate(self.w.p.cursors):
            dx = abs(self.scene().axis.x(t) - x)
            handle = QRectF(
                self.mapFromScene(self.scene().axis.x(t), 0).x() - 7,
                18 + i * 13,
                16,
                13,
            )
            if handle.contains(pos):
                return i
            if self.mode == "measure" and pos.y() >= HEADER and dx <= 7:
                candidates.append((dx, i != self.active_cursor, i))
        return min(candidates)[2] if candidates else None

    def hit(self, pos):
        c = self.scene()
        p = self.mapToScene(pos)
        t = c.axis.t(p.x())
        i = int((p.y() - HEADER) // ROW)
        s = c.rows[i] if 0 <= i < len(c.rows) else None
        return s, t, p

    def candidates(self, s, t):
        if s.kind == "clock":
            return [
                (tt, edge)
                for tt, _, edge in s.clock_edges(
                    max(0, t - s.cycle), min(self.w.p.duration, t + s.cycle)
                )
            ]
        i = bisect_left(s.edges, t, key=lambda e: e.t)
        return [(e.t, e.id) for e in s.edges[max(0, i - 1) : i + 1]]

    def near(self, s, t):
        a = self.scene().axis
        if s:
            best = min(
                self.candidates(s, t),
                key=lambda e: abs(a.x(t) - a.x(e[0])),
                default=None,
            )
            if best and abs(a.x(t) - a.x(best[0])) <= 9:
                return best
        return None

    def snap(self, t, exclude=None):
        p = self.w.p
        if not p.snap:
            return t
        a = self.scene().axis
        step, origin, _ = p.grid_parameters()
        if self.drag and p.grid_mode == "clock" and p.reference_clock() is exclude:
            # Keep the drag's original lattice while the reference phase previews.
            origin = self.drag[3]
        grid_time = origin + ((t - origin + step // 2) // step) * step
        times = [max(0, min(p.duration, grid_time))]
        for s in self.scene().rows:
            if s != exclude:
                n = self.near(s, t)
                if n:
                    times.append(n[0])
        return min(times, key=lambda x: abs(a.x(x) - a.x(t)))

    def anchor(self, s, t):
        n = self.near(s, t)
        return (
            Anchor(n[0], s.id, n[1])
            if n and self.w.p.snap
            else Anchor(self.snap(t), s.id if s else "")
        )

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        s, t, p = self.hit(pos)
        if e.button() == Qt.MiddleButton:
            self.pan = pos
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        if e.modifiers() & Qt.ShiftModifier:
            self.start = pos
            self.band.setGeometry(QRect(pos, pos))
            self.band.show()
            return
        cursor = self.cursor_at(pos)
        if cursor is not None:
            self.active_cursor = cursor
            self.cursor_drag = (cursor, self.w.p.cursors[cursor], self.w.p.data(), pos)
            self.setCursor(Qt.SizeHorCursor)
            return
        if self.mode == "measure" or pos.y() < HEADER:
            self.w.cursor(self.snap(t))
            return
        if self.mode == "note":
            anchor = self.anchor(s, t)
            if self.pending is None:
                self.pending = anchor
                self.w.statusBar().showMessage(
                    self.w.tr2("请选择终点", "Choose end point")
                )
            else:
                first, self.pending = self.pending, None
                self.w.add_note(first, anchor)
            return
        for i, n in enumerate(self.w.p.notes):
            if n.id == self.w.note_id and e.modifiers() & Qt.AltModifier:
                a, b, _ = self.scene().note_points(n, i)
                for key, pt in (("a", a), ("b", b)):
                    if (pt - p).manhattanLength() < 10:
                        self.note_drag = n, key, self.w.p.data()
                        return
        note = self.scene().note_at(p)
        if note and not (s and self.near(s, t)):
            self.w.select_note(note.id)
            return
        if not s:
            return
        self.w.select(s.id, bool(e.modifiers() & Qt.ControlModifier))
        near = self.near(s, t)
        self.scene().edge = (s.id, near[0]) if near else None
        self.scene().items_by_id[s.id].update()
        self.w.edge_id = near[1] if near else ""
        self.w.inspector()
        if s.locked:
            return
        if self.mode == "draw":
            self.w.edit_value(s, t, insert=True)
        elif s.kind == "clock" or (near and near[0] > 0):
            i = s.index(near[0]) if near else 0
            self.drag = (s, i, t, s.phase, s.edges[i].t, near[0] if near else t)

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        s, t, p = self.hit(pos)
        self.w.pointer(t)
        if self.pan is not None:
            d = pos - self.pan
            self.pan = pos
            for bar, delta in [
                (self.horizontalScrollBar(), d.x()),
                (self.verticalScrollBar(), d.y()),
            ]:
                bar.setValue(bar.value() - delta)
        elif self.start is not None:
            self.band.setGeometry(QRect(self.start, pos).normalized())
        elif self.cursor_drag:
            index, original, before, start = self.cursor_drag
            if (pos - start).manhattanLength() >= QApplication.startDragDistance():
                offset = t - self.hit(start)[1]
                self.w.p.cursors[index] = self.snap(
                    max(0, min(self.w.p.duration, original + offset))
                )
                self.viewport().update()
                self.w.status()
        elif self.note_drag:
            note, key, _ = self.note_drag
            setattr(note, key, self.anchor(s, t))
            self.viewport().update()
        elif self.drag:
            tr, i, origin, phase, before, edge = self.drag
            target = self.snap(t - origin + edge, tr)
            if tr.kind == "clock":
                tr.phase = max(-(10**15), min(10**15, phase + target - edge))
            else:
                tr.move(i, target, self.w.p.duration)
            c = self.scene()
            c.edge = (tr.id, target if tr.kind == "clock" else tr.edges[i].t)
            c.items_by_id[tr.id].update()
            if self.w.p.notes or tr.kind == "clock":
                self.viewport().update()
        else:
            self.setCursor(
                Qt.SizeHorCursor
                if self.cursor_at(pos) is not None
                or (s and not s.locked and self.near(s, t))
                else Qt.CrossCursor if self.mode != "select" else Qt.ArrowCursor
            )

    def mouseReleaseEvent(self, e):
        if self.pan is not None:
            self.pan = None
            self.unsetCursor()
        elif self.start is not None:
            pos = e.position().toPoint()
            a, b = sorted((self.hit(self.start)[1], self.hit(pos)[1]))
            self.start = None
            self.band.hide()
            if b > a:
                self.w.zoom_range(a, b)
        elif self.cursor_drag:
            before = self.cursor_drag[2]
            self.cursor_drag = None
            self.w.commit(before, "Move measurement cursor")
        elif self.note_drag:
            before = self.note_drag[2]
            self.note_drag = None
            self.w.commit(before, "Move annotation endpoint")
        elif self.drag:
            s, i, _, phase, old, _ = self.drag
            self.drag = None
            old = phase if s.kind == "clock" else old
            new = s.phase if s.kind == "clock" else s.edges[i].t
            if old != new:
                self.w.history.push(MoveEdge(self.w, s.id, s.edges[i].id, old, new))
        else:
            super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if self.cursor_at(e.position().toPoint()) is not None:
            return
        s, t, _ = self.hit(e.position().toPoint())
        self.drag = None
        if self.mode == "select" and s and s.kind != "clock" and not s.locked:
            self.w.edit_value(s, t)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self.cursor_drag:
            before = self.cursor_drag[2]
            self.cursor_drag = None
            self.w.restore(before)
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        s, t, point = self.hit(e.pos())
        m = QMenu(self)
        axis = self.scene().axis
        for clock, time, key in self.scene().guide_lines(
            axis.t(point.x() - 7), axis.t(point.x() + 7)
        ):
            action = m.addAction(
                self.w.tr2("删除参考线", "Delete guide")
                + f" · {clock.name} · {fmt(time, self.w.p.unit)} {self.w.p.unit}",
                lambda checked=False, ident=clock.id, edge=key: self.w.hide_clock_guide(
                    ident, edge
                ),
            )
            action.setEnabled(not clock.locked)
        clock_id = s.id if s and s.kind == "clock" else None
        m.addAction(
            self.w.tr2("添加指定时钟的周期参考线…", "Add cycle guides for a clock…"),
            lambda: self.w.set_clock_cycle_guides(True, clock_id),
        )
        m.addAction(
            self.w.tr2(
                "删除指定时钟的所有周期参考线…", "Delete all cycle guides for a clock…"
            ),
            lambda: self.w.set_clock_cycle_guides(False, clock_id),
        )
        if s:
            self.w.select(s.id)
            if s.kind == "clock" and s.hidden_guides:
                action = m.addAction(
                    self.w.tr2(
                        "恢复此时钟已删除的参考线",
                        "Restore deleted guides for this clock",
                    ),
                    lambda: self.w.restore_clock_guides(s.id),
                )
                action.setEnabled(not s.locked)
            if not s.locked and s.kind != "clock":
                m.addAction(
                    self.w.tr2("插入跳变", "Insert transition"),
                    lambda: self.w.edit_value(s, t, True),
                )
                m.addAction(
                    self.w.tr2("删除区段起点", "Delete transition"),
                    lambda: self.w.remove_edge(s, s.index(t)),
                )
        m.addAction(
            self.w.tr2("放置测量游标", "Place cursor"),
            lambda: self.w.cursor(self.snap(t)),
        )
        for i in range(len(self.w.p.cursors)):
            m.addAction(
                self.w.tr2("移动浮标 ", "Move cursor ") + "AB"[i],
                lambda checked=False, index=i: self.w.cursor(self.snap(t), index),
            )
        m.exec(e.globalPos())

    def drawForeground(self, p, rect):
        super().drawForeground(p, rect)
        top = self.mapToScene(0, 0).y()
        if top > 0:
            p.save()
            p.translate(0, top)
            ruler = QRectF(rect.left(), 0, rect.width(), HEADER)
            p.setClipRect(ruler, Qt.IntersectClip)
            self.scene().drawBackground(p, ruler)
            self.scene().draw_cursors(p, HEADER)
            p.restore()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ShiftModifier:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - e.angleDelta().y())
        elif e.modifiers() & Qt.AltModifier:
            super().wheelEvent(e)
        else:
            pos = e.position().toPoint()
            self.w.zoom(
                1.25 if e.angleDelta().y() > 0 else 0.8, self.hit(pos)[1], pos.x()
            )
