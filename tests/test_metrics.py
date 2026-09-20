#!/usr/bin/env python3
"""beta2: metrics + sampler."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from storage import db as dbmod  # noqa: E402
from observability.metrics import record_metric, list_metrics, MetricNames  # noqa: E402
from observability.sampler import sample_resources, collect_resources  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "t.db")
        os.environ["AGENTBOX_V5_DB"] = db_path
        home = Path(td) / "home"
        home.mkdir()
        os.environ["AGENTBOX_V5_HOME"] = str(home)
        dbmod.init_db(db_path)
        mid = record_metric(MetricNames.TASKS_CREATED, 1.0, labels={"t": "1"}, db_path=db_path)
        assert mid > 0
        rows = list_metrics(name=MetricNames.TASKS_CREATED, db_path=db_path)
        assert rows and rows[0]["metric_value"] == 1.0
        data = collect_resources(db_path=db_path)
        assert "cpu_pct" in data and "ram_pct" in data
        result = sample_resources(db_path=db_path)
        assert result["written"]
        print("OK: test_metrics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
