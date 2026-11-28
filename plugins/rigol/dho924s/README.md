<!-- author: Stephen Eaton -->
# Rigol DHO-924S device plugin

This project is the BenchWeave device plugin for the Rigol DHO-924S oscilloscope.
It is an independent project. It does not import the BenchWeave core, and the
core wheel does not include it.

## Evidence status

> **CAUTION:** THIS PLUGIN IS NOT QUALIFIED FOR HARDWARE. NO DHO-924S INSTRUMENT
> WAS CONNECTED WHEN THIS PLUGIN WAS BUILT. DO NOT USE THE RESULTS FROM THIS
> PLUGIN AS EVIDENCE ABOUT AN INSTRUMENT.

The project was built from the programming guide of the manufacturer. The guide
is a description of the shapes of the commands. It is not evidence from a unit.
All tests use synthetic exchanges. A synthetic exchange is an exchange that a
person wrote. Its values are invented. No vector is a recording.

## What the adapter does

The adapter does one operation on a wire: `identify`. It sends the identity
query `*IDN?`. It reads the reply. The adapter returns the identity when the
model in the reply agrees with the committed model. It refuses the operation
when the reply is different or incomplete. The adapter refuses all other
operations before it sends data.

## What the descriptor does not claim

The descriptor makes no claim about the physical unit. It does not list:

- a firmware version
- the interface of the unit: USB-TMC (USB Test & Measurement Class) or LAN
  (local area network)
- the command dialect of the unit after the identity query
- capture limits
- the channel count and the vertical ranges
- a device-class profile

`docs/device-evidence.md` is the evidence sheet. It lists each unknown fact. It
also lists the evidence that will settle each fact. The test
`tests/test_evidence_gate.py` reads the evidence sheet. The test fails when the
descriptor makes a claim that the sheet does not unlock with evidence from
hardware.

## Develop

This directory is the project root. It needs Python 3.13 or a later version and
`uv`. It does not need a BenchWeave installation.

1. Install the development dependencies: `uv sync --locked --dev`.
2. Get the pinned standard documents: `uv run python scripts/fetch_contracts.py`.
3. Do the tests: `uv run pytest`.
4. Do the lint checks: `uv run ruff check .` and `uv run ruff format --check .`.
5. Do the type check: `uv run mypy`.

Step 2 needs the network one time. The command downloads the standard documents
and verifies each file against the digest in `contracts/lock.json`. It does not
download device material. The tests run offline after step 2.

The repository CI (continuous integration) does not do the tests of this
project.

## Layout

| Path | Contents |
|---|---|
| `src/benchweave_rigol_dho924s/` | The package: adapter, client, codec, descriptor and session |
| `src/benchweave_rigol_dho924s/descriptor.json` | The descriptor: one declaration, and no copy of it in Python |
| `src/benchweave_rigol_dho924s/adapter-vectors.json` | Synthetic exchanges |
| `src/benchweave_rigol_dho924s/adapter-failure-vectors.json` | Synthetic failures |
| `contracts/` | The constraints and the lock of the standard documents |
| `docs/device-evidence.md` | The evidence sheet |
| `scripts/fetch_contracts.py` | The one-time download of the pinned standard documents |
| `tests/` | The tests and the synthetic host |
