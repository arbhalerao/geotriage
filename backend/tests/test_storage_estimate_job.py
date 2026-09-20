import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from api.schemas.estimate import EstimateCreate
from builder.estimate import Estimate, run_estimate
from core.db.models.builder import StorageEstimate
from core.db.models.enums import BuilderRunStatus

GB = 1024**3
NOW = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
SQUARE = {"type": "Polygon", "coordinates": [[[90.3, 23.6], [90.5, 23.6], [90.5, 23.9], [90.3, 23.9], [90.3, 23.6]]]}


class Rows:
    def __init__(self, row):
        self.row, self.statuses = row, []

    @contextmanager
    def __call__(self):
        rows = self

        class Session:
            def get(self, _model, row_id):
                return rows.row if row_id == rows.row.id else None

            def commit(self):
                rows.statuses.append(rows.row.status)

        yield Session()


class Fixed:
    def __init__(self, estimate=None, error=None):
        self.estimate_, self.error = estimate, error

    def estimate(self, draft, now):
        if self.error:
            raise self.error
        return self.estimate_


def a_row():
    return StorageEstimate(id=uuid.uuid4(), status=BuilderRunStatus.queued, draft={"geometry": SQUARE})


def test_an_estimate_ends_done_with_its_figures_and_verdict():
    row = a_row()
    rows = Rows(row)
    run_estimate(row.id, session_factory=rows, estimator=Fixed(Estimate(101, int(3.8 * GB), 35 * GB, False, False)), now=NOW)
    assert rows.statuses == [BuilderRunStatus.running, BuilderRunStatus.done]
    assert (row.result["scenes"], row.result["verdict"]) == (101, "large")


def test_an_estimate_that_fails_says_why():
    row = a_row()
    with pytest.raises(ConnectionError):
        run_estimate(row.id, session_factory=Rows(row), estimator=Fixed(error=ConnectionError("archive unreachable")), now=NOW)
    assert row.status == BuilderRunStatus.failed and "archive unreachable" in row.error


def request(**changes):
    base = {
        "geometry": SQUARE,
        "time_mode": "historical",
        "time_start": "2024-01-01T00:00:00Z",
        "time_end": "2024-12-31T00:00:00Z",
        "collection_slugs": ["sentinel-2-l2a"],
        "models": [{"model_slug": "ndwi-water-detector"}],
    }
    return EstimateCreate(**{**base, **changes})


def test_an_estimate_needs_no_name_and_keeps_what_staging_depends_on():
    draft = request().as_draft()
    assert "name" not in draft
    assert draft["time_start"].startswith("2024-01-01") and draft["collection_slugs"] == ["sentinel-2-l2a"]


def test_an_estimate_is_refused_for_a_workflow_that_couldn_t_be_created():
    with pytest.raises(ValidationError, match="can't end in the future"):
        request(time_end="2099-01-01T00:00:00Z")
    with pytest.raises(ValidationError):
        request(collection_slugs=[])
