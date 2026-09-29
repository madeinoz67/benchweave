import { useMemo } from "react";
import {
  DigitalLanesPlot,
  type Lane,
  type LaneGroup,
} from "../components/plots/DigitalLanesPlot";
import type { LaneState } from "../components/plots/lane-reduction";
import {
  EngineeringPlot,
  type PlotTrace,
  type TraceHint,
} from "../components/plots/EngineeringPlot";
import { titleFor } from "../compositions/fixtures";
import type { PlotView, PreviewScenario } from "./api";

export interface PlotJoin {
  traces: readonly PlotTrace[];
  hints: ReadonlyMap<string, TraceHint> | undefined;
  feedable: boolean;
}

/** Pure join: one projected view × one scenario → traces + hints.
 *
 *  The preview data model is ONE simulated value per observation target
 *  per scenario, not observation history — every feedable trace is an honest
 *  single point at x = 0, and the panel carries the standing disclosure line.
 *  Feedability is per target: the observation must exist and carry a finite
 *  number. Bindings that share a target share that single observation.
 *  Hints ride as projected preferences (row C): color_role/visible merge
 *  onto the trace hint the plot component already consumes, and the map is
 *  omitted entirely when no channel declares a preference. No threshold is
 *  ever constructed here — manifest plots carry none and fabricating a limit
 *  line would launder a preference into an alarm.
 */
export function plotTraces(view: PlotView, scenario: PreviewScenario): PlotJoin {
  const observation = scenario.observations.find((row) => row.binding_id === view.binding_id);
  const value = observation?.value;
  const feedable = typeof value === "number" && Number.isFinite(value);
  const hints = new Map<string, TraceHint>();
  const traces: PlotTrace[] = view.channels.map((channelView) => {
    const hint: TraceHint = {};
    if (channelView.color_role !== undefined) hint.colorRole = channelView.color_role;
    if (channelView.visible !== undefined) hint.visible = channelView.visible;
    if (hint.colorRole !== undefined || hint.visible !== undefined) {
      hints.set(channelView.variable_id, hint);
    }
    return {
      id: channelView.variable_id,
      // The projected label is the authoring authority; prettifying the id is
      // the fallback when the wire label is empty, never a replacement.
      label: channelView.label || titleFor(channelView.variable_id),
      unit: channelView.unit ?? "",
      values: feedable ? [[0, value]] : [],
    };
  });
  return { traces, hints: hints.size > 0 ? hints : undefined, feedable };
}

/** §E.4 preview honesty (design §1.4): a capture view renders its DECLARED
 *  STRUCTURE with a deterministic synthetic state pattern exercising all
 *  four wire states — never observation history, and the standing
 *  disclosure line names the simulation. The pattern is phase-shifted per
 *  channel so lanes are visibly distinct without any colour meaning. */
function syntheticLaneStates(channelIndex: number, length = 240): LaneState[] {
  const pattern: LaneState[] = [
    ...Array.from({ length: 90 }, () => "0" as LaneState),
    ...Array.from({ length: 60 }, () => "1" as LaneState),
    ...Array.from({ length: 45 }, () => "x" as LaneState),
    ...Array.from({ length: 45 }, () => "z" as LaneState),
  ];
  const phase = channelIndex * 17;
  return Array.from({ length }, (_, index) => pattern[(index + phase) % pattern.length]!);
}

export interface PreviewPlotsProps {
  views: readonly PlotView[];
  scenario: PreviewScenario;
}

export function PreviewPlots({ views, scenario }: PreviewPlotsProps) {
  // Referential stability across unrelated parent re-renders (role, theme,
  // receipt): the joined traces AND the axis object keep identity so
  // EngineeringPlot's effect does not dispose and re-init every echarts
  // instance per state change.
  const plotted = useMemo(
    () =>
      views.map((viewItem) => ({
        view: viewItem,
        join: plotTraces(viewItem, scenario),
        x: { label: titleFor(viewItem.x.label), unit: viewItem.x.unit ?? "" },
      })),
    [views, scenario],
  );
  if (views.length === 0) return null;
  return (
    <section className="bw-preview__plots" aria-label="Declared plots">
      <h2 className="bw-preview__plots-heading">Declared plots</h2>
      <p className="bw-preview__plots-note">
        Preview scenarios carry one simulated value per observed target — not observation history.
        Lane activity in capture views is a labelled synthetic pattern, not acquired data.
      </p>
      {plotted.map(({ view, join, x }, index) => (
        // Manifest ids may contain ':' (the schema id pattern allows it),
        // so `${page_id}:${title}` is separator-collidable; the list
        // position is the collision-free key for a fixed decoded array.
        <div className="bw-preview__plot" key={index}>
          {view.kind === "digital_lanes" ? (
            <DigitalLanesPlot
              title={view.title}
              x={x}
              columns={24}
              lanes={view.channels.map(
                (channel, channelIndex): Lane => ({
                  id: channel.variable_id,
                  label: channel.label || titleFor(channel.variable_id),
                  states: syntheticLaneStates(channelIndex),
                  axis: { start: 0, step: 1e-6 },
                }),
              )}
              groups={(view.lane_groups ?? []).map(
                (group): LaneGroup => ({
                  id: group.id,
                  ...(group.label !== undefined ? { label: group.label } : {}),
                  member_ids: group.member_ids,
                  ...(group.radix !== undefined ? { radix: group.radix } : {}),
                }),
              )}
            />
          ) : (
            <EngineeringPlot
              kind={view.kind}
              title={view.title}
              x={x}
              traces={join.traces}
              hints={join.hints}
            />
          )}
          {join.feedable || view.kind === "digital_lanes" ? null : (
            <p role="status" className="bw-preview__no-data">
              No preview data for this scenario
            </p>
          )}
        </div>
      ))}
    </section>
  );
}
