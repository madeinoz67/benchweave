# Add a device class

A device class gives one class of instrument its shared page shape. The class reference is data that the gateway expands into pages. The mockup is the visual specification of the result. You write two files, and they land as one change.

The machine corpus lives in the `standards/plugin-ui-class-reference/` directory of the repository. The family overview and the schemas are in [that directory](../standards/plugin-ui-class-reference/). The [Device classes table](device-classes.md) shows every class that the corpus implements today.

## The class file

Write one file, `class-<slug>.json`, for the class. The file binds one OTDP profile with its `profile_id` field. The schema `class-reference.schema.json` in the family directory defines the full shape.

The reference carries structure, never data. It may name page ids, slot keys, titles and layout spans. It may not carry values, units, thresholds or channel names. Every data item resolves at expansion time from the device descriptor and the OTDP action schemas.

A device descriptor declares its classes in a `profiles` array of profile ids. The array has no maximum and the ids are unique. A device may claim several profiles. For example, one device can claim the oscilloscope class and the logic analyser class together. The gateway merges the selected references, so your class must compose with every other class. Never author an identifier in the prefixed namespace of another class. Never assume that your class composes first. The family overview states the two composition rules in full.

## The mockup

Write one mockup, `class-<slug>.html`, in the `docs/internal/ui-styleguide-mockups/` directory. The mockup is the specification that the class gate validates against. One composition serves both themes: two `data-theme` sections, light and dark, over the shipped token set. Keep the page self-contained. Use invented identifiers only.

The theme-block convention:

> Each theme block is a complete page. The banner, the ground and the footer sit inside the block. `body` and `html` own no theme.

Put each §E.1 component hook on its root element: `bw-reading` on an `article`, `bw-alert-bubble` on an `aside`, `bw-plot` on a `section`, `bw-data-table` on a `table`, `bw-button` on a `button`. Placement is part of the specification. The census counts the hooks per theme. A hook on the wrong element fails the gate even when the count is correct.

The mockup is a guide, not a wall. Use it as a base. You can adapt it to your class. Do not add vocabulary only to copy a decorative detail of the mockup.

## The census

`tests/ui_html/classref_census.py` is the shared instrument. Its `hook_census()` counts the §E.1 hooks of one mockup per theme, and records the tag and the ancestor classes of each occurrence. Its `resolve_count()` evaluates the closed count grammar that the expect block authors. Derive the expectations of your class test from this instrument. Never count by hand.

## For a human author

1. Read the family overview and one existing class file. Start with the class that is closest to yours.
2. Write `class-<slug>.json` against the schema. Carry structure only.
3. Write the mockup `class-<slug>.html` to the convention above.
4. Write the class test `tests/ui_html/test_classref_<slug>.py`. Model it on the arms of the existing classes, and resolve the expectations through the census.
5. The sweep-plan record `docs/internal/classref-sweep-plan.json` carries the planned classes. Add one row for a class that you plan but have not landed yet. When your class file lands, the table moves the row to implemented. You do not edit the record.
6. Run the gates below. Land the class file, the mockup and the test in one change.

## For an AI agent

1. Read the schema, the family overview and the closest existing class before you write.
2. Derive every expectation from the corpus and from the census instrument. Do not derive an expectation from the pixels of the mockup.
3. Keep the mockup to the convention, and treat it as a guide. Do not add vocabulary only to copy a decorative detail of the mockup.
4. Do not add your class to a hand-kept list. The table, the preview set and the composition pair set derive from the corpus. Your class joins the pair set of the composition gate automatically.
5. Run the exact commands below. Land the class file, the mockup and the test in one change.

## The gates

Run these commands from the repository root. The mypy run is bare and config-driven.

```sh
UV_PROJECT_ENVIRONMENT=venv uv run ruff check .
rm -rf .mypy_cache && UV_PROJECT_ENVIRONMENT=venv uv run mypy
UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/ui_html/test_classref_<slug>.py tests/ui_html/test_classref_composition.py tests/contract/test_docs_site_device_classes.py
```
