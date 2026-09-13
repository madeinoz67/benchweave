"""WP08 Task 2: run-row lease-authority column + run_states bench index.

Additive only (D9 lease-authority modeling): ``runs.authority`` records
whether a run's authority came from a lease (``lease``) or the gateway
(``gateway`` — the default, so every pre-existing row reads as
gateway-owned; WP08 Task 3 consumes the field for commissioned takeover).
The index backs the seam's §5 busy oracle — ``Store.list_run_states``
filters ``run_states`` by bench_id.
"""

from __future__ import annotations

STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE runs ADD COLUMN authority TEXT NOT NULL DEFAULT 'gateway'",
    "CREATE INDEX IF NOT EXISTS idx_run_states_bench ON run_states (bench_id)",
)
