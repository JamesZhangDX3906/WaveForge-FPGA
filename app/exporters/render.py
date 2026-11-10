from PySide6.QtCore import QRectF, QSize, QSizeF, QMarginsF, Qt
from PySide6.QtGui import (
    QImage,
    QPainter,
    QPdfWriter,
    QColor,
    QPageSize,
    QPageLayout,
    QFont,
)
from PySide6.QtSvg import QSvgGenerator
from app.graphics.scene import TimingScene, Axis, HEADER, ROW


def render(
    project,
    kind,
    path="",
    width=1600,
    lo=0,
    hi=None,
    background="dark",
    margin=20,
    grid=True,
    font="Segoe UI",
    stroke=2,
):
    hi = project.duration if hi is None else hi
    if not 0 <= lo < hi <= project.duration or width < 400 or margin > width // 5:
        raise ValueError("导出范围或尺寸无效 / Invalid export range or size")
    labels = 130
    usable = width - 2 * margin - labels
    c = TimingScene(project, usable, background == "white")
    c.axis = Axis(project, usable, lo, hi)
    c.grid_override = grid
    c.exporting = True
    c.transparent = background == "transparent"
    c.stroke = stroke
    c.fontname = font
    height = int(c.sceneRect().height() + 2 * margin)
    target = QRectF(margin + labels, margin, usable, c.sceneRect().height())
    if kind in ("png", "clipboard"):
        if width * height > 80_000_000:
            raise ValueError("图像过大 / Image too large")
        device = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        device.fill(Qt.transparent)
    elif kind == "svg":
        device = QSvgGenerator()
        device.setFileName(str(path))
        device.setSize(QSize(width, height))
        device.setViewBox(QRectF(0, 0, width, height))
    else:
        device = QPdfWriter(str(path))
        device.setResolution(96)
        device.setPageSize(
            QPageSize(
                QSizeF(width * 25.4 / 96, height * 25.4 / 96), QPageSize.Millimeter
            )
        )
        device.setPageMargins(QMarginsF(), QPageLayout.Millimeter)
    painter = QPainter(device)
    if not painter.isActive():
        raise OSError(str(path))
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        if not c.transparent:
            painter.fillRect(QRectF(0, 0, width, height), QColor(c.palette[0]))
        painter.setFont(QFont(font, 10))
        painter.setPen(QColor(c.palette[4]))
        for i, s in enumerate(c.rows):
            painter.drawText(
                QRectF(margin, margin + HEADER + i * ROW, labels - 5, ROW),
                Qt.AlignVCenter,
                ("¬ " if s.active_low else "") + s.name,
            )
        c.render(
            painter,
            target,
            QRectF(c.axis.x(lo), 0, usable, c.sceneRect().height()),
            Qt.IgnoreAspectRatio,
        )
    finally:
        painter.end()
    if kind == "png" and not device.save(str(path), "PNG"):
        raise OSError(str(path))
    if kind == "clipboard":
        return device
