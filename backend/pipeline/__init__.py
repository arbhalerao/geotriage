"""
the application: discover scenes, stage their bands, score them, finalize

plain functions over a database session, importing no celery and no fastapi
the worker and the API are both adapters onto this, which is what makes it runnable from a test
"""

from pipeline.discover import discover, mark_workflow_failed
from pipeline.finalize import claim_due_workflows, finalize_workflow
from pipeline.registry import delete_workflow_artifacts, seed_defaults, smoke_test_model
from pipeline.score import score_run
from pipeline.screen import screen_item
from pipeline.stage import stage_bands

__all__ = [
    "claim_due_workflows",
    "delete_workflow_artifacts",
    "discover",
    "finalize_workflow",
    "mark_workflow_failed",
    "score_run",
    "seed_defaults",
    "smoke_test_model",
    "screen_item",
    "stage_bands",
]
