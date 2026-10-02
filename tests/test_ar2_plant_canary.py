"""AR-2 plant: deliberately-failing canary for the windows evidence lane.

NEVER MERGED. This file exists on the throwaway plant branch only, to
prove the evidence machinery fires on a real Windows red before any real
one arrives (the G2-plant precedent): the pytest step must red, the JOB
conclusion must stay green (step-level continue-on-error), the warning
annotation and the job summary must name this id, and the junitxml
artifact must be uploaded.
"""

import sys


def test_ar2_plant_canary_deliberate_windows_red():
    # Deliberate red on the platform the evidence lane runs; green on POSIX
    # so only the lane under proof fires on the plant PR.
    if sys.platform == "win32":
        raise AssertionError(
            "AR-2 plant canary: deliberate red — windows evidence lane must "
            "carry this as step-red / job-green + warning + summary + artifact"
        )
