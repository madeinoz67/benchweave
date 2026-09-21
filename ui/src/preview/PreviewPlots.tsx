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
 *  The preview data model is ONE simulated value per binding per scenario,
 *  not observation history — every feedable trace is an honest single point
 *  at x = 0, and the panel carries the standing disclosure line. Feedability
 *  is per binding: the observation must exist and carry a finite number.
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
      label: titleFor(channelView.variable_id),
      unit: channelView.unit ?? "",
      values: feedable ? [[0, value]] : [],
    };
  });
  return { traces, hints: hints.size > 0 ? hints : undefined, feedable };
}

export interface PreviewPlotsProps {
  views: readonly PlotView[];
  scenario: PreviewScenario;
}

export function PreviewPlots({ views, scenario }: PreviewPlotsProps) {
  if (views.length === 0) return null;
  return (
    <section className="bw-preview__plots" aria-label="Declared plots">
      <h2 className="bw-preview__plots-heading">Declared plots</h2>
      <p className="bw-preview__plots-note">
        Preview scenarios carry one simulated value per binding — not observation history.
      </p>
      {views.map((view) => {
        const join = plotTraces(view, scenario);
        return (
          <div className="bw-preview__plot" key={`${view.page_id}:${view.title}`}>
            <EngineeringPlot
              kind={view.kind}
              title={view.title}
              x={{ label: titleFor(view.x.label), unit: view.x.unit ?? "" }}
              traces={join.traces}
              hints={join.hints}
            />
            {join.feedable ? null : (
              <p role="status" className="bw-preview__no-data">
                No preview data for this scenario
              </p>
            )}
          </div>
        );
      })}
    </section>
  );
}
