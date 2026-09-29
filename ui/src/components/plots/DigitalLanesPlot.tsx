import { useId, useMemo } from "react";

import { reduceLane, type LaneState } from "./lane-reduction";
import "./digital-lanes.css";

/** §E.4: the host-knowledge seam mirrors the engineering-plot hints —
 * identity is lane POSITION; a hint carries visibility only. */
export interface LaneHint {
  visible?: boolean;
}

/** One acquired channel. `states` is the wire's four-state alphabet verbatim;
 * `axis` is the dataset's regular time axis (t_i = start + i·step — the
 * derivation stated in the plugin-ui 0.3.0 README). */
export interface Lane {
  id: string;
  label: string;
  states: readonly LaneState[];
  axis: { start: number; step: number };
}

/** §E.4.3: a collapsed bus lane. Member order is declaration order with the
 * FIRST declared member the LSB — bus values are a pure function of
 * (member states, member order). */
export interface LaneGroup {
  id: string;
  label?: string;
  member_ids: readonly string[];
  radix?: "hex" | "decimal";
  default_collapsed?: boolean;
}

/** §E.4.5: cursors are presentation-only positions in sample space. */
export interface LaneCursor {
  sample: number;
}

/** The decode action's event_log row, wire-shaped: [start_s, end_s) seconds,
 * the payload in the wire's hex encoding, and the decode status. */
export interface DecoderEvent {
  start_s: number;
  end_s: number;
  payload_hex: string;
  status: string;
}

/** §E.4.6: the decoder-lane declaration as the wire carries it, with the
 * host-resolved events. A lane with NO events renders the slice-2 interim
 * note (awaiting decoder rendering) — never a silent blank. */
export interface DecoderLaneDeclaration {
  id: string;
  label?: string;
  decoder: string;
  settings?: Record<string, unknown>;
  source_channel_ids: readonly string[];
  binding_id: string;
  events?: readonly DecoderEvent[];
}

export interface DigitalLanesPlotProps {
  title: string;
  x: { label: string; unit: string };
  lanes: readonly Lane[];
  groups?: readonly LaneGroup[];
  /** The dataset's trigger.time_relative_s — null renders NO marker and no
   * position is fabricated. */
  triggerTime?: number | null;
  cursors?: readonly LaneCursor[];
  decoderLanes?: readonly DecoderLaneDeclaration[];
  hints?: ReadonlyMap<string, LaneHint>;
  /** Drawn column budget (§E.4.4); the reduction keeps every transition. */
  columns?: number;
}

const CANVAS_WIDTH = 640;
const BAND_HEIGHT = 28;
const HIDDEN_BAND_HEIGHT = 14;
const LABEL_WIDTH = 96;
// x has no fill colour BY DESIGN: it renders the cross-hatch pattern
// geometry (§E.4.2), never a colour value.
const STATE_COLORS: Record<Exclude<LaneState, "x">, string> = {
  "0": "var(--bw-plot-lane-low, #8a8f98)",
  "1": "var(--bw-plot-lane-high, #d0d6e0)",
  z: "var(--bw-plot-lane-float, #8a8f98)",
};

/** §E.2.5's `at {rate}` suffix: rate = 1/axis step, human-scaled. */
function formatRate(step: number): string {
  const hz = 1 / step;
  if (hz >= 1e6) return `${trim(hz / 1e6)} MHz`;
  if (hz >= 1e3) return `${trim(hz / 1e3)} kHz`;
  return `${trim(hz)} Hz`;
}

function trim(value: number): string {
  return Number(value.toFixed(3)).toString();
}

/** §E.4.5's Δt readout: |x_b − x_a| in the view's axis mode, scaled. */
function formatDeltaSeconds(seconds: number): string {
  const abs = Math.abs(seconds);
  if (abs >= 1) return `${trim(seconds)} s`;
  if (abs >= 1e-3) return `${trim(seconds * 1e3)} ms`;
  if (abs >= 1e-6) return `${trim(seconds * 1e6)} µs`;
  return `${trim(seconds * 1e9)} ns`;
}

