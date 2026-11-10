from pathlib import Path
import os
from PySide6.QtCore import QStandardPaths, QLockFile, QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication
from app.core.model import Project
from app.services.files import load, save
from app.services.templates import template
from app.exporters.render import render
from app.importers.digital import read_vcd, read_csv
from app.ui.widgets import dialog


class Documents:
    def setup_recovery(self):
        self.data_dir = Path(
            os.environ.get("WAVEFORGE_DATA_DIR")
            or QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.session_settings = QSettings(
            str(self.data_dir / "session.ini"), QSettings.IniFormat
        )
        self.recovery = self.data_dir / f"recovery-{os.getpid()}.wfg"
        self.recovery_lock = QLockFile(str(self.recovery) + ".lock")
        self.recovery_lock.setStaleLockTime(0)
        self.recovery_lock.tryLock(0)

    def remember_project(self, path):
        self.session_settings.setValue("last_project", str(Path(path).resolve()))
        self.session_settings.sync()
        if self.session_settings.status() != QSettings.NoError:
            self.statusBar().showMessage(
                self.tr2(
                    "无法保存最近工程记录", "Unable to save recent project setting"
                ),
                8000,
            )

    def open_startup_project(self):
        if self.recover():
            return
        self.session_settings.sync()
        path = self.session_settings.value("last_project", "")
        if isinstance(path, str) and path:
            self.open_path(Path(path), report_errors=False)

    def recover(self):
        for path in sorted(
            self.data_dir.glob("recovery-*.wfg"), key=lambda f: -f.stat().st_mtime
        ):
            if path == self.recovery:
                continue
            lock = QLockFile(str(path) + ".lock")
            lock.setStaleLockTime(0)
            if not lock.tryLock(0):
                continue
            try:
                result = QMessageBox.question(
                    self,
                    "WaveForge FPGA",
                    self.tr2("恢复上次未保存的编辑？", "Recover unsaved changes?"),
                )
                if result == QMessageBox.Yes:
                    p = load(path)
                    self.replace(p, None)
                    self.history.resetClean()
                    save(p, self.recovery)
                path.unlink()
                return result == QMessageBox.Yes
            except Exception as exc:
                self.error(exc)
            finally:
                lock.unlock()
        return False

    def snapshot_view(self):
        self.p.zoom = self.zoom_factor
        self.p.viewport_start = self.scene.axis.t(self.view.mapToScene(0, 0).x())

    def autosave(self):
        self.snapshot_view()
        try:
            if not self.history.isClean():
                save(self.p, self.recovery)
            else:
                self.recovery.unlink(missing_ok=True)
        except OSError as exc:
            self.statusBar().showMessage(str(exc))

    def confirm(self):
        if self.history.isClean():
            return True
        result = QMessageBox.question(
            self,
            "WaveForge FPGA",
            self.tr2("保存当前工程的更改？", "Save changes to this project?"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
        )
        return (
            result == QMessageBox.Discard
            or result == QMessageBox.Save
            and self.save_file()
        )

    def replace(self, p, path):
        self.history.clear()
        self.path = path
        self.selected = []
        self.note_id = self.edge_id = ""
        self.view.pending = self.view.drag = None
        self.zoom_factor = p.zoom
        self.restore(p.data())
        self.view.horizontalScrollBar().setValue(
            round(self.scene.axis.x(p.viewport_start))
        )
        self.recovery.unlink(missing_ok=True)

    def new(self, name=None):
        if self.confirm():
            self.replace(template(name) if name else Project(), None)

    def save_file(self, choose=False):
        path = self.path
        if choose or not path:
            path = QFileDialog.getSaveFileName(
                self,
                self.tr2("保存工程", "Save project"),
                self.p.name.replace("/", "-") + ".wfg",
                "WaveForge (*.wfg)",
            )[0]
        if not path:
            return False
        try:
            path = Path(path).resolve()
            if path.suffix.lower() != ".wfg":
                path = path.with_suffix(".wfg")
            self.snapshot_view()
            save(self.p, path)
            self.path = path
            self.history.setClean()
            self.autosave()
            self.status()
            self.remember_project(path)
            return True
        except Exception as exc:
            self.error(exc)
        return False

    def open_file(self):
        path = QFileDialog.getOpenFileName(
            self, self.tr2("打开工程", "Open project"), "", "WaveForge (*.wfg)"
        )[0]
        if path:
            self.open_path(Path(path))

    def open_path(self, path, as_template=False, report_errors=True):
        try:
            path = Path(path).resolve()
            p = load(path)
            if self.confirm():
                self.replace(p, None if as_template else path)
                if not as_template:
                    self.remember_project(path)
                return True
        except Exception as exc:
            if report_errors:
                self.error(exc)
            else:
                self.statusBar().showMessage(
                    self.tr2(
                        "无法自动打开上次工程", "Unable to reopen the last project"
                    )
                    + f" · {path} · {exc}",
                    10000,
                )
        return False

    def user_template(self, write, channels_only=False):
        folder = self.data_dir / "templates"
        folder.mkdir(exist_ok=True)
        if write:
            path = QFileDialog.getSaveFileName(
                self,
                self.tr2("保存模板", "Save template"),
                str(folder / "template.wfg"),
                "WaveForge (*.wfg)",
            )[0]
            if path:
                try:
                    doc = self.p
                    if channels_only:
                        tracks = self.tracks_selected()
                        if not tracks:
                            return self.info("请先选择通道", "Select channels first")
                        ids = {s.id for s in tracks}
                        notes = [
                            n
                            for n in self.p.notes
                            if n.a.track in ids and n.b.track in ids
                        ]
                        doc = Project(
                            name=Path(path).stem,
                            tracks=tracks,
                            notes=notes,
                            duration=self.p.duration,
                            step=self.p.step,
                            unit=self.p.unit,
                        )
                    save(doc, path)
                except Exception as exc:
                    self.error(exc)
        else:
            path = QFileDialog.getOpenFileName(
                self,
                self.tr2("加载模板", "Load template"),
                str(folder),
                "WaveForge (*.wfg)",
            )[0]
            if path:
                if channels_only:
                    try:
                        doc = load(path)
                        original = self.clip
                        try:
                            self.clip = (doc.tracks, doc.notes)
                            self.paste()
                        finally:
                            self.clip = original
                    except Exception as exc:
                        self.error(exc)
                else:
                    self.open_path(Path(path), True)

    def import_file(self):
        tr = self.tr2
        path = QFileDialog.getOpenFileName(
            self, tr("导入波形", "Import waveforms"), "", "VCD / CSV (*.vcd *.csv)"
        )[0]
        if not path:
            return
        v = dialog(
            self,
            tr("导入时间范围", "Import time window"),
            [
                ("lo", tr("开始 ps", "Start ps"), 0),
                ("hi", tr("结束 ps（可留空）", "End ps (optional)"), ""),
            ],
        )
        if not v:
            return
        try:
            lo, hi = int(v["lo"]), int(v["hi"] or 10**15 - 1)
            if not 0 <= lo <= hi < 10**15:
                raise ValueError("Invalid range")
            path = Path(path)
            p = (read_csv if path.suffix.lower() == ".csv" else read_vcd)(path, lo, hi)
            if self.confirm():
                self.replace(p, None)
                self.history.resetClean()
        except Exception as exc:
            self.error(exc)

    def export(self, clipboard=False):
        tr = self.tr2
        fields = [
            ("width", tr("宽度 px", "Width px"), 1600),
            ("bg", tr("背景", "Background"), ["white", "dark", "transparent"]),
            ("lo", tr("开始 ps", "Start ps"), 0),
            ("hi", tr("结束 ps", "End ps"), self.p.duration),
            ("margin", tr("页边距 px", "Margin px"), 20),
            ("font", tr("字体", "Font"), "Segoe UI"),
            ("stroke", tr("线宽", "Stroke"), 2),
            ("grid", tr("显示网格", "Show grid"), self.p.grid),
        ]
        if not clipboard:
            fields.insert(0, ("format", tr("格式", "Format"), ["png", "svg", "pdf"]))
        v = dialog(
            self,
            (
                tr("复制图片", "Copy image")
                if clipboard
                else tr("导出时序图", "Export diagram")
            ),
            fields,
        )
        if not v:
            return
        kind = v.get("format", "clipboard")
        path = ""
        if not clipboard:
            path = QFileDialog.getSaveFileName(
                self,
                tr("导出", "Export"),
                self.p.name.replace("/", "-") + "." + kind,
                f"{kind.upper()} (*.{kind})",
            )[0]
            if not path:
                return
        try:
            width, margin, stroke = map(int, (v["width"], v["margin"], v["stroke"]))
            if (
                not 400 <= width <= 16000
                or not 0 <= margin <= 1000
                or not 1 <= stroke <= 12
            ):
                raise ValueError("Invalid dimensions")
            image = render(
                self.p,
                kind,
                path,
                width,
                int(v["lo"]),
                int(v["hi"]),
                v["bg"],
                margin,
                v["grid"],
                v["font"],
                stroke,
            )
            if clipboard:
                QApplication.clipboard().setImage(image)
            self.statusBar().showMessage(
                tr("已复制图片", "Image copied") if clipboard else str(path), 4000
            )
        except Exception as exc:
            self.error(exc)

    def time_break(self):
        v = dialog(
            self,
            self.tr2("添加时间断点", "Add time break"),
            [
                ("a", "A · ps", self.p.duration // 2),
                ("b", "B · ps", self.p.duration * 3 // 4),
            ],
        )
        if v:
            self.edit(
                "Time break",
                lambda: setattr(
                    self.p,
                    "breaks",
                    sorted([*self.p.breaks, [int(v["a"]), int(v["b"])]]),
                ),
            )

    def closeEvent(self, e):
        if self.confirm():
            self.recovery.unlink(missing_ok=True)
            self.recovery_lock.unlock()
            e.accept()
        else:
            e.ignore()
