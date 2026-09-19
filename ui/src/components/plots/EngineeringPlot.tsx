import * as echarts from "echarts/core";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { LineChart } from "echarts/charts";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useId, useRef } from "react";

import "./engineering-plot.css";

echarts.use([GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, LineChart, SVGRenderer]);

export interface PlotAxis {
  label: string;
  unit: string;
}

export interface PlotTrace {
  id: string;
  label: string;
  unit: string;
  values: readonly (readonly [number, number])[];
}

/** Per-channel presentation preference keyed by trace id. A bias, never a
 *  command: the component stays free to disregard it, and a hint can never
 *  supply a literal colour or touch severity colouring. */
export interface TraceHint {
  colorRole?: "accent" | "muted";
  visible?: boolean;
}

export interface EngineeringPlotProps {
  kind: "time_series" | "waveform";
  title: string;
  x: PlotAxis;
  traces: readonly PlotTrace[];
  threshold?: { value: number; label: string; severity: "warning" | "critical" };
  hints?: ReadonlyMap<string, TraceHint>;
}

interface TraceStyle {
  color: string;
  symbol: "circle" | "diamond";
  lineType: "solid" | "dashed";
}

/** Resolve index-derived defaults (pass 1) over the FULL ordered trace list,
 *  then bias colours by hint (pass 2). Styles are computed before any
 *  visibility filtering so hiding a channel can never shift the styling of
 *  the channels around it. */
function resolveStyles(
  traces: readonly PlotTrace[],
  hints: ReadonlyMap<string, TraceHint> | undefined,
  tokens: { accent: string; alert: string; muted?: string },
): TraceStyle[] {
  const defaults: TraceStyle[] = traces.map((_, index) => ({
    color: index === 0 ? tokens.accent : tokens.alert,
    symbol: index % 2 === 0 ? "circle" : "diamond",
    lineType: index % 2 === 0 ? "solid" : "dashed",
  }));
  if (hints === undefined) return defaults;
  // Uniqueness of the emphasis colour is a host invariant, arbitrated over
  // the VISIBLE traces in trace order: pass-1 index-0 accent is the FIRST
  // claim, so an accent hint on a later trace loses silently to it (no
  // cascade: index 0 keeps its default). A hidden trace releases its claim
  // exactly as a muted one does — neither claims nor starves — so "no
  // emphasis rendered" is never laundered from "no emphasis requested".
  // Muting index 0 is the sanctioned emphasis composition; among visible
  // traces hinting accent, the earliest in trace order wins while the others
  // revert to their pass-1 defaults.
  let accentClaimed = false;
  return traces.map((trace, index) => {
    const hint = hints.get(trace.id);
    const hidden = hint?.visible === false;
    if (hint?.colorRole === "muted" && tokens.muted !== undefined) {
      return { ...defaults[index], color: tokens.muted };
    }
    if (!hidden && defaults[index].color === tokens.accent) {
      accentClaimed = true;
      return defaults[index];
    }
    if (!hidden && hint?.colorRole === "accent" && !accentClaimed) {
      accentClaimed = true;
      return { ...defaults[index], color: tokens.accent };
    }
    return defaults[index];
  });
}

