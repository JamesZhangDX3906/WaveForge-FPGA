import json
import os
import tempfile
from pathlib import Path
from app.core.model import Project


def save(project, path):
    project.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf8", dir=path.parent, delete=False
    ) as f:
        tmp = Path(f.name)
        try:
            json.dump(project.data(), f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            f.close()
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def load(path):
    return Project.parse(json.loads(Path(path).read_text(encoding="utf-8-sig")))
