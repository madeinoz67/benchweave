# Flashing and recovery — CH32V006E8R ADC board

Build (host toolchain: the MRS-bundled `riscv-wch-elf-gcc`, see the
Makefile header for `MRS_BASE`):

    make MRS_BASE=<mrs resources dir>

Artifacts land in `build/`: `.elf`, `.hex`, `.bin`, `.lst`, `.siz`. The
v2 build is ~6.6 KB of flash and 0.8 KB of RAM against the part's
62 KB / 8 KB budget (`Ld/Link.ld` is the authority: the CH32V006
variant block reads FLASH 62K, RAM 8K). Reproducibility: record and
compare the `.hex` sha256 — the hex image is identical across build
directories; object files are not.

Flash: WCH-LinkE (or WCH-Link) via wlink / MounRiver Studio, SWIO on the
board's programming header; the image is `build/ch32v006e8r_adc.hex`.

Recovery: the boot state is always 2 Mbps, 8N1, legacy frames — a v1
host (or a plain terminal at 2 Mbps) can always talk to a board running
this firmware without knowing about v2. If a negotiation leaves a board
in an unexpected state, power-cycle it: boot state is not persisted. The
revert guard (T_revert, 250 ms hint) already returns a switched board to
boot state on its own when the master goes silent.
