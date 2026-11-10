from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QByteArray, Qt

PATHS = {
    "wave": "M2 15h5V6h5v12h5V9h5",
    "new": "M5 3h10l4 4v14H5z M12 9v8m-4-4h8",
    "open": "M3 18V6h7l2 3h8v2 M3 19l3-7h16l-4 7z",
    "save": "M4 3h13l3 3v15H4z M8 3v6h8V3 M8 21v-8h8v8",
    "undo": "M8 5l-5 5 5 5 M3 10h10q8 0 7 10",
    "redo": "M16 5l5 5-5 5 M21 10h-10q-8 0-7 10",
    "clock": "M2 17h3V6h7v11h6V6h4",
    "signal": "M2 17h9V7h11",
    "bus": "M2 7h5l3 4 3-4h9 M2 17h5l3-6 3 6h9",
    "select": "M5 3l14 10-7 1-3 7z",
    "draw": "M4 20l2-7L17 2l5 5-12 12z",
    "note": "M3 4h18v13H9l-6 4z M7 9h10",
    "measure": "M2 14l13-12 7 7L9 22z M8 10l3 3m2-8 3 3",
    "fit": "M3 5v14m18-14v14M6 12h12m-9-3-3 3 3 3m6-6 3 3-3 3",
    "minus": "M5 12h14",
    "plus": "M5 12h14m-7-7v14",
    "export": "M4 13v7h16v-7 M12 16V3m-5 5 5-5 5 5",
    "grid": "M3 7h18M3 16h18M7 3v18m9-18v18",
    "snap": "M4 4v9a8 8 0 0 0 16 0V4h-5v9a3 3 0 0 1-6 0V4z",
    "theme": "M20 15A9 9 0 0 1 9 3a9 9 0 1 0 11 12",
}


def icon(key, color):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{PATHS[key]}" stroke="{color}" fill="none" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    return QIcon(pm)


def stylesheet(light):
    bg, panel, text, muted, border, field = (
        ("#f4f6fa", "#ffffff", "#263245", "#65748a", "#cdd6e2", "#f4f7fb")
        if light
        else ("#11141b", "#1a1f29", "#e0e7f2", "#95a3b9", "#303846", "#222936")
    )
    return f"""
    * {{font-family:'Segoe UI','Microsoft YaHei UI',sans-serif;font-size:13px;color:{text};}}
    QMainWindow,QDialog,QMenuBar,QStatusBar {{background:{bg};}}
    QWidget#panel,QScrollArea,QScrollArea>QWidget>QWidget,QToolBar,QMenu,QTreeWidget {{background:{panel};}}
    QLabel#muted {{color:{muted};font-size:11px;}}
    QLabel#heading {{font-size:16px;font-weight:600;}}
    QLabel#brand {{font-size:19px;font-weight:bold;}}
    QLabel#logo {{background:#306bd5;color:white;border-radius:7px;padding:5px;}}
    QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {{background:{field};border:1px solid {border};border-radius:5px;padding:5px;}}
    QPushButton,QToolButton {{background:transparent;border:1px solid transparent;border-radius:5px;padding:5px;}}
    QPushButton {{background:{field};border-color:{border};padding:6px 12px;}}
    QPushButton:hover,QToolButton:hover,QMenu::item:selected,QMenuBar::item:selected {{background:#354563;color:white;}}
    QToolButton:checked,QTreeWidget::item:selected {{background:#294674;color:#eaf3ff;}}
    QToolButton:disabled,QPushButton:disabled {{color:{muted};}}
    QMenu::item {{padding:6px 25px;}}
    QToolBar {{border:0;border-bottom:1px solid {border};spacing:3px;padding:4px;}}
    QTreeWidget,QGraphicsView,QScrollArea {{border:0;outline:0;}}
    QTreeWidget::item {{height:32px;}}
    QSplitter::handle {{background:{border};width:1px;}}
    QScrollBar {{background:{bg};width:10px;height:10px;}}
    QScrollBar::handle {{background:{border};border-radius:4px;min-width:16px;min-height:16px;}}
    QStatusBar {{border-top:1px solid {border};}}
    """


def apply_palette(app, light):
    from PySide6.QtGui import QPalette, QColor

    palette = QPalette()
    bg, panel, field, text, disabled, selection = (
        ("#f4f6fa", "#ffffff", "#f4f7fb", "#263245", "#8491a0", "#306bd5")
        if light
        else ("#11141b", "#1a1f29", "#222936", "#e0e7f2", "#68778d", "#345991")
    )
    for role, color in [
        (QPalette.Window, panel),
        (QPalette.WindowText, text),
        (QPalette.Base, field),
        (QPalette.AlternateBase, bg),
        (QPalette.ToolTipBase, field),
        (QPalette.ToolTipText, text),
        (QPalette.Text, text),
        (QPalette.Button, panel),
        (QPalette.ButtonText, text),
        (QPalette.Highlight, selection),
        (QPalette.HighlightedText, "#ffffff"),
        (QPalette.PlaceholderText, disabled),
    ]:
        palette.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(disabled))
    app.setPalette(palette)
