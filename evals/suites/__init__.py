from evals.runner import Suite
from evals.suites import time_mode

SUITES: dict[str, Suite] = {suite.name: suite for suite in [time_mode.SUITE]}