interface DrawnColumn {
  column: ReturnType<typeof reduceLane>[number];
  x: number;
  width: number;
}

export function DigitalLanesPlot({
  title,
  x,
  lanes,
  groups = [],
  triggerTime = null,
  cursors = [],
  decoderLanes = [],
  hints,
  columns = 64,
}: DigitalLanesPlotProps) {
  const hatchId = useId();
  const columnBudget = Math.max(1, columns);

  // Fold M1: the bus-collapse set is computed ONCE outside the row memo —
  // the row renderer and the decoder waiting predicate share this predicate.
  const collapsedInto = new Set(
    groups.flatMap((group) => (group.default_collapsed ? group.member_ids : [])),
  );
  const rows = useMemo(() => {
    // §E.4.1: a hidden lane's band renders COLLAPSED with its label
    // retained — hiding is a disclosure, never a removal.
    // §E.4.1 + §E.4.3 (fold F4): a group declared default_collapsed folds
    // its members into the bus lane on first render — the hidden-lane
    // treatment (collapsed band, label retained), driven by the declaration
    // the wire has carried since 0.3.0/0.2.0.
    const laneRows = lanes.map((lane) => {
      const isHidden = hints?.get(lane.id)?.visible === false || collapsedInto.has(lane.id);
      const reduced = isHidden ? [] : reduceLane(lane.states, columnBudget);
      const drawn: DrawnColumn[] = reduced.map((column, index) => ({
        column,
        x: LABEL_WIDTH + (index * (CANVAS_WIDTH - LABEL_WIDTH)) / reduced.length,
        width: (CANVAS_WIDTH - LABEL_WIDTH) / reduced.length,
      }));
      return { kind: "channel" as const, lane, drawn, isHidden };
    });
    const byId = new Map(lanes.map((lane) => [lane.id, lane]));
    const groupRows = groups.flatMap((group) => {
      const lookedUp: (Lane | undefined)[] = group.member_ids.map((id) => byId.get(id));
      // A group naming an unknown lane drops SILENTLY here — unreachable
      // through validated paths (the manifest validator refuses a
      // member outside y as unresolved_reference), so this is
      // defense-in-depth trust, not a second validation layer; slice 3's
      // renderer arms own the never-silent posture for real inputs.
      if (lookedUp.some((member) => member === undefined)) return [];
      const members = lookedUp as Lane[];
      const reduced = members.map((member) => reduceLane(member.states, columnBudget));
      const width = Math.max(...reduced.map((columns_) => columns_.length), 1);
      const bus: { value: string | null; hatch: boolean }[] = [];
      for (let index = 0; index < width; index += 1) {
        let bits = 0;
        let resolved = true;
        reduced.forEach((columns_, memberIndex) => {
          const column = columns_[Math.min(index, columns_.length - 1)]!;
          // §E.4.3 row 4 + §E.4.4 row 1 (fold F1): a member column that
          // CHANGED mid-column (an interior edge or a glitch mark) is as
          // unstable as x/z — the bus cell hatches, never a fabricated
          // stable value over the transition.
          if (column.glitch || column.edge) {
            resolved = false;
            return;
          }
          if (column.state === "1") bits += 1 << memberIndex;
          else if (column.state !== "0") resolved = false; // x/z member: unknown bus
        });
        if (!resolved) bus.push({ value: null, hatch: true });
        else if ((group.radix ?? "hex") === "decimal") {
          bus.push({ value: bits.toString(10), hatch: false });
        } else {
          bus.push({ value: `0x${bits.toString(16).padStart(Math.ceil(members.length / 4), "0")}`, hatch: false });
        }
      }
      return [{ kind: "group" as const, group, members, bus }];
    });
    return [...laneRows, ...groupRows];
  }, [hints, groups, columnBudget, lanes]);


  const firstAxis = lanes[0]?.axis;
  const acquired = Math.max(0, ...lanes.map((lane) => lane.states.length));
  const drawnColumns = Math.max(0, ...rows.map((row) => (row.kind === "channel" ? row.drawn.length : row.bus.length)));
  const sampleToX = (sample: number) => {
    const span = Math.max(1, acquired - 1);
    return LABEL_WIDTH + (sample / span) * (CANVAS_WIDTH - LABEL_WIDTH);
  };
  // §E.4.6: decoder annotation rows render BENEATH the channel and bus rows,
  // declaration order, their spans at the event's exact sample extent
  // (sample = (seconds − axis.start) / axis.step — the event_log's own time
  // base is the capture axis). A row whose source channel is hidden WAITS —
  // its events do not render and do not orphan onto a neighbour — and a
  // lane with no events at all keeps the slice-2 awaiting note.
  const decoderRows = decoderLanes.map((lane) => {
    // Fold M1: ONE hidden predicate — the same seam the row renderer
    // honours (hint-visible:false OR bus-collapsed member), so a decoder on
    // a collapsed member waits exactly like one on an explicitly hidden
    // lane.
    const sourceHidden = lane.source_channel_ids.some(
      (id) => hints?.get(id)?.visible === false || collapsedInto.has(id),
    );
    const hasEvents = (lane.events?.length ?? 0) > 0;
    const events =
      lane.events === undefined || sourceHidden
        ? []
        : lane.events.flatMap((event) => {
            const axis = firstAxis ?? { start: 0, step: 1 };
            // Fold L2: extents clip to the capture window; an event fully
            // outside it does not render; a zero-width [t,t) event renders
            // the minimum-width mark (never invisible); the drawn width
            // clamps at 1px.
            const startSample = Math.max((event.start_s - axis.start) / axis.step, 0);
            const endSample = Math.min((event.end_s - axis.start) / axis.step, acquired - 1);
            if (startSample >= acquired - 1) return [];
            const x = sampleToX(startSample);
            const end = sampleToX(Math.max(endSample, startSample));
            return [{ ...event, x, width: Math.max(end - x, 1) }];
          });
    return { kind: "decoder" as const, lane, events, sourceHidden, hasEvents };
  });
  const allRows = [...rows, ...decoderRows];
  const rowHeights = allRows.map((row) => (row.kind === "channel" && row.isHidden ? HIDDEN_BAND_HEIGHT : BAND_HEIGHT));
  const rowTops: number[] = [];
  let topCursor = 16;
  rowHeights.forEach((height) => {
    rowTops.push(topCursor);
    topCursor += height;
  });
  const canvasHeight = topCursor + 8;
  // §E.4.6 Disclosure (fold M2): settings render VERBATIM as they are on
  // the wire — scalars as their string form, nested values as their compact
  // JSON, nulls skipped; never "[object Object]" on a contract surface.
  const decoderDisclosure = (lane: { decoder: string; settings?: Record<string, unknown> }) =>
    `${lane.decoder}${
      lane.settings
        ? ` · ${Object.values(lane.settings)
            .filter((value) => value !== null && value !== undefined)
            .map((value) => (typeof value === "object" ? JSON.stringify(value) : String(value)))
            .join(" ")}`
        : ""
    }`;
  // §E.4.5 row 4 (fold F2): the Δt readout speaks the view's axis mode —
  // seconds mode scales the unit (7 µs), sample-index mode reads the raw
  // difference in the host's unit (7 samples) — never both.
  const cursorDelta =
    cursors.length >= 2 && firstAxis
      ? x.unit === "s"
        ? Math.abs(
            (firstAxis.start + cursors[cursors.length - 1]!.sample * firstAxis.step) -
              (firstAxis.start + cursors[0]!.sample * firstAxis.step),
          )
        : Math.abs(cursors[cursors.length - 1]!.sample - cursors[0]!.sample)
      : null;
  const cursorReadout =
    cursorDelta === null
      ? null
      : x.unit === "s"
        ? `Δt = ${formatDeltaSeconds(cursorDelta)}`
        : `Δt = ${trim(cursorDelta)} ${x.unit}`;
  const triggerX =
    triggerTime !== null && firstAxis
      ? sampleToX((triggerTime - firstAxis.start) / firstAxis.step)
      : null;
  const description = `${lanes.length} lanes over ${x.label} (${x.unit}); ${drawnColumns} columns drawn per lane`;

  return (
    <figure className="bw-lanes" aria-label={title}>
      <figcaption className="bw-lanes__title">{title}</figcaption>
      <div
        className="bw-lanes__canvas"
        role="img"
        aria-label={title}
        aria-describedby={`${hatchId}-desc`}
        data-bw-acquisition={`Acquired ${acquired} samples · plotted ${drawnColumns}${firstAxis ? ` at ${formatRate(firstAxis.step)}` : ""}`}
      >
        <svg viewBox={`0 0 ${CANVAS_WIDTH} ${canvasHeight}`} width="100%" role="presentation">
          <defs>
            <pattern id={hatchId} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill="transparent" />
              <line x1="0" y1="0" x2="0" y2="6" stroke="var(--bw-plot-lane-hatch, #8a8f98)" strokeWidth="2" />
            </pattern>
            <desc id={`${hatchId}-desc`}>{description}</desc>
          </defs>
          {allRows.map((row, rowIndex) => {
            const top = rowTops[rowIndex]!;
            const height = rowHeights[rowIndex]!;
            const identifier =
              row.kind === "group" ? row.group.id : row.kind === "decoder" ? row.lane.id : row.lane.id;
            const label =
              row.kind === "group"
                ? (row.group.label ?? row.group.id)
                : row.kind === "decoder"
                  ? (row.lane.label ?? decoderDisclosure(row.lane))
                  : row.lane.label;
            const isHidden = row.kind === "channel" && row.isHidden;
            return (
              <g
                key={identifier}
                className="bw-lanes__lane"
                data-bw-lane={rowIndex}
                data-bw-lane-kind={row.kind}
                {...(isHidden ? { "data-hidden": "true" } : {})}
                aria-label={isHidden ? `${label} (hidden by presentation preference)` : label}
              >
                <text className="bw-lanes__label" x={4} y={top + height / 2 + 4}>
                  {label}
                  {isHidden ? " · hidden" : ""}
                </text>
                {row.kind === "channel"
                  ? row.drawn.map(({ column, x: cx, width }, columnIndex) => {
                      const mid = top + BAND_HEIGHT / 2;
                      const segments = column.edge
                        ? [
                            { state: column.edge.from, width: width / 2 },
                            { state: column.edge.to, width: width / 2 },
                          ]
                        : [{ state: column.state, width }];
                      return (
                        <g key={columnIndex} data-bw-column={columnIndex}>
                          {column.glitch ? (
                            <rect
                              className="bw-lanes__glitch"
                              data-bw-glitch="true"
                              x={cx}
                              y={top}
                              width={width}
                              height={BAND_HEIGHT}
                              fill={`url(#${hatchId})`}
                              stroke="var(--bw-plot-lane-hatch, #8a8f98)"
                            />
                          ) : (
                            segments.map((segment, segmentIndex) => {
                              const sx = cx + segmentIndex * (width / 2);
                              if (segment.state === "x") {
                                return (
                                  <rect
                                    key={segmentIndex}
                                    data-bw-state="x"
                                    x={sx}
                                    y={top}
                                    width={segment.width}
                                    height={BAND_HEIGHT}
                                    fill={`url(#${hatchId})`}
                                  />
                                );
                              }
                              if (segment.state === "z") {
                                return (
                                  <line
                                    key={segmentIndex}
                                    data-bw-state="z"
                                    x1={sx}
                                    y1={mid}
                                    x2={sx + segment.width}
                                    y2={mid}
                                    stroke={STATE_COLORS.z}
                                    strokeWidth="2"
                                  />
                                );
                              }
                              return (
                                <rect
                                  key={segmentIndex}
                                  data-bw-state={segment.state}
                                  x={sx}
                                  y={segment.state === "1" ? top : mid}
                                  width={segment.width}
                                  height={BAND_HEIGHT / 2}
                                  fill={STATE_COLORS[segment.state]}
                                />
                              );
                            })
                          )}
                        </g>
                      );
                    })
                  : row.kind === "group"
                    ? row.bus.map((cell, cellIndex) => {
                      const width = (CANVAS_WIDTH - LABEL_WIDTH) / row.bus.length;
                      const cx = LABEL_WIDTH + cellIndex * width;
                      return cell.hatch ? (
                        <rect
                          key={cellIndex}
                          className="bw-lanes__group"
                          data-bw-state="x"
                          x={cx}
                          y={top}
                          width={width}
                          height={BAND_HEIGHT}
                          fill={`url(#${hatchId})`}
                        />
                      ) : (
                        <g key={cellIndex} className="bw-lanes__group">
                          <rect x={cx} y={top} width={width} height={BAND_HEIGHT} fill="var(--bw-plot-lane-bus, #3a3f4a)" />
                          <text x={cx + width / 2} y={top + BAND_HEIGHT / 2 + 4} textAnchor="middle" className="bw-lanes__bus-value">
                            {cell.value}
                          </text>
                        </g>
                      );
                    })
                  : row.kind === "decoder"
                    ? row.events.map((event, eventIndex) => (
                        <g key={eventIndex} data-bw-span={eventIndex}>
                          <rect
                            x={event.x}
                            y={top}
                            width={event.width}
                            height={height}
                            fill="var(--bw-plot-lane-bus, #3a3f4a)"
                            stroke="var(--bw-plot-lane-hatch, #8a8f98)"
                          />
                          <text
                            x={event.x + Math.max(event.width / 2, 8)}
                            y={top + height / 2 + 4}
                            textAnchor="middle"
                            className="bw-lanes__bus-value"
                          >
                            {event.payload_hex}
                          </text>
                        </g>
                      ))
                    : null}
              {row.kind === "decoder" && row.lane.label !== undefined ? (
                <text
                  className="bw-lanes__label"
                  x={CANVAS_WIDTH - 4}
                  y={top + height / 2 + 4}
                  textAnchor="end"
                >
                  {decoderDisclosure(row.lane)}
                </text>
              ) : null}
              {row.kind === "decoder" && row.sourceHidden ? (
                <text data-bw-waiting="true" x={LABEL_WIDTH + 4} y={top + height / 2 + 4} className="bw-lanes__bus-value">
                  {`events waiting — source channel hidden`}
                </text>
              ) : null}
              </g>
            );
          })}
          {triggerX !== null ? (
            <g data-bw-trigger="true" className="bw-lanes__trigger">
              <line x1={triggerX} y1={8} x2={triggerX} y2={canvasHeight - 8} stroke="var(--bw-plot-lane-trigger, currentColor)" strokeWidth="2" />
              <text x={triggerX + 3} y={12} className="bw-lanes__trigger-label">trigger</text>
            </g>
          ) : null}
          {cursors.map((cursor, index) => {
            const cx = firstAxis ? sampleToX(cursor.sample) : null;
            return cx === null ? null : (
              <g key={index} data-bw-cursor={index}>
                <line x1={cx} y1={8} x2={cx} y2={canvasHeight - 8} stroke="var(--bw-plot-lane-cursor, currentColor)" strokeDasharray="3 3" />
              </g>
            );
          })}
        </svg>
      </div>
      {cursorReadout !== null ? <p className="bw-lanes__cursors-delta">{cursorReadout}</p> : null}
      {decoderLanes.length > 0 && decoderLanes.every((lane) => (lane.events?.length ?? 0) === 0) ? (
        <p role="status" className="bw-lanes__decoder-note">
          {`Decoder lanes declared (${[...new Set(decoderLanes.map((lane) => lane.decoder))].join(", ")}) — awaiting decoder rendering`}
        </p>
      ) : null}
      <p className="bw-lanes__axis">{`${x.label} (${x.unit})`}</p>
      <p className="bw-plot__acquisition" data-bw-acquisition="true">
        {`Acquired ${acquired} samples · plotted ${drawnColumns}${firstAxis ? ` at ${formatRate(firstAxis.step)}` : ""}`}
      </p>
      {lanes.some((lane) => hints?.get(lane.id)?.visible === false) ? (
        <p className="bw-visually-hidden">hidden</p>
      ) : null}
    </figure>
  );
}
