import json
import os
import subprocess
import sys
import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox
from app.core.model import Project
from app.services.files import save


@pytest.mark.parametrize("explicit_path", [False, True])
def test_recent_project_reopens_in_new_process(editor, tmp_path, explicit_path):
    path = tmp_path / "最近的工程.wfg"
    save(Project(name="Last project", duration=500000), path)
    assert editor.open_path(path)
    assert editor.session_settings.value("last_project") == str(path.resolve())
    chosen = tmp_path / "chosen.wfg"
    save(Project(name="Chosen project", duration=250000), chosen)
    script = """
import json
import sys
from PySide6.QtCore import QTimer
import main
from app.ui.main_window import Window
class ObservedWindow(Window):
    def __init__(self):
        super().__init__()
        QTimer.singleShot(150, self.report)
    def report(self):
        print(json.dumps({'name':self.p.name,'duration':self.p.duration,'path':str(self.path)}))
        self.history.setClean()
        self.close()
main.Window=ObservedWindow
sys.argv=['main.py'] + sys.argv[1:]
sys.exit(main.main())
"""
    result = subprocess.run(
        [sys.executable, "-c", script, *([str(chosen)] if explicit_path else [])],
        capture_output=True,
        text=True,
        encoding="utf8",
        timeout=20,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data == {
        "name": "Chosen project" if explicit_path else "Last project",
        "duration": 250000 if explicit_path else 500000,
        "path": str(chosen.resolve() if explicit_path else path.resolve()),
    }


def test_save_as_updates_recent_project_but_template_does_not(
    editor, tmp_path, monkeypatch
):
    w = editor
    file = tmp_path / "saved.wfg"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(file), ""))
    assert w.save_file(True)
    assert w.session_settings.value("last_project") == str(file.resolve())
    template = tmp_path / "template.wfg"
    save(Project(name="Template"), template)
    assert w.open_path(template, as_template=True)
    assert w.session_settings.value("last_project") == str(file.resolve())
    w.open_startup_project()
    assert w.path == file.resolve()


@pytest.mark.parametrize("corrupt", [False, True])
def test_unavailable_recent_file_shows_status_without_blocking(
    editor, tmp_path, corrupt
):
    w = editor
    path = tmp_path / "unavailable.wfg"
    if corrupt:
        path.write_text("invalid JSON", encoding="utf8")
    w.remember_project(path)
    before = w.p.data()
    w.open_startup_project()
    assert w.p.data() == before and w.path is None
    assert str(path) in w.statusBar().currentMessage()


def test_unsaved_recovery_has_priority(editor, tmp_path, monkeypatch):
    w = editor
    file = tmp_path / "last.wfg"
    save(Project(name="Last saved"), file)
    w.remember_project(file)
    recovery = w.data_dir / "recovery-old.wfg"
    save(Project(name="Unsaved recovered"), recovery)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    w.open_startup_project()
    assert w.p.name == "Unsaved recovered"
    assert w.path is None and not w.history.isClean()
    assert w.session_settings.value("last_project") == str(file.resolve())
    assert not recovery.exists()


def test_declining_recovery_opens_recent_project(editor, tmp_path, monkeypatch):
    w = editor
    file = tmp_path / "last.wfg"
    save(Project(name="Last saved"), file)
    w.remember_project(file)
    save(Project(name="Recovery"), w.data_dir / "recovery-old.wfg")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
    w.open_startup_project()
    assert w.p.name == "Last saved" and w.path == file.resolve()


def test_failed_and_cancelled_open_do_not_replace_recent_record(
    editor, tmp_path, monkeypatch
):
    w = editor
    last = tmp_path / "last.wfg"
    other = tmp_path / "other.wfg"
    save(Project(name="Last"), last)
    save(Project(name="Other"), other)
    assert w.open_path(last)
    monkeypatch.setattr(w, "error", lambda exc: None)
    assert not w.open_path(tmp_path / "missing.wfg")
    monkeypatch.setattr(w, "confirm", lambda: False)
    assert not w.open_path(other)
    assert w.session_settings.value("last_project") == str(last.resolve())
    assert w.path == last.resolve()


def test_failed_save_does_not_replace_recent_record(editor, tmp_path, monkeypatch):
    w = editor
    last = tmp_path / "last.wfg"
    save(Project(), last)
    assert w.open_path(last)
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args: (str(tmp_path / "fail.wfg"), "")
    )
    monkeypatch.setattr(w, "error", lambda exc: None)

    def fail(*args):
        raise OSError("write failed")

    monkeypatch.setattr("app.ui.documents.save", fail)
    assert not w.save_file(True)
    assert w.session_settings.value("last_project") == str(last.resolve())
