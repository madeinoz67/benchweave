<!-- author: Stephen Eaton -->
# Rigol DHO-924S device evidence sheet

This is the device evidence sheet that `docs/device-developer-guide.md` section 2 asks for, written
before any command was implemented. It follows the engineering register.

**Evidence level of this integration: none from hardware.** No Rigol instrument was connected,
queried or captured while this project was built. No protocol capture, firmware reading, transcript
or vector from a DHO-924S exists in this repository. Every fact about the physical unit is therefore
UNKNOWN below. What the project does contain is (a) code written from the manufacturer's programming
guide and tested against invented exchanges, and (b) this sheet, which names the evidence that would
settle each unknown.

The rule this sheet enforces is A02, qualified not assumed: a claim about the unit enters the
descriptor only with evidence from the unit. `tests/test_evidence_gate.py` reads the `STATUS` lines
of this sheet and refuses a descriptor that makes a claim no `EVIDENCED` row with a hardware source
unlocks.

## 1. How to read the status lines

Each unit fact has exactly one status line, in one of two forms:

- `STATUS[<key>]: UNKNOWN — evidence needed: <what to run and capture on the unit>`
- `STATUS[<key>]: EVIDENCED | source=<capture or record> | date=<YYYY-MM-DD> | origin=<hardware|simulator>`

A key is one of the five base keys below, or a base key and a detail joined by a colon
(`firmware:<version>`, `profile:<profile id>`, `bounds:<name>`, `channels:<channel id>`,
`transport:<type>`). A detailed row can be written only when its base fact is itself settled.

What the gate accepts as proof: an `EVIDENCED` row whose origin is `hardware`. A row with the
origin `simulator` records that something was tested against a mock. It unlocks nothing.

What the gate does not catch: whether the cited capture is real, and whether code that claims to
implement an evidenced fact does. Both stay with the reviewer.

Three kinds of material appear in this project and must not be confused:

| Kind | Meaning | May fill a unit fact? |
|---|---|---|
| hardware | Captured on the actual DHO-924S, with date and source | Yes |
| simulator | Authored or mocked exchange, tested against the mock transport | No |
| documentary | The manufacturer's programming guide, read as a description of command shapes | No |

## 2. Unit facts

### 2.1 Which transport the unit presents

STATUS[transport]: UNKNOWN — evidence needed: connect the unit's rear USB DEVICE port to the host and record whether a USB-TMC instrument appears, with its vendor and product ID and resource string; then record the unit's LAN settings from its Utility IO menu; then send `*IDN?` over each interface that is present and capture the complete exchange (bytes written, bytes read, and how the reply is terminated).

The programming guide describes two remote interfaces, USB and LAN, and says the instrument conforms
to the LXI Core 2011 device standard. That is documentary. It does not say which interface this unit
presents, on which host, or with which backend.

Procedure that would settle it:

1. With the unit off, connect its USB DEVICE port to the host. Power the unit on. Enumerate and
   record the USB instrument: vendor ID, product ID, USB serial, and the resource string the host
   forms for it.
2. Read the unit's LAN configuration from its front panel (address, netmask, gateway). Record whether
   the unit answers a discovery request on the bench network.
3. For each interface that is present, send `*IDN?` and capture the whole exchange.
4. Record, for each interface, the write terminator the unit accepted and the terminator that ended
   its reply. The guide states neither. A reply with no line feed, read with line-feed termination,
   does not complete; that is a refused identify, not a pass.

The descriptor keeps `transport.type` `custom` with no provider until one interface is evidenced. No
USB-TMC or LAN-SCPI provider contract is admitted in the standards corpus.

### 2.2 The installed firmware version

STATUS[firmware]: UNKNOWN — evidence needed: send `*IDN?` to the unit over its evidenced interface and capture the reply verbatim; its fourth field is the software version.

The guide documents the identity reply as four comma-separated fields: manufacturer, model, serial
number and software version. `:SYSTem:VERSion?` returns the version of SCPI, not the firmware, and
must not be used for this fact.

The identity reply was authored, not recorded, and its serial and firmware tokens are invented.

With no firmware read from the unit the descriptor declares `firmware_policy` `commissioned` and
carries no `supported_firmware` list. A listed policy requires at least one version, and no version
may be written from the datasheet or the guide. Each version later listed needs its own row here:
`STATUS[firmware:<version>]: EVIDENCED | ... | origin=hardware`.

