from PySide6.QtCore import Qt, QTimer, QSettings, QSize
from PySide6.QtGui import QAction, QActionGroup, QUndoStack
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QSplitter,
    QToolBar,
    QTreeWidgetItem,
    QMenu,
    QLineEdit,
    QScrollArea,
    QMessageBox,
    QApplication,
)
from app.core.model import Project, fmt
from app.services.templates import example, TEMPLATES
from app.commands.history import Change
from app.graphics.scene import TimingScene
from app.graphics.view import TimingView
from app.ui.style import icon, stylesheet, apply_palette
from app.ui.widgets import Tree, Names, label
from app.ui.documents import Documents
from app.ui.operations import Operations


class Window(Documents, Operations, QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("WaveForge", "FPGA")
        self.lang = self.settings.value("language", "zh")
        self.light = self.settings.value("theme", "dark") == "light"
        self.p = example()
        self.path = None
        self.selected = [self.p.tracks[0].id]
        self.note_id = self.edge_id = ""
        self.clip = []
        self.zoom_factor = 1
        self.mouse_t = 0
        self.history = QUndoStack(self)
        self.history.setUndoLimit(80)
        self.resize(1450, 850)
        self.setup_recovery()
        self.build()
        self.timer = QTimer(self, interval=12000)
        self.timer.timeout.connect(self.autosave)
        self.timer.start()
        self.history.cleanChanged.connect(self.status)
        QTimer.singleShot(0, self.fit)

    def tr2(self, zh, en):
        return zh if self.lang == "zh" else en

    def error(self, exc):
        QMessageBox.warning(
            self,
            self.tr2("操作未完成", "Operation failed"),
            str(exc) or type(exc).__name__,
        )

    def info(self, zh, en):
        QMessageBox.information(self, "WaveForge FPGA", self.tr2(zh, en))

    def edit(self, title, fn):
        before = self.p.data()
        try:
            fn()
            self.commit(before, title)
        except Exception as exc:
            self.restore(before)
            self.error(exc)

    def commit(self, before, title):
        try:
            self.p.validate()
        except Exception as exc:
            self.restore(before)
            self.error(exc)
            return
        after = self.p.data()
        if after != before:
            self.history.push(Change(title, before, after, self.restore))

    def restore(self, data):
        self.p = Project.parse(data)
        self.selected = [i for i in self.selected if self.p.track(i)]
        if not any(n.id == self.note_id for n in self.p.notes):
            self.note_id = ""
        self.view.pending = None
        self.view.cursor_drag = None
        self.refresh()

    def action(self, menu, zh, en, fn, key="", svg="", bar=None):
        a = QAction(self.tr2(zh, en), menu or bar or self)
        if svg:
            a.setIcon(icon(svg, "#51627a" if self.light else "#b9c9e2"))
        if key:
            a.setShortcut(key)
        a.triggered.connect(lambda checked=False: fn())
        if menu:
            menu.addAction(a)
        if bar:
            bar.addAction(a)
        return a

    def panel(self):
        w = QWidget()
        w.setObjectName("panel")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 15, 12, 10)
        lay.setSpacing(12)
        return w, lay

    def build(self):
        tr = self.tr2
        apply_palette(QApplication.instance(), self.light)
        self.setStyleSheet(stylesheet(self.light))
        self.setWindowIcon(icon("wave", "#5595ff"))
        for action in self.menuBar().actions():
            if action.menu():
                action.menu().deleteLater()
        self.menuBar().clear()
        if hasattr(self, "bar"):
            self.removeToolBar(self.bar)
            self.bar.deleteLater()
        self.bar = bar = QToolBar()
        bar.setMovable(False)
        bar.setIconSize(QSize(18, 18))
        self.addToolBar(bar)
        logo = label("", "logo")
        logo.setPixmap(icon("wave", "#ffffff").pixmap(22, 22))
        bar.addWidget(logo)
        bar.addWidget(label(" WaveForge  ", "brand"))
        bar.addSeparator()
        menus = [
            self.menuBar().addMenu(tr(z, e))
            for z, e in [
                ("文件", "File"),
                ("编辑", "Edit"),
                ("视图", "View"),
                ("通道", "Channel"),
                ("模板", "Templates"),
                ("时序", "Timing"),
            ]
        ]
        file, edit, view, channel, templates, timing = menus
        A = self.action
        A(file, "新建", "New", self.new, "Ctrl+N", "new", bar)
        A(file, "打开", "Open", self.open_file, "Ctrl+O", "open", bar)
        A(file, "保存", "Save", self.save_file, "Ctrl+S", "save", bar)
        A(file, "另存为", "Save as", lambda: self.save_file(True), "Ctrl+Shift+S")
        A(file, "导入 VCD / CSV", "Import VCD / CSV", self.import_file)
        A(file, "复制波形图片", "Copy waveform image", lambda: self.export(True))
        bar.addSeparator()
        undo = A(edit, "撤销", "Undo", self.history.undo, "Ctrl+Z", "undo", bar)
        redo = A(edit, "重做", "Redo", self.history.redo, "Ctrl+Y", "redo", bar)
        for action, check, sig in [
            (undo, self.history.canUndo, self.history.canUndoChanged),
            (redo, self.history.canRedo, self.history.canRedoChanged),
        ]:
            action.setEnabled(check())
            sig.connect(action.setEnabled)
        for z, e, fn, key in [
            ("复制通道", "Copy channels", self.copy, "Ctrl+C"),
            ("粘贴通道", "Paste channels", self.paste, "Ctrl+V"),
            ("删除所选", "Delete selection", self.delete, "Delete"),
            ("分组", "Group", self.group, ""),
            ("锁定 / 解锁", "Lock / unlock", self.lock, ""),
        ]:
            A(edit, z, e, fn, key)
        bar.addSeparator()
        for z, e, k in [
            ("时钟", "Clock", "clock"),
            ("信号", "Signal", "signal"),
            ("总线", "Bus", "bus"),
        ]:
            a = A(channel, z, e, lambda kind=k: self.add(kind), "", k, bar)
            bar.widgetForAction(a).setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        localized_templates = {
            "Synchronous reset": "同步复位",
            "Asynchronous reset": "异步复位",
            "Clock enable": "时钟使能",
            "FIFO": "FIFO 读写",
            "RAM": "RAM 读写",
            "Valid/Ready": "Valid/Ready 数据传输",
        }
        for name in TEMPLATES:
            A(
                templates,
                localized_templates.get(name, name),
                name,
                lambda n=name: self.new(n),
            )
        templates.addSeparator()
        A(
            templates,
            "保存为用户模板",
            "Save user template",
            lambda: self.user_template(True),
        )
        A(
            templates,
            "加载用户模板",
            "Load user template",
            lambda: self.user_template(False),
        )
        A(
            templates,
            "所选通道另存为模板",
            "Save selected channels as template",
            lambda: self.user_template(True, True),
        )
        A(
            templates,
            "插入模板通道",
            "Insert channels from template",
            lambda: self.user_template(False, True),
        )
        A(timing, "对齐或平移边沿", "Align or shift edges", self.align)
        A(timing, "添加时间断点", "Add time break", self.time_break)
        A(
            timing,
            "清除时间断点",
            "Clear time breaks",
            lambda: self.edit("Clear breaks", self.p.breaks.clear),
        )
        self.add_clock_guides_action = A(
            timing,
            "添加指定时钟的周期参考线…",
            "Add cycle guides for a clock…",
            lambda: self.set_clock_cycle_guides(True),
        )
        self.delete_clock_guides_action = A(
            timing,
            "删除指定时钟的所有周期参考线…",
            "Delete all cycle guides for a clock…",
            lambda: self.set_clock_cycle_guides(False),
        )
        A(
            timing,
            "清除游标",
            "Clear cursors",
            lambda: self.edit("Clear cursors", self.p.cursors.clear),
        )
        A(timing, "工程设置", "Project settings", lambda: self.select(""))
        A(view, "深色 / 浅色", "Dark / light", self.theme, "", "theme", bar)
        A(view, "中文 / English", "中文 / English", self.language)
        A(
            view,
            "信号管理区",
            "Signal explorer",
            lambda: self.left.setVisible(not self.left.isVisible()),
        )
        A(
            view,
            "属性面板",
            "Inspector",
            lambda: self.right.setVisible(not self.right.isVisible()),
        )
        spacer = QWidget()
        from PySide6.QtWidgets import QSizePolicy

        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)
        a = A(file, "导出", "Export", self.export, "Ctrl+E", "export", bar)
        bar.widgetForAction(a).setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.split = QSplitter()
        self.setCentralWidget(self.split)
        self.left, lay = self.panel()
        self.split.addWidget(self.left)
        lay.addWidget(label(tr("信号管理", "Signal explorer"), "heading"))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("搜索信号…", "Find signal…"))
        self.search.setClearButtonEnabled(True)
        lay.addWidget(self.search)
        self.tree = Tree(self)
        lay.addWidget(self.tree)
        self.search.textChanged.connect(self.fill_tree)
        self.tree.itemSelectionChanged.connect(self.tree_selection)
        self.tree.itemChanged.connect(self.tree_check)
        self.tree.itemCollapsed.connect(lambda item: self.collapse(item, True))
        self.tree.itemExpanded.connect(lambda item: self.collapse(item, False))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_menu)
        center, cl = self.panel()
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.split.addWidget(center)
        self.tools = QToolBar()
        self.tools.setIconSize(QSize(16, 16))
        cl.addWidget(self.tools)
        self.project_label = label("", "heading")
        self.tools.addWidget(self.project_label)
        self.tools.addSeparator()
        group = QActionGroup(self.tools)
        for k, z, e in [
            ("select", "选择", "Select"),
            ("draw", "绘制", "Draw"),
            ("note", "标注", "Annotate"),
            ("measure", "测量", "Measure"),
        ]:
            a = A(None, z, e, lambda mode=k: self.mode(mode), "", k, self.tools)
            a.setCheckable(True)
            group.addAction(a)
            a.setChecked(k == "select")
        self.tools.addSeparator()
        for z, e, fn, k in [
            ("缩小", "Zoom out", lambda: self.zoom(0.8), "minus"),
            ("放大", "Zoom in", lambda: self.zoom(1.25), "plus"),
            ("适应窗口", "Fit", self.fit, "fit"),
        ]:
            A(view, z, e, fn, "", k, self.tools)
        self.grid_actions = {}
        for k, z, e in [("grid", "网格", "Grid"), ("snap", "吸附", "Snap")]:
            a = A(view, z, e, lambda key=k: self.toggle(key), "", k, self.tools)
            a.setCheckable(True)
            self.grid_actions[k] = a
        self.tools.addSeparator()
        self.duration_action = A(
            timing, "设置结束时间…", "Set end time…", self.set_duration, bar=self.tools
        )
        self.duration_action.setToolTip(
            tr(
                "输入更长的结束时间以延长波形",
                "Enter a later end time to extend the waveform",
            )
        )
        self.scene = TimingScene(self.p)
        self.view = TimingView(self, self.scene)
        self.names = Names(self)
        chart = QSplitter()
        chart.addWidget(self.names)
        chart.addWidget(self.view)
        chart.setStretchFactor(1, 1)
        chart.setSizes([104, 800])
        cl.addWidget(chart)
        self.view.verticalScrollBar().valueChanged.connect(
            lambda _: self.names.update()
        )
        self.right, rl = self.panel()
        self.split.addWidget(self.right)
        rl.addWidget(label(tr("属性检查器", "Inspector"), "heading"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self.props = QVBoxLayout(content)
        self.props.setContentsMargins(0, 2, 0, 2)
        scroll.setWidget(content)
        rl.addWidget(scroll)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([210, 950, 250])
        self.refresh()

    def mode(self, k):
        self.view.mode = k
        self.view.pending = None

    def theme(self):
        self.light = not self.light
        self.settings.setValue("theme", "light" if self.light else "dark")
        self.build()
        QTimer.singleShot(0, self.fit)

    def language(self):
        self.lang = "en" if self.lang == "zh" else "zh"
        self.settings.setValue("language", self.lang)
        self.build()
        QTimer.singleShot(0, self.fit)

    def toggle(self, k):
        self.edit(k, lambda: setattr(self.p, k, not getattr(self.p, k)))

    def tree_menu(self, pos):
        m = QMenu(self)
        for z, e, f in [
            ("重命名 / 属性", "Rename / properties", lambda: self.right.show()),
            ("分组", "Group", self.group),
            ("锁定 / 解锁", "Lock / unlock", self.lock),
            ("复制通道", "Copy", self.copy),
            ("粘贴通道", "Paste", self.paste),
            ("删除", "Delete", self.delete),
            ("对齐 / 延迟", "Align / shift", self.align),
        ]:
            m.addAction(self.tr2(z, e), f)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def collapse(self, it, state):
        group = it.text(0)
        if it.data(0, Qt.UserRole):
            return

        def change():
            groups = set(self.p.collapsed)
            (groups.add if state else groups.discard)(group)
            self.p.collapsed = sorted(groups)

        self.edit_from_tree("Group visibility", change)

    def edit_from_tree(self, title, change):
        # Native Qt item-change handlers still use the emitting item on return.
        # Rebuild the tree after that stack unwinds.
        self._tree_edit = True
        try:
            self.edit(title, change)
        finally:
            self._tree_edit = False

    def tree_check(self, it, col):
        s = self.p.track(it.data(0, Qt.UserRole))
        if s:
            self.edit_from_tree(
                "Visibility",
                lambda: setattr(s, "visible", it.checkState(0) == Qt.Checked),
            )

    def fill_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        groups = {}
        for s in self.p.tracks:
            if self.search.text().lower() not in s.name.lower():
                continue
            if s.group and s.group not in groups:
                groups[s.group] = QTreeWidgetItem(self.tree, [s.group])
            title = (
                s.name
                + ("  [" + str(s.width - 1) + ":0]" if s.kind == "bus" else "")
                + ("  ⌑" if s.locked else "")
            )
            it = QTreeWidgetItem(groups.get(s.group, self.tree), [title])
            it.setIcon(0, icon(s.kind, s.color))
            it.setData(0, Qt.UserRole, s.id)
            it.setCheckState(0, Qt.Checked if s.visible else Qt.Unchecked)
            it.setSelected(s.id in self.selected)
            it.setToolTip(0, f"{s.kind} · {s.width} bit")
        for name, it in groups.items():
            it.setExpanded(name not in self.p.collapsed)
        if self.p.notes:
            parent = QTreeWidgetItem(self.tree, [self.tr2("时序标注", "Annotations")])
            parent.setData(0, Qt.UserRole, "@notes")
            for n in self.p.notes:
                it = QTreeWidgetItem(parent, [n.text or n.kind])
                it.setData(0, Qt.UserRole, n.id)
                it.setSelected(n.id == self.note_id)
                it.setIcon(0, icon("note", n.color))
            parent.setExpanded(True)
        self.tree.blockSignals(False)

    def tree_selection(self):
        ids = [it.data(0, Qt.UserRole) for it in self.tree.selectedItems()]
        groups = {
            item.text(0)
            for item in self.tree.selectedItems()
            if not item.data(0, Qt.UserRole)
        }
        self.selected = [
            s.id for s in self.p.tracks if s.id in ids or s.group in groups
        ]
        note = next((n for n in self.p.notes if n.id in ids), None)
        if note:
            self.note_id = note.id
            self.edge_id = ""
            self.show_selection()
            return
        self.note_id = self.edge_id = ""
        self.show_selection()

    def select(self, ident, add=False):
        self.selected = (
            (
                [i for i in self.selected if i != ident]
                if ident in self.selected
                else [*self.selected, ident]
            )
            if add
            else [ident] if ident else []
        )
        self.note_id = self.edge_id = ""
        self.fill_tree()
        self.show_selection()

    def select_note(self, ident):
        self.select("")
        self.note_id = ident
        self.fill_tree()
        self.show_selection()

    def show_selection(self):
        self.scene.note_id = self.note_id
        self.scene.selected = self.selected[0] if self.selected else ""
        self.scene.edge = None
        self.view.viewport().update()
        self.names.update()
        self.inspector()
        self.status()

    def refresh(self):
        self.scene.reset(self.p, self.width_px(), self.light)
        if getattr(self, "_tree_edit", False):
            QTimer.singleShot(0, self.fill_tree)
        else:
            self.fill_tree()
        self.show_selection()
        self.project_label.setText("  " + self.p.name[:23] + "  ")
        self.duration_action.setText(
            self.tr2("结束 ", "End ")
            + fmt(self.p.duration, self.p.unit)
            + " "
            + self.p.unit
            + "…"
        )
        for k, a in self.grid_actions.items():
            a.setChecked(getattr(self.p, k))

    def width_px(self):
        return max(200, self.view.viewport().width() - 2) * self.zoom_factor

    def fit(self):
        self.zoom_factor = 1
        self.refresh()

    def zoom(self, factor, t=None, x=None):
        if t is None:
            x = self.view.viewport().width() // 2
            t = self.scene.axis.t(self.view.mapToScene(x, 0).x())
        self.zoom_factor = max(0.25, min(4096, self.zoom_factor * factor))
        self.scene.resize_axis(self.width_px())
        self.status()
        self.view.horizontalScrollBar().setValue(round(self.scene.axis.x(t) - x))

    def zoom_range(self, a, b):
        span = self.scene.axis.x(b) - self.scene.axis.x(a)
        if span > 0:
            self.zoom(self.view.viewport().width() / span, a, 0)

    def pointer(self, t):
        self.mouse_t = t
        self.status()

    def status(self, *args):
        tr = self.tr2
        state = (
            tr("已修改", "Modified")
            if not self.history.isClean()
            else tr("就绪", "Ready")
        )
        self.setWindowTitle(
            ("* " if not self.history.isClean() else "")
            + self.p.name
            + "  ·  WaveForge FPGA"
        )
        unit = self.p.unit
        delta = (
            "    Δ "
            + fmt(abs(self.p.cursors[1] - self.p.cursors[0]), unit)
            + " "
            + unit
            if len(self.p.cursors) == 2
            else ""
        )
        selected = ", ".join(s.name for s in self.tracks_selected())
        self.statusBar().showMessage(
            f"  {self.p.name}    ·    {state}      |      {fmt(self.mouse_t,unit)} {unit}{delta}      |      {self.zoom_factor:.0%}      |      "
            + tr("网格", "Grid")
            + f" {fmt(self.p.grid_parameters()[0],unit)} {unit} "
            + ("✓" if self.p.grid else "—")
            + "    "
            + tr("吸附", "Snap")
            + (" ✓" if self.p.snap else " —")
            + "      "
            + selected
        )
