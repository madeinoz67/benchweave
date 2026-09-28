import * as echarts from "echarts/core";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import { LineChart } from "echarts/charts";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";

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
  symbol: string;
  lineType: "solid" | "dashed";
}

/** The contract's symbol sequence (§E.2.2): 8 framework-neutral shapes; the
 *  reference binding uses the ECharts built-ins plus two custom SVG paths
 *  (plus, saltire) where the chart library lacks a shape. */
const SYMBOL_SEQUENCE = [
  "circle",
  "rect",
  "triangle",
  "diamond",
  "pin",
  "arrow",
  "path://M5,-1.4 L1.4,-1.4 L1.4,-5 L-1.4,-5 L-1.4,-1.4 L-5,-1.4 L-5,1.4 L-1.4,1.4 L-1.4,5 L1.4,5 L1.4,1.4 L5,1.4 Z",
  "path://M4.74,3.04 L3.04,4.74 L-3.04,-4.74 L-4.74,-3.04 Z M3.04,-4.74 L4.74,-3.04 L-4.74,3.04 L-3.04,4.74 Z",
] as const;

/** Bytewise lexicographic comparison (UTF-8 byte order) — the contract's
 *  slot-assignment order. UTF-8 byte order equals code-point order, so this
 *  compares code points left to right, NOT JS string ordering (which is
 *  UTF-16 code-unit order). */
const bytewiseLess = (a: string, b: string): boolean => {
  const encoder = new TextEncoder();
  const left = encoder.encode(a);
  const right = encoder.encode(b);
  const length = Math.min(left.length, right.length);
  for (let i = 0; i < length; i += 1) {
    if (left[i]! < right[i]!) return true;
    if (left[i]! > right[i]!) return false;
  }
  return left.length < right.length;
};

/** The trace-id -> slot map (pass 1's assignment), used by the legend's
 *  data-bw-series-slot disclosure. */
function slotMap(traces: readonly PlotTrace[]): Map<string, number> {
  const slots = new Map<string, number>();
  [...traces].map((trace) => trace.id).sort((a, b) => (bytewiseLess(a, b) ? -1 : bytewiseLess(b, a) ? 1 : 0)).forEach((id, index) => slots.set(id, index));
  return slots;
}

/** Resolve SET-derived defaults (pass 1) over the FULL declared trace id set,
 *  then bias colours by hint (pass 2). Styles are computed before any
 *  visibility filtering so hiding a channel can never shift the styling of
 *  the channels around it.
 *
 *  Pass 1 (the contract §E.2.1 slot grammar): the declared ids are sorted
 *  bytewise (UTF-8 byte order) and slot i takes colour series-((i mod 8)+1),
 *  dash-1/dash-2 by i<8, and symbol-((i mod 8)+1). Assignment is a pure
 *  function of the declared id SET — display order never enters it, so
 *  reordering the declared list restyles nothing, and hiding a channel (a
 *  display concern) never restyles its siblings. Adding or removing a
 *  declared id re-derives the plot's slots (the set changed). */
function resolveStyles(
  traces: readonly PlotTrace[],
  hints: ReadonlyMap<string, TraceHint> | undefined,
  tokens: { series: readonly string[]; alert: string; muted?: string },
): TraceStyle[] {
  const slots = slotMap(traces);
  const defaults: TraceStyle[] = traces.map((trace) => {
    const slot = slots.get(trace.id) ?? 0;
    return {
      // readTokens guarantees eight entries (fallback literals when the theme
      // resolves none), so the slot colour is always defined.
      color: tokens.series[slot % 8]!,
      symbol: SYMBOL_SEQUENCE[slot % 8],
      lineType: slot < 8 ? "solid" : "dashed",
    };
  });
  if (hints === undefined) return defaults;
  // Uniqueness of the emphasis colour is a host invariant, arbitrated over
  // the VISIBLE traces in trace order: pass-1 slot-1 (series-1) is the FIRST
  // claim, so an accent hint on a later trace loses silently to it (no
  // cascade: slot 1 keeps its default). A hidden trace releases its claim
  // and neither claims nor starves — so "no emphasis rendered" is never
  // laundered from "no emphasis requested". A muted trace releases its claim
  // only when the theme provides the muted token: a token-less muted hint
  // falls back to its pass-1 default, which still claims for slot 1.
  // Muting slot 1 is the sanctioned emphasis composition; among visible
  // traces hinting accent, the earliest in trace order wins while the others
  // revert to their pass-1 defaults. The accent hint's binding is
  // --bw-series-1 (the plot's emphasis role), per the contract §E.2.
  let accentClaimed = false;
  return traces.map((trace, index) => {
    const hint = hints.get(trace.id);
    const hidden = hint?.visible === false;
    if (hint?.colorRole === "muted" && tokens.muted !== undefined) {
      return { ...defaults[index]!, color: tokens.muted };
    }
    if (!hidden && defaults[index]!.color === tokens.series[0]) {
      accentClaimed = true;
      return defaults[index]!;
    }
    if (!hidden && hint?.colorRole === "accent" && !accentClaimed) {
      accentClaimed = true;
      return { ...defaults[index]!, color: tokens.series[0] };
    }
    return defaults[index]!;
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
  // The series fallback literals are the LIGHT theme's slot values (the same
  // jsdom-compat pattern as the other documented fallbacks); the in-tree
  // themes always define all eight, and L3 pins the mirror.
  const seriesFallback = ["#253421", "#8e7588", "#2f3300", "#00379d", "#7e002d", "#746084", "#5a1538", "#183058"];
  return {
    text: mutedToken ?? "#5b6a73",
    muted: mutedToken,
    border: styles.getPropertyValue("--bw-border").trim() || "#c3cfd5",
    alert: styles.getPropertyValue(`--bw-${severity ?? "warning"}`).trim() || "#a96608",
    series: Array.from({ length: 8 }, (_, i) => styles.getPropertyValue(`--bw-series-${i + 1}`).trim() || seriesFallback[i]!),
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
  const slots = useMemo(() => slotMap(traces), [traces]);
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
              data-line={legendStyles[index]?.lineType ?? "solid"}
              data-bw-series-slot={String((slots.get(trace.id) ?? 0) % 8 + 1)}
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
