"""Shared support for the composed-member arms (#556 Track B, slice B7):
the scratch corpus builder, imported by the member test modules as a
sibling (the ``ui_gateway_support`` pattern — no package structure
under ``tests/``).

RETIREMENT RECORD (2026-10-26, the #561 rebase): this module used to
carry a test-authored member-declaration schema STAND-IN, planted at
the active family version while the committed corpus served none. The
standards PR landed the real 0.5.0
``composed-member-declaration.schema.json`` in the corpus and the
pointer advanced to the SDK that serves it, and the stand-in was
measured against that world before removal: the member arms were driven
with the real schema planted in its place and 25 of 26 passed — 24
unchanged, the transitional refusal arm after it learned to construct
its own no-schema corpus, and the retirement guard firing as its own
instruction. The two placement arms' plots needed the real schema's
required ``series`` key added (they had been written against the
stand-in's looser plot); every other arm's documents were already
real-schema-valid. NO arm needs the stand-in: it is deleted, not kept,
and the retirement guard went with it (its condition — corpus serves
the schema while a test leans on the stand-in — is now permanently
satisfied and would fire forever).

``build_member_corpus`` therefore remains only as the scratch-copy
helper the arms use to avoid mutating the committed corpus (the
transitional arm strips the schema in ITS copy; nothing else writes).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from benchweave.vendoring import corpus_root


def build_member_corpus(tmp_path: Path) -> Path:
    """The committed corpus copied into tmp — the served member schema
    rides along natively
    (the family corpus since the #561 standards PR landed it at 0.5.0;
    0.6.0 at this bump);
    nothing is planted. The arms that need a corpus WITHOUT the schema
    construct it themselves (the transitional refusal arm strips it)."""
    corpus = tmp_path / "standards"
    shutil.copytree(corpus_root(), corpus)
    return corpus
