#!/usr/bin/env python3
"""beta2: artifacts store."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from artifacts.store import write_text_artifact, list_artifacts, artifact_dir  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        home = Path(td) / "home"
        home.mkdir()
        os.environ["AGENTBOX_V5_DB"] = db_path
        os.environ["AGENTBOX_V5_HOME"] = str(home)
        dbmod.init_db(db_path)
        task = dbmod.create_task("/tmp/p", "art", db_path=db_path)
        row = write_text_artifact(task["id"], "researcher", "out.md", "# hi", db_path=db_path)
        assert row["path"]
        assert Path(row["path"]).is_file()
        d = artifact_dir(task["id"], "researcher")
        assert str(d) in row["path"] or d == Path(row["path"]).parent
        rows = list_artifacts(task_id=task["id"], db_path=db_path)
        assert len(rows) == 1
        print("OK: test_artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
