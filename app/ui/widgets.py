import json
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QDrag, QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QLabel,
    QTreeWidget,
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QToolButton,
    QColorDialog,
)
from app.graphics.scene import ROW, HEADER


def label(text, style=""):
    w = QLabel(text)
    w.setObjectName(style)
    return w


class ColorField(QWidget):
    def __init__(self, value, title):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.edit = QLineEdit(str(value))
        self.edit.setMinimumWidth(65)
        self.button = QToolButton()
        self.button.setFixedSize(30, 28)
        self.button.setToolTip("打开调色盘 / Open color palette")
        self.button.setAccessibleName(title + " · 调色盘 / Color palette")
        self.button.clicked.connect(self.choose_color)
        self.edit.textChanged.connect(self.update_swatch)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)
        self.update_swatch()

    def text(self):
        return self.edit.text()

    def setText(self, text):
        self.edit.setText(text)

    def update_swatch(self):
        color = QColor(self.text())
        pixmap = QPixmap(18, 18)
        pixmap.fill(color if color.isValid() else Qt.transparent)
        self.button.setIcon(QIcon(pixmap))

    def choose_color(self):
        color = QColor(self.text())
        picker = QColorDialog(color if color.isValid() else QColor("#4f8cff"), self)
        picker.setWindowTitle("调色盘 / Color palette")
        picker.setOption(QColorDialog.DontUseNativeDialog, True)
        if picker.exec() == QDialog.Accepted:
            self.setText(picker.selectedColor().name(QColor.HexRgb))


class Fields(QWidget):
    def __init__(self, fields):
        super().__init__()
        self.controls = {}
        f = QFormLayout(self)
        f.setContentsMargins(0, 2, 0, 2)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for key, title, value in fields:
            if key in ("color", "guide_color"):
                w = ColorField(value, title)
            elif isinstance(value, list):
                w = QComboBox()
                w.addItems([str(x) for x in value])
            elif isinstance(value, bool):
                w = QCheckBox()
                w.setChecked(value)
            else:
                w = QLineEdit(str(value))
            self.controls[key] = w
            f.addRow(title, w)

    def values(self):
        return {
            k: (
                w.currentText()
                if isinstance(w, QComboBox)
                else w.isChecked() if isinstance(w, QCheckBox) else w.text()
            )
            for k, w in self.controls.items()
        }


def dialog(parent, title, fields):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    layout = QVBoxLayout(dlg)
    form = Fields(fields)
    layout.addWidget(form)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    return form.values() if dlg.exec() else None


class Names(QWidget):
    def __init__(self, w):
        super().__init__()
        self.w = w
        self.setMinimumWidth(62)
        self.press_pos = None
        self.drag_ids = []
        self.drop_slot = None
        self.setToolTip(
            w.tr2(
                "上下拖动信号名称可调整顺序", "Drag signal names vertically to reorder"
            )
        )

    def paintEvent(self, event):
        w = self.w
        c = w.scene
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(c.palette[0]))
        off = w.view.mapToScene(0, 0).y()
        p.setPen(QColor(c.palette[3]))
        p.drawText(12, int(27 - off), w.tr2("信号", "Signal"))
        for i, s in enumerate(c.rows):
            y = HEADER + i * ROW - off
            if y + ROW < 0 or y > self.height():
                continue
            if s.id == c.selected:
                p.fillRect(QRectF(0, y, self.width(), ROW), QColor(c.palette[5]))
            p.setPen(QColor(c.palette[1]))
            p.drawLine(0, int(y + ROW - 1), self.width(), int(y + ROW - 1))
            p.setPen(QColor(c.palette[4]))
            title = ("¬ " if s.active_low else "") + s.name
            p.drawText(
                QRectF(12, y, self.width() - 14, ROW),
                Qt.AlignVCenter,
                p.fontMetrics().elidedText(title, Qt.ElideRight, self.width() - 15),
            )
        if off > 0:
            p.fillRect(QRectF(0, 0, self.width(), HEADER), QColor(c.palette[0]))
            p.setPen(QColor(c.palette[3]))
            p.drawText(12, 27, w.tr2("信号", "Signal"))
        if self.drop_slot is not None:
            y = max(HEADER, HEADER + self.drop_slot * ROW - off)
            p.setPen(QPen(QColor("#4f8cff"), 2))
            p.drawLine(0, round(y), self.width(), round(y))

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or e.position().y() < HEADER:
            return
        y = e.position().y() + self.w.view.mapToScene(0, 0).y()
        i = int((y - HEADER) // ROW)
        if 0 <= i < len(self.w.scene.rows):
            ident = self.w.scene.rows[i].id
            if e.modifiers() & Qt.ControlModifier:
                self.w.select(ident, True)
            elif ident not in self.w.selected:
                self.w.select(ident)
            self.press_pos = e.position().toPoint()
            self.drag_ids = list(self.w.selected)

    def mouseMoveEvent(self, e):
        if self.press_pos is None or not e.buttons() & Qt.LeftButton:
            return
        if (
            e.position().toPoint() - self.press_pos
        ).manhattanLength() < QApplication.startDragDistance():
            return
        bar = self.w.view.verticalScrollBar()
        if e.position().y() < HEADER + 16:
            bar.setValue(bar.value() - ROW // 2)
        elif e.position().y() > self.height() - 16:
            bar.setValue(bar.value() + ROW // 2)
        y = e.position().y() + self.w.view.mapToScene(0, 0).y()
        self.drop_slot = max(
            0, min(len(self.w.scene.rows), int((y - HEADER + ROW / 2) // ROW))
        )
        self.setCursor(Qt.ClosedHandCursor)
        self.update()

    def mouseReleaseEvent(self, e):
        ids, slot = self.drag_ids, self.drop_slot
        self.press_pos = self.drop_slot = None
        self.drag_ids = []
        self.unsetCursor()
        self.update()
        rows = self.w.scene.rows
        if slot is not None and rows:
            target = rows[min(slot, len(rows) - 1)]
            self.w.reorder_tracks(ids, target.id, slot == len(rows), target.group)


class Tree(QTreeWidget):
    TRACK_MIME = "application/x-waveforge-tracks"

    def __init__(self, w):
        super().__init__()
        self.w = w
        self.setHeaderHidden(True)
        self.setIndentation(12)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)

    def startDrag(self, supported_actions):
        ids = [s.id for s in self.w.tracks_selected()]
        if not ids or any(self.w.p.track(i).locked for i in ids):
            return
        mime = self.model().mimeData(self.selectedIndexes())
        mime.setData(self.TRACK_MIME, json.dumps(ids).encode("utf8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        # The edit command owns the move. QAbstractItemView must not remove rows
        # from the refreshed tree after the drop has rebuilt its items.
        drag.exec(Qt.MoveAction)

    def dropEvent(self, e):
        if e.source() is not self or not e.mimeData().hasFormat(self.TRACK_MIME):
            e.ignore()
            return
        target = self.itemAt(e.position().toPoint())
        ids = json.loads(bytes(e.mimeData().data(self.TRACK_MIME)))
        if (
            target
            and target.data(0, Qt.UserRole)
            and not self.w.p.track(target.data(0, Qt.UserRole))
        ):
            e.ignore()
            return
        dest = self.w.p.track(target.data(0, Qt.UserRole)) if target else None
        group = dest.group if dest else target.text(0) if target else None
        after = bool(
            dest and e.position().y() >= self.visualItemRect(target).center().y()
        )
        self.w.reorder_tracks(ids, dest.id if dest else None, after, group)
        e.setDropAction(Qt.MoveAction)
        e.accept()
