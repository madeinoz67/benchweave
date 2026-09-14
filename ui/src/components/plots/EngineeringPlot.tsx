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

export interface EngineeringPlotProps {
  kind: "time_series" | "waveform";
  title: string;
  x: PlotAxis;
  traces: readonly PlotTrace[];
  threshold?: { value: number; label: string; severity: "warning" | "critical" };
}

export function EngineeringPlot({ kind, title, x, traces, threshold }: EngineeringPlotProps) {
  const chartElement = useRef<HTMLDivElement>(null);
  const descriptionId = useId();
  const description = `${x.label} in ${x.unit}; ${traces.map((trace) => `${trace.label} in ${trace.unit}`).join("; ")}`;

  useEffect(() => {
    const element = chartElement.current;
    if (element === null) return;
    const chart = echarts.init(element, undefined, {
      renderer: "svg",
      width: element.clientWidth || 640,
      height: element.clientHeight || 256,
    });
    const styles = getComputedStyle(element);
    const text = styles.getPropertyValue("--bw-text-muted").trim() || "#5b6a73";
    const border = styles.getPropertyValue("--bw-border").trim() || "#c3cfd5";
    const accent = styles.getPropertyValue("--bw-accent").trim() || "#0b7181";
    const alert = styles.getPropertyValue(`--bw-${threshold?.severity ?? "warning"}`).trim() || "#a96608";
    chart.setOption({
      animation: !(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false),
      grid: { left: 58, right: 24, top: 24, bottom: 44 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "value", name: `${x.label} (${x.unit})`, nameLocation: "middle", nameGap: 28, axisLabel: { color: text }, axisLine: { lineStyle: { color: border } }, splitLine: { lineStyle: { color: border, opacity: 0.45 } } },
      yAxis: { type: "value", axisLabel: { color: text }, axisLine: { lineStyle: { color: border } }, splitLine: { lineStyle: { color: border, opacity: 0.45 } } },
      series: traces.map((trace, index) => ({
        id: trace.id,
        name: `${trace.label} · ${trace.unit}`,
        type: "line",
        showSymbol: kind === "time_series",
        symbol: index % 2 === 0 ? "circle" : "diamond",
        lineStyle: { color: index === 0 ? accent : alert, type: index % 2 === 0 ? "solid" : "dashed", width: 2 },
        itemStyle: { color: index === 0 ? accent : alert },
        data: trace.values,
        markLine: threshold && index === 0 ? { symbol: "none", label: { formatter: threshold.label, color: alert }, lineStyle: { color: alert, type: "dashed" }, data: [{ yAxis: threshold.value }] } : undefined,
      })),
    });
    const resize = () => chart.resize({ width: element.clientWidth || 640, height: element.clientHeight || 256 });
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [kind, threshold, traces, x]);

  return (
    <figure className="bw-plot">
      <figcaption>{title}</figcaption>
      <div ref={chartElement} className="bw-plot__canvas" role="img" aria-label={title} aria-describedby={descriptionId} />
      <p className="bw-visually-hidden" id={descriptionId}>{description}</p>
      <ul className="bw-plot__legend" aria-label="Traces">
        {traces.map((trace, index) => <li key={trace.id} data-line={index % 2 === 0 ? "solid" : "dashed"}>{trace.label} · {trace.unit}</li>)}
      </ul>
    </figure>
  );
}
