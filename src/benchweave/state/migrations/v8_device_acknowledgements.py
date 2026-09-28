"""Device acknowledgement column (issue #219, design deferral D11).

One additive ``ALTER TABLE devices ADD COLUMN acknowledgement_json TEXT``:
the admission-record-owned persistence of a per-device operator
acknowledgement — ``{"otdp_version": ..., "recorded_at": ...}`` as written
by ``bootstrap.admit_startup_bench`` from the admission's pin record, NULL
for every device that loaded without one (whole-row replace semantics on
``put_device`` keep a withdrawn acknowledgement from lingering). Additive
in exactly the sense v7 established (``ADD COLUMN`` rewrites no data and
adds no constraint); the read surface is the API-view projection, which
derives the acknowledged-pin map for VR-16's warning from this column.
"""

from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE devices ADD COLUMN acknowledgement_json TEXT",
)