export function EngineeringPlot({ kind, title, x, traces, threshold, hints }: EngineeringPlotProps) {
  const chartElement = useRef<HTMLDivElement>(null);
  const descriptionId = useId();
  const visible = (trace: PlotTrace) => hints?.get(trace.id)?.visible !== false;
  const description = `${x.label} in ${x.unit}; ${traces.filter(visible).map((trace) => `${trace.label} in ${trace.unit}`).join("; ")}`;

  useEffect(() => {
    const element = chartElement.current;
    if (element === null) return;
    const chart = echarts.init(element, undefined, {
      renderer: "svg",
      width: element.clientWidth || 640,
      height: element.clientHeight || 256,
    });
    const styles = getComputedStyle(element);
    // A missing muted token leaves the role undefined, so a muted hint falls
    // back to the trace's pass-1 default (design rule 5) — never a hardcoded
    // literal, which would paint one theme's contrast into the other.
    const mutedToken = styles.getPropertyValue("--bw-text-muted").trim() || undefined;
    const tokens = {
      text: mutedToken ?? "#5b6a73",
      muted: mutedToken,
      border: styles.getPropertyValue("--bw-border").trim() || "#c3cfd5",
      accent: styles.getPropertyValue("--bw-accent").trim() || "#0b7181",
      alert: styles.getPropertyValue(`--bw-${threshold?.severity ?? "warning"}`).trim() || "#a96608",
    };
    // Two passes: index-derived defaults over the full list, then hint bias.
    const resolved = resolveStyles(traces, hints, tokens);
    const visibleTraces = traces.filter((trace) => hints?.get(trace.id)?.visible !== false);
    const markLine = threshold
      ? { symbol: "none", label: { formatter: threshold.label, color: tokens.alert }, lineStyle: { color: tokens.alert, type: "dashed" as const }, data: [{ yAxis: threshold.value }] }
      : undefined;
    const series = visibleTraces.map((trace, position) => {
      const style = resolved[traces.indexOf(trace)];
      return {
        id: trace.id,
        name: `${trace.label} · ${trace.unit}`,
        type: "line",
        showSymbol: kind === "time_series",
        symbol: style.symbol,
        lineStyle: { color: style.color, type: style.lineType, width: 2 },
        itemStyle: { color: style.color },
        data: trace.values,
        markLine: markLine !== undefined && position === 0 ? markLine : undefined,
      };
    });
    if (markLine !== undefined && visibleTraces.length === 0) {
      // Every channel presentation-hidden still owes the viewer the limit:
      // echarts attaches mark lines to a series, so an empty-data carrier
      // renders the threshold and nothing else. Dropping it here would
      // launder "no limit plotted" as "no limit configured".
      series.push({
        id: "__threshold",
        name: threshold!.label,
        type: "line",
        showSymbol: false,
        symbol: "circle",
        lineStyle: { color: "transparent", type: "solid", width: 0 },
        itemStyle: { color: "transparent" },
        data: [],
        markLine,
      });
    }
    chart.setOption({
      animation: !(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false),
      grid: { left: 58, right: 24, top: 24, bottom: 44 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "value", name: `${x.label} (${x.unit})`, nameLocation: "middle", nameGap: 28, axisLabel: { color: tokens.text }, axisLine: { lineStyle: { color: tokens.border } }, splitLine: { lineStyle: { color: tokens.border, opacity: 0.45 } } },
      yAxis: { type: "value", axisLabel: { color: tokens.text }, axisLine: { lineStyle: { color: tokens.border } }, splitLine: { lineStyle: { color: tokens.border, opacity: 0.45 } } },
      // Visibility filters AFTER style resolution (indices never shift); the
      // threshold mark line rides the first visible series, or the carrier
      // above when none is visible.
      series,
    });
    const resize = () => chart.resize({ width: element.clientWidth || 640, height: element.clientHeight || 256 });
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [kind, threshold, traces, x, hints]);

  return (
    <figure className="bw-plot">
      <figcaption>{title}</figcaption>
      <div ref={chartElement} className="bw-plot__canvas" role="img" aria-label={title} aria-describedby={descriptionId} />
      <p className="bw-visually-hidden" id={descriptionId}>{description}</p>
      <ul className="bw-plot__legend" aria-label="Traces">
        {traces.map((trace, index) => {
          const isHidden = hints?.get(trace.id)?.visible === false;
          return (
            <li
              key={trace.id}
              data-line={index % 2 === 0 ? "solid" : "dashed"}
              data-hidden={isHidden ? "true" : undefined}
              aria-label={isHidden ? `${trace.label} · ${trace.unit} (hidden by presentation preference)` : undefined}
            >
              {trace.label} · {trace.unit}
              {isHidden ? <span className="bw-plot__legend-hidden">hidden</span> : null}
            </li>
          );
        })}
      </ul>
    </figure>
  );
}
