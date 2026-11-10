from bisect import bisect_left
from math import ceil, floor
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF
from PySide6.QtGui import (
    QColor,
    QPen,
    QBrush,
    QPainterPath,
    QFont,
    QPolygonF,
    QPainterPathStroker,
    QFontMetricsF,
)
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItem
from app.core.model import fmt

HEADER, ROW = 46, 58
DARK = ("#151922", "#29303e", "#3c4659", "#aab5c8", "#e4ebf5", "#202936")
LIGHT = ("#ffffff", "#e7ecf1", "#cbd3dd", "#556272", "#243246", "#eaf3ff")


def pen(color, width=1, style=Qt.SolidLine):
    return QPen(QColor(color), width, style)


def line(p, x, y, x2, y2):
    p.drawLine(QLineF(x, y, x2, y2))


class Axis:
    def __init__(self, project, width, start=0, end=None):
        self.project = project
        self.width = width
        self.mark = max(1, project.step // 3)
        self.origin = self.compressed(start)
        self.span = (
            self.compressed(project.duration if end is None else end) - self.origin
        )

    def compressed(self, t):
        removed = 0
        for a, b in self.project.breaks:
            if t <= a:
                break
            mark = min(self.mark, b - a)
            if t < b:
                return a - removed + (t - a) * mark / (b - a)
            removed += b - a - mark
        return t - removed

    def x(self, t):
        return (self.compressed(t) - self.origin) * self.width / self.span

    def t(self, x):
        u = self.origin + x * self.span / self.width
        for a, b in self.project.breaks:
            if u <= a:
                break
            mark = min(self.mark, b - a)
            if u < a + mark:
                u = a + (u - a) * (b - a) / mark
                break
            u += b - a - mark
        return max(0, min(self.project.duration, round(u)))


class RowItem(QGraphicsItem):
    def __init__(self, scene, s):
        super().__init__()
        self.canvas, self.s = scene, s
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption)

    def boundingRect(self):
        return QRectF(0, 0, self.canvas.axis.width, ROW)

    def paint(self, p, opt, widget=None):
        c, s = self.canvas, self.s
        axis = c.axis
        rect = opt.exposedRect.intersected(self.boundingRect())
        lo, hi = axis.t(rect.left()), axis.t(rect.right())
        if s.id == c.selected and not c.exporting:
            p.fillRect(rect, QColor(c.palette[5]))
        color = QColor(s.color)
        if c.paper:
            color = color.darker(170)
        if c.project.style == "datasheet":
            color = QColor("#30382e")
        p.setPen(pen(c.palette[1]))
        line(p, rect.left(), ROW - 1, rect.right(), ROW - 1)
        if s.kind == "clock" and axis.x(lo + s.cycle) - axis.x(lo) < 2:
            p.fillRect(
                QRectF(rect.left(), 18, rect.width(), 23),
                QBrush(color, Qt.Dense4Pattern),
            )
            return
        if s.kind == "clock":
            edges = ((t, v) for t, v, _ in c.visible_clock(s, lo + 1, hi))
            first = lo
        else:
            i = s.index(lo)
            first = s.edges[i].t
            end = min(len(s.edges), bisect_left(s.edges, hi, key=lambda e: e.t) + 1)
            if end - i > max(100, rect.width() * 3):
                self.paint_dense(p, rect, lo, hi, color)
                return
            edges = ((s.edges[j].t, s.state(s.edges[j].t)) for j in range(i + 1, end))
        v = s.state(lo)
        last = axis.x(first)

        def level(v):
            return 16 if v in ("1", "H") else 41 if v in ("0", "L") else 29

        def segment(x, y, v):
            x = max(-8, x)
            y = min(axis.width + 8, y)
            if y <= x:
                return
            if s.kind == "bus" or v in ("X", "C", "INVALID"):
                d = min(5, (y - x) / 2)
                poly = QPolygonF(
                    [
                        QPointF(x, 29),
                        QPointF(x + d, 16),
                        QPointF(y - d, 16),
                        QPointF(y, 29),
                        QPointF(y - d, 41),
                        QPointF(x + d, 41),
                    ]
                )
                fill = QColor(color)
                fill.setAlpha(35)
                p.setBrush(
                    QBrush(
                        fill,
                        (
                            Qt.BDiagPattern
                            if v in ("X", "C", "INVALID")
                            else Qt.SolidPattern
                        ),
                    )
                )
                p.setPen(pen(color, c.stroke))
                p.drawPolygon(poly)
                p.setBrush(Qt.NoBrush)
                label = s.display(v)
                if p.fontMetrics().horizontalAdvance(label) + 12 < y - x:
                    p.drawText(QRectF(x, 16, y - x, 25), Qt.AlignCenter, label)
            else:
                p.setPen(
                    pen(
                        color,
                        c.stroke,
                        Qt.DashLine if v in ("Z", "H", "L") else Qt.SolidLine,
                    )
                )
                line(p, x, level(v), y, level(v))
                if v == "G":
                    line(p, x, 41, x + min(3, y - x), 16)
                    line(p, x + min(3, y - x), 16, x + min(6, y - x), 41)

        p.setFont(QFont(c.fontname, 9))
        for t, nv in edges:
            x = axis.x(t)
            segment(last, x, v)
            last = x
            if s.kind != "bus":
                last = axis.x(min(c.project.duration, t + s.slope))
                if s.kind != "clock":
                    idx = s.index(t) + 1
                    if idx < len(s.edges):
                        last = min(last, axis.x(s.edges[idx].t))
                p.setPen(pen(color, c.stroke))
                line(p, x, level(v), last, level(nv))
            v = nv
        right = axis.width
        if s.kind != "clock" and end < len(s.edges):
            right = axis.x(s.edges[end].t)
        segment(last, right, v)
        if c.edge and c.edge[0] == s.id and not c.exporting:
            p.setBrush(color)
            p.drawEllipse(QPointF(axis.x(c.edge[1]), 29), 4, 4)

    def paint_dense(self, p, rect, lo, hi, color):
        """Aggregate subpixel transitions per visible device column."""
        axis = self.canvas.axis
        s = self.s
        p.setPen(pen(color, self.canvas.stroke))
        for x in range(floor(rect.left()), ceil(rect.right()) + 1):
            start, end = axis.t(x), axis.t(x + 1)
            i, j = s.index(start), s.index(end)
            if i != j or s.kind == "bus":
                line(p, x, 16, x, 41)
            else:
                v = s.state(start)
                y = 16 if v in ("1", "H") else 41 if v in ("0", "L") else 29
                line(p, x, y, x + 1, y)


