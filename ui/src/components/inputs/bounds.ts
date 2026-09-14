export function clampValue(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function stepValue(
  value: number,
  step: number,
  min: number,
  max: number,
  direction: 1 | -1,
): number {
  const precision = Math.max(0, (step.toString().split(".")[1] ?? "").length);
  return clampValue(Number((value + step * direction).toFixed(precision)), min, max);
}