### 2.3 The SCPI dialect of this unit

STATUS[dialect]: UNKNOWN — evidence needed: capture on the unit, for each base action, every command sent and every reply received, with the unit's state before and after; the pairs are listed in the table below.

The guide gives the shape of each command. Whether this unit accepts that shape, what it answers,
and how it reports an error are not evidenced. This project puts exactly one command on a wire: the
identity query. Every other command is refused before any write.

| Base action | Exchanges to capture on the unit |
|---|---|
| configure | For each setting, the set command and its query: `:CHANnel<n>:DISPlay`, `:CHANnel<n>:COUPling`, `:CHANnel<n>:PROBe`, `:CHANnel<n>:SCALe`, `:CHANnel<n>:OFFSet`, `:TIMebase:MAIN:SCALe`, `:TIMebase:MAIN:OFFSet`, `:TIMebase:MODE`, `:ACQuire:TYPE`, `:ACQuire:MDEPth`, `:ACQuire:AVERages`; and the read-only `:ACQuire:SRATe?`. For each trigger setting: `:TRIGger:MODE`, `:TRIGger:SWEep`, `:TRIGger:COUPling`, `:TRIGger:EDGE:SOURce`, `:TRIGger:EDGE:SLOPe`, `:TRIGger:EDGE:LEVel`. Record each commanded value beside the value read back. |
| arm | `:SINGle`, then `:TRIGger:STATus?` polled until the acquisition stops. Also `:TFORce` and `:RUN` if they are to be used. Record the time each reply took. |
| fetch | `:STOP`, then `:WAVeform:SOURce`, `:WAVeform:MODE`, `:WAVeform:FORMat`, `:WAVeform:STARt`, `:WAVeform:STOP`, each with its query; then `:WAVeform:PREamble?` and the complete `:WAVeform:DATA?` reply, header included. |
| abort | `:STOP`, then `:TRIGger:STATus?`. Record whether the status confirms that acquisition stopped. |
| error behaviour | Send one command the unit rejects and capture the reply; then drain the queue with `:SYSTem:ERRor[:NEXT]?` and record each entry and the entry that marks an empty queue. |

Three documented behaviours matter to a later design and need unit confirmation:

- The guide says the average count is rounded down to the nearest power of two. An integration must
  never report the requested count as the effective one; it must read the count back.
- The guide says memory data can be read only while acquisition is stopped.
- The guide gives trigger status answers of `TD`, `WAIT`, `RUN`, `AUTO` and `STOP`. Which of them this
  unit returns, and when, is not evidenced.

### 2.4 Capture bounds

STATUS[bounds]: UNKNOWN — evidence needed: with the channel count that the bench will use, set `:ACQuire:MDEPth` to each documented value in turn and read it back with `:ACQuire:MDEPth?`; at each depth read `:ACQuire:SRATe?`; in RAW mode read `:WAVeform:POINts?`; then capture one complete `:WAVeform:DATA?` transfer at the largest depth that read back, recording its block header, its byte count and its duration.

The guide lists memory depth values that depend on how many channels are enabled, and reserves its
largest values for one series. Those are the model family's capabilities. None of them is a
measurement of this unit.

The evidenced maximum is the largest value for which a complete transfer was captured on this unit,
under the channel count in use, and reproduced after a power cycle and after a change made from the
front panel. A value that was set and read back but never transferred in full is not evidenced.

No bounds-dependent field is declared in the descriptor: no `capture_limits`, no parameter range, no
`input_constraints`. The class maximum of 1,000,000 samples is a resource backstop in the catalog.
It is not this unit's limit and is not copied into the descriptor. Each field later added needs its
own row here: `STATUS[bounds:<field>]: EVIDENCED | ... | origin=hardware`.

> **CAUTION:** DO NOT USE A DEVICE'S MAXIMUM CAPABILITY AS A SAFE LIMIT FOR THE ATTACHED DEVICE UNDER
> TEST (DUT). A maximum that the instrument can reach is not a limit that the DUT tolerates. DUT
> limits belong in bench configuration, not in a reusable descriptor.

