# plugin-ui 0.3.0 → 0.3.1 migration note

From-predecessor note for the 0.3.1 PATCH bump (issue #444, the
commissioned-preset firmware gate; additive machine errata — the
backwards-compatible row of GOVERNANCE's bump classes, the mirror image of
the #62 MINOR: that change tightened valid→invalid, this loosens
invalid→valid with nothing removed or retyped).

## What changed

The preset firmware gate (`validate_preset` in the corpus-owned
`contracts.py`) learns the OTDP identity policy's division of firmware
authority, as three rules:

1. The preset's own `supported_firmware` list always applies — a supplied
   firmware must be a member.
2. `firmware is None` is admissible only under `firmware_policy:
   "commissioned"` — the honest "cannot be decided from the descriptor"
   posture for offline checks. Under `listed` policy unknown firmware
   still fails. The apply path is unchanged: it refuses `not_ready` before
   the gate when no firmware is established, and with an established
   firmware rule 1 governs.
3. A firmware list the descriptor DECLARES is enforced regardless of
   policy (a `None` firmware is not a member): `listed` descriptors must
   declare one, and a commissioned descriptor that declares one keeps its
   descriptor-side membership check.

The predecessor's `"any"` policy arm was unreachable dead code
(`firmware_policy` is `["listed", "commissioned"]` in every OTDP schema
version in this tree, and the gate only sees OTDP-validated descriptors)
and is removed. The refusal is unchanged where it fires: Finding code
`incompatible_firmware`, path `preset.supported_firmware`, message "A
known firmware compatible with the descriptor and preset is required".

## The range consequence (coordinator ruling; G-3)

The served range slides narrow: `>=0.3.0,<0.4.0` → `>=0.3.1,<0.4.0`. A pin
to 0.3.0 is OUT of the carried set after this bump (the same
one-live-object slide as every plugin-ui bump: the normative bundle row
lists the live code object in every carried version's row, so single-
serving is the only honest posture — the manifest's F1/D2 policy note
sanctions the below-floor range). Re-stamp 0.3.0 pins to 0.3.1 (the
documents are 0.3.1-valid except `contract_version`, which the re-stamp
updates); no previously-valid 0.3.0 document becomes invalid under its
own frozen schema.

## Effect on consumers

- SDK `check-preset` / `check-ui`: a commissioned descriptor whose preset
  lists the supplied firmware now passes (previously refused by the
  descriptor-side conjunct against an empty list).
- Gateway presentation composition: `firmware=None` for a listless
  commissioned descriptor is now the admitted offline posture, so the
  settings/preset UI no longer marks the whole attachment invalid.
- Standalone authoring: a whole-document preset put on a commissioned
  project with no firmware source validates under the `None` posture
  instead of refusing "no firmware to judge the preset against" (that
  error keeps its force for non-commissioned policies).
- Standalone apply: unchanged — the established-firmware gate still
  refuses before any write.
