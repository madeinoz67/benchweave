import * as echarts from "echarts/core";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { LineChart } from "echarts/charts";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useId, useLayoutEffect, useRef, useState, type CSSProperties } from "react";

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
  // and neither claims nor starves — so "no emphasis rendered" is never
  // laundered from "no emphasis requested". A muted trace releases its claim
  // only when the theme provides the muted token: a token-less muted hint
  // falls back to its pass-1 default, which still claims for index 0.
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

/** Read the theme tokens once for one resolution rule shared by the chart
 *  canvas and the legend swatches: a missing muted token leaves the role
 *  undefined, so a muted hint falls back to the trace's pass-1 default
 *  (design rule 5) — never a hardcoded literal, which would paint one
 *  theme's contrast into the other. */
function readTokens(
  severity: "warning" | "critical" | undefined,
  styles: CSSStyleDeclaration,
) {
  const mutedToken = styles.getPropertyValue("--bw-text-muted").trim() || undefined;
  return {
    text: mutedToken ?? "#5b6a73",
    muted: mutedToken,
    border: styles.getPropertyValue("--bw-border").trim() || "#c3cfd5",
    accent: styles.getPropertyValue("--bw-accent").trim() || "#0b7181",
    alert: styles.getPropertyValue(`--bw-${severity ?? "warning"}`).trim() || "#a96608",
  };
}

/** Unit-bearing display strings never dangle their separator: a null/empty
 *  catalogue unit renders the bare label, not "label · " / "label in " /
 *  "label ()". */
const labelled = (label: string, unit: string): string => (unit ? `${label} · ${unit}` : label);
const inUnit = (label: string, unit: string): string => (unit ? `${label} in ${unit}` : label);

export function EngineeringPlot({ kind, title, x, traces, threshold, hints }: EngineeringPlotProps) {
  const figureElement = useRef<HTMLElement>(null);
  const chartElement = useRef<HTMLDivElement>(null);
  const descriptionId = useId();
  const [themeVersion, setThemeVersion] = useState(0);
  const [legendStyles, setLegendStyles] = useState<TraceStyle[]>([]);
  const visible = (trace: PlotTrace) => hints?.get(trace.id)?.visible !== false;
  const description = `${inUnit(x.label, x.unit)}; ${traces.filter(visible).map((trace) => inUnit(trace.label, trace.unit)).join("; ")}`;

  // FC6: a theme switch mutates an ancestor's data-theme attribute — no data
  // dependency of this component changes, so tokens resolved once go stale.
  // Observe the closest [data-theme] ancestor (documentElement fallback,
  // deduped when identical — covers both the gateway app that themes a
  // wrapper element and the preview that themes the document root) and bump
  // a version the legend resolution and the chart effect both depend on.
  useLayoutEffect(() => {
    const element = figureElement.current;
    if (element === null || typeof MutationObserver === "undefined") return;
    const themed = element.closest("[data-theme]") ?? document.documentElement;
    const observer = new MutationObserver((records) => {
      if (records.some((record) => record.attributeName === "data-theme")) {
        setThemeVersion((version) => version + 1);
      }
    });
    observer.observe(themed, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  // The legend is the disclosure key: its swatches resolve through the same
  // two-pass styling as the chart, read from the component's own root — the
  // subtree that inherits the active theme whichever ancestor carries
  // data-theme, so legend and chart can never disagree (the gateway-app
  // always-light-legend manifestation). Refs are not attached during render,
  // so the read happens post-attach and lands in state before paint.
  useLayoutEffect(() => {
    const element = figureElement.current;
    if (element === null) return;
    setLegendStyles(resolveStyles(traces, hints, readTokens(threshold?.severity, getComputedStyle(element))));
  }, [traces, hints, threshold, themeVersion]);

  useEffect(() => {
    const element = chartElement.current;
    if (element === null) return;
    const chart = echarts.init(element, undefined, {
      renderer: "svg",
      width: element.clientWidth || 640,
      height: element.clientHeight || 256,
    });
    // Same read source as the legend (the component's own root): the canvas
    // div inherits the same theme variables, and one read source means the
    // two resolutions cannot diverge.
    const tokens = readTokens(threshold?.severity, getComputedStyle(figureElement.current ?? element));
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
        name: labelled(trace.label, trace.unit),
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
      // echarts attaches mark lines to a series, so a carrier renders the
      // threshold and nothing else. Dropping it here would launder "no limit
      // plotted" as "no limit configured". The carrier's two invisible data
      // points span the threshold value because echarts does NOT expand the
      // y-axis extent for markLine values — an empty-data carrier leaves a
      // threshold outside the default [0,1] extent undrawn (falsified with
      // the repo's own echarts via SSR render).
      series.push({
        id: "__threshold",
        name: threshold!.label,
        type: "line",
        showSymbol: false,
        symbol: "circle",
        lineStyle: { color: "transparent", type: "solid", width: 0 },
        itemStyle: { color: "transparent" },
        data: [[0, threshold!.value], [1, threshold!.value]],
        markLine,
      });
    }
    chart.setOption({
      animation: !(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false),
      grid: { left: 58, right: 24, top: 24, bottom: 44 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "value", name: x.unit ? `${x.label} (${x.unit})` : x.label, nameLocation: "middle", nameGap: 28, axisLabel: { color: tokens.text }, axisLine: { lineStyle: { color: tokens.border } }, splitLine: { lineStyle: { color: tokens.border, opacity: 0.45 } } },
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
  }, [kind, threshold, traces, x, hints, themeVersion]);

  return (
    <figure className="bw-plot" ref={figureElement}>
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
              aria-label={isHidden ? `${labelled(trace.label, trace.unit)} (hidden by presentation preference)` : undefined}
              style={{ "--legend-swatch": legendStyles[index]?.color ?? "" } as CSSProperties}
            >
              {labelled(trace.label, trace.unit)}
              {isHidden ? <span className="bw-plot__legend-hidden">hidden</span> : null}
            </li>
          );
        })}
      </ul>
    </figure>
  );
}