### 2.5 Channel count and vertical ranges of this unit

STATUS[channels]: UNKNOWN — evidence needed: for n from 1 to 4, send `:CHANnel<n>:DISPlay?` and record the reply and any error the unit returns for a channel it does not have; then for each channel that answers, set `:CHANnel<n>:PROBe` to `1`, set `:CHANnel<n>:SCALe` to the smallest and the largest documented value, and read both back with `:CHANnel<n>:SCALe?`; record also `:CHANnel<n>:COUPling?` and `:CHANnel<n>:BWLimit?`.

The guide's model table lists the DHO924S with four analogue channels and a 250 MHz bandwidth, and
gives the DHO900 series a vertical scale range of 200 microvolts to 10 volts per division at a 1X
probe ratio. That is documentary. It must be read from the unit before it is declared.

No channel is declared in the descriptor. Each channel later added needs its own row here:
`STATUS[channels:<channel id>]: EVIDENCED | ... | origin=hardware`.

## 3. Connection and framing

STATUS[dialect:framing]: UNKNOWN — evidence needed: capture the identity exchange on the unit with the raw bytes shown, and record the terminator that followed the command the unit accepted and the terminator that ended its reply.

The adapter supplies the framing that IEEE 488.2 defines, because the guide says its command language
is built on that standard: a line feed ends each command, and a line feed is expected to end each
reply. This is documentary by reference. The guide does not state the terminator for this unit, and
no unit was observed. With the wrong framing the identity query does not complete and the adapter
refuses. It never reports an identity it did not read in full.

## 4. Captured exchanges

| Exchange | Source | Date | Target identity | Origin |
|---|---|---|---|---|
| none | — | — | — | — |

No exchange has been captured on hardware.

The exchanges in `adapter-vectors.json` and `adapter-failure-vectors.json` were authored for this
project on 2026-11-28. Their origin is `simulator`. They follow the shapes the guide documents and
contain invented values. Each file names itself synthetic in its `provenance` field. None is a
recording, and none may be cited as evidence about a unit.

## 5. Documentary evidence (not unit evidence)

Source: Rigol **DHO800/DHO900 Programming Guide**.
URL: `https://download.rigol.com/en/Manual/Digital%20Oscilloscope/DHO900/DHO800900_ProgrammingGuide_EN.pdf`
Revision: the document prints no revision number. It carries copyright 2024, its PDF metadata gives
a creation date of 2024-10-16, and the sha256 of the file read is
`bfd8a9cc7c1498b534688a0927fbc55d2ca535883895d6e5228a8335b99d7d7d`.

The guide is cited for the shape of commands only. It fills no unit fact in section 2. No part of it
is copied into this project.

What the code takes from it:

| Shape | Where the code uses it |
|---|---|
| The identity query and its four-field reply | `codec.parse_idn`, `session.identify` |
| The waveform block header: `#`, a digit count, that many length digits, then the data | `codec.parse_block` |
| The waveform preamble: ten comma-separated parameters | `codec.parse_preamble` |
| The BYTE format, one byte per point, converted with the vertical increment, origin and reference | `codec.decode_byte_waveform` |
| The ASCII format: voltage values separated by commas | `codec.parse_ascii_waveform` |

**Premise check.** The build brief for this project expected a waveform block of IEEE floats in
little-endian order. The guide does not document a float waveform format for this series. It
documents three formats: BYTE with one byte per point, WORD with two bytes per point, and ASCII. No
float decoder is written. If this unit is found to return floats, the fact needs a row here with a
captured exchange: `STATUS[dialect:waveform-float]: EVIDENCED | ... | origin=hardware`.

**Not documented, therefore not implemented:**

- The byte order of the WORD format. The codec refuses WORD data. Row needed:
  `STATUS[dialect:waveform-word-byte-order]`.
- Any waveform vector. The waveform vectors in this project are invented.

## 6. A later increment

Each later claim follows the same order: capture on the unit, write the row here with its source and
date, then change the descriptor, then extend the code. The evidence gate refuses the second step
without the first. The device-class profile `otdp.oscilloscope/1.0.0` is claimed only when all four
of its base actions (configure, arm, fetch and abort) are evidenced in section 2.3 and implemented; a
device that cannot perform a base action stays an unclassified core integration.