class TimingScene(QGraphicsScene):
    def __init__(self, project, width=1000, light=False):
        super().__init__()
        self.selected = ""
        self.note_id = ""
        self.edge = None
        self.exporting = False
        self.transparent = False
        self.stroke = 2
        self.fontname = "Segoe UI"
        self.grid_override = None
        self.reset(project, width, light)

    def reset(self, project, width, light=False):
        self.clear()
        self.project = project
        self.axis = Axis(project, width)
        self.paper = light or project.style != "engineering"
        self.palette = LIGHT if self.paper else DARK
        if project.style == "datasheet":
            self.palette = (
                "#fffef5",
                "#ddd8c6",
                "#b8b4a4",
                "#565448",
                "#1e211e",
                "#ebeada",
            )
        self.rows = [
            s for s in project.tracks if s.visible and s.group not in project.collapsed
        ]
        self.items_by_id = {}
        for i, s in enumerate(self.rows):
            item = RowItem(self, s)
            self.addItem(item)
            item.setY(HEADER + i * ROW)
            self.items_by_id[s.id] = item
        self.setSceneRect(
            0,
            0,
            width,
            HEADER + ROW * len(self.rows) + max(46, 32 * len(project.notes) + 18),
        )
        self.invalidate()

    def resize_axis(self, width):
        for item in self.items_by_id.values():
            item.prepareGeometryChange()
        self.axis = Axis(self.project, width)
        self.setSceneRect(0, 0, width, self.sceneRect().height())
        self.invalidate()

    def grid_ticks(self, lo, hi):
        """Use the same clock-derived grid for screen and vector exports."""
        a = self.axis
        step, origin, cycle = self.project.grid_parameters()
        while step * a.width / a.span < 12:
            step *= 2
        label_every = next(
            (k for k in (1, 2, 5, 10) if k * step * a.width / a.span >= 68), 10
        )
        # Labels stay on full cycles when half-cycle subdivisions are visible.
        if step < cycle:
            label_every = ((label_every + 1) // 2) * 2
        t = origin + ((lo - origin) // step) * step
        while t <= hi:
            index = (t - origin) // step
            yield t, (t - origin) % cycle == 0, index % label_every == 0
            jump = next((b for start, b in self.project.breaks if start <= t < b), None)
            t = (
                origin + ((jump - origin + step - 1) // step) * step
                if jump
                else t + step
            )

    def drawBackground(self, p, r):
        if not self.transparent:
            p.fillRect(r, QColor(self.palette[0]))
        a = self.axis
        lo, hi = a.t(r.left()), a.t(r.right())
        p.setFont(QFont(self.fontname, 9))
        show_grid = (
            self.project.grid if self.grid_override is None else self.grid_override
        )
        for t, large, show_label in self.grid_ticks(lo, hi):
            x = a.x(t)
            if show_grid:
                p.setPen(pen(self.palette[2 if large else 1], 1, Qt.DotLine))
                line(p, x, HEADER, x, self.sceneRect().bottom())
            if show_label:
                p.setPen(pen(self.palette[3]))
                p.drawText(
                    QPointF(x + 4, 27),
                    fmt(t, self.project.unit) + " " + self.project.unit,
                )

    def visible_clock(self, track, lo, hi):
        for a, b in self.project.breaks:
            if b < lo:
                continue
            if a > hi:
                break
            yield from track.clock_edges(lo, min(a, hi))
            lo = max(lo, b)
            if lo <= hi:
                yield lo, track.state(lo), "break"
        yield from track.clock_edges(lo, hi)

    def note_points(self, n, i):
        y = HEADER + ROW * len(self.rows) + 20 + 32 * i

        def point(a):
            item = self.items_by_id.get(a.track)
            return QPointF(
                self.axis.x(self.project.resolve(a)), item.y() + 29 if item else y
            )

        return point(n.a), point(n.b), y

    def arrow_path(self, n, a, b):
        path = QPainterPath(a)
        if n.kind == "Bezier":
            mid = (a.x() + b.x()) / 2
            path.cubicTo(mid, a.y(), mid, b.y(), b.x(), b.y())
        else:
            if n.kind == "Polyline":
                path.lineTo(b.x(), a.y())
            path.lineTo(b)
        return path

    def note_at(self, pos):
        for i, n in reversed(list(enumerate(self.project.notes))):
            a, b, y = self.note_points(n, i)
            if (
                abs(pos.y() - y) < 14
                and min(a.x(), b.x()) - 6 <= pos.x() <= max(a.x(), b.x()) + 100
            ):
                return n
            if n.kind in ("Arrow", "Polyline", "Bezier"):
                stroker = QPainterPathStroker()
                stroker.setWidth(max(8, n.weight + 4))
                if stroker.createStroke(self.arrow_path(n, a, b)).contains(pos):
                    return n
            elif n.kind in ("Text", "Omission"):
                bounds = QFontMetricsF(QFont(n.font, n.size)).boundingRect(
                    n.text if n.kind == "Text" else "//"
                )
                if bounds.translated(a).adjusted(-3, -3, 3, 3).contains(pos):
                    return n
            elif n.kind == "Separator" and abs(pos.y() - (a.y() + 24)) < 4:
                return n
        return None

    def guide_lines(self, lo, hi):
        for s in self.rows:
            if s.kind != "clock":
                continue
            modes = self.project.guides_for(s)
            if modes and self.axis.width * s.cycle / self.axis.span > 6:
                hidden = set(s.hidden_guides)
                for t, v, key in self.visible_clock(s, lo, hi):
                    if (
                        key != "break"
                        and key not in hidden
                        and (
                            ("cycle" in modes and key.endswith("/0"))
                            or ("rising" in modes and v == "1")
                            or ("falling" in modes and v == "0")
                        )
                    ):
                        yield s, t, key

    def drawForeground(self, p, r):
        for s, t, key in self.guide_lines(
            self.axis.t(r.left()), self.axis.t(r.right())
        ):
            ink = QColor(self.project.guide_color_for(s))
            if self.paper:
                ink = ink.darker(155)
            p.setPen(pen(ink, 1, Qt.DashLine))
            x = self.axis.x(t)
            line(p, x, HEADER, x, self.sceneRect().height())
        for i, n in enumerate(self.project.notes):
            a, b, y = self.note_points(n, i)
            ink = QColor(n.color).darker(155) if self.paper else QColor(n.color)
            p.setPen(pen(ink, n.weight))
            p.setFont(QFont(n.font, n.size))
            x, z = a.x(), b.x()
            if self.note_id == n.id and not self.exporting:
                p.setBrush(QColor(n.color))
                for pt in (a, b):
                    p.drawEllipse(pt, 5, 5)
                p.setBrush(Qt.NoBrush)
            if n.kind == "Invalid":
                p.fillRect(
                    QRectF(min(x, z), HEADER, abs(z - x), y - HEADER),
                    QBrush(QColor(n.color), Qt.BDiagPattern),
                )
            elif n.kind in ("Arrow", "Polyline", "Bezier"):
                path = self.arrow_path(n, a, b)
                p.drawPath(path)
                from math import atan2, cos, sin

                for show, tip, tail in [
                    (n.arrows in ("end", "both"), b, path.pointAtPercent(0.98)),
                    (n.arrows == "both", a, path.pointAtPercent(0.02)),
                ]:
                    if show:
                        angle = atan2(tip.y() - tail.y(), tip.x() - tail.x())
                        for delta in (-0.48, 0.48):
                            line(
                                p,
                                tip.x(),
                                tip.y(),
                                tip.x() - 8 * cos(angle + delta),
                                tip.y() - 8 * sin(angle + delta),
                            )
            elif n.kind == "Separator":
                line(p, 0, a.y() + 24, self.axis.width, a.y() + 24)
            elif n.kind == "Omission":
                p.drawText(a, "//")
            elif n.kind == "Text":
                p.drawText(a, n.text)
            else:
                line(p, x, y, z, y)
                sign = 1 if z >= x else -1
                for xx, anchor, d, show in (
                    (x, a, sign, n.arrows == "both"),
                    (z, b, -sign, n.arrows in ("end", "both")),
                ):
                    p.setPen(pen(ink, 1, Qt.DotLine))
                    line(p, xx, anchor.y(), xx, y)
                    p.setPen(pen(ink, n.weight))
                    if show:
                        for dy in (-4, 4):
                            line(p, xx, y, xx + d * 6, y + dy)
            if n.kind != "Text":
                p.drawText(
                    QPointF(min(x, z) + 4, y - 4),
                    n.text
                    or n.kind
                    + "  "
                    + fmt(
                        abs(self.project.resolve(n.b) - self.project.resolve(n.a)),
                        self.project.unit,
                    )
                    + " "
                    + self.project.unit,
                )
        self.draw_cursors(p)
        for a, b in self.project.breaks:
            p.setPen(pen(self.palette[4], 2))
            p.drawText(QPointF(self.axis.x(a), 39), "//")

    def draw_cursors(self, p, bottom=None):
        bottom = self.sceneRect().height() if bottom is None else bottom
        for i, t in enumerate(self.project.cursors):
            x = self.axis.x(t)
            col = ("#52b7ef", "#f4ad6e")[i]
            p.setPen(pen(col, 1, Qt.DashLine))
            line(p, x, HEADER, x, bottom)
            # Separate handle lanes keep both cursors selectable even at Δt = 0.
            p.setPen(pen(col))
            p.setBrush(QColor(self.palette[0]))
            rect = QRectF(x - 6, 18 + i * 13, 14, 13)
            p.drawRect(rect)
            p.drawText(rect, Qt.AlignCenter, "AB"[i])
            p.setBrush(Qt.NoBrush)
