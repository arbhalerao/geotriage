from evals.runner import Suite
from evals.suites import builder, time_mode

SUITES: dict[str, Suite] = {suite.name: suite for suite in [time_mode.SUITE, builder.BUILDER, builder.ALWAYS_ASKS]}
