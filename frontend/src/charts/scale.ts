// frontend/src/charts/scale.ts

export type TimeInput = string | number | Date;

export interface StepPoint {
  readonly x: number;
  readonly y: number;
  readonly gapBefore?: boolean;
}

export interface BandPoint {
  readonly x: number;
  readonly yTop: number;
  readonly yBottom: number;
  readonly gapBefore?: boolean;
}

export function toEpochMs(value: TimeInput): number {
  if (typeof value === "number") {
    return value;
  }
  if (value instanceof Date) {
    return value.getTime();
  }
  return Date.parse(value);
}

export function roundSvg(value: number): number {
  const rounded = Math.round(value * 100) / 100;
  return Object.is(rounded, -0) ? 0 : rounded;
}

export function timeScale(
  domain: readonly [TimeInput, TimeInput],
  range: readonly [number, number],
): (value: TimeInput) => number {
  const d0 = toEpochMs(domain[0]);
  const d1 = toEpochMs(domain[1]);
  const r0 = range[0];
  const r1 = range[1];
  const span = d1 - d0;
  if (!Number.isFinite(span) || span === 0) {
    const mid = roundSvg((r0 + r1) / 2);
    return () => mid;
  }
  return (value: TimeInput): number => {
    const ms = toEpochMs(value);
    if (!Number.isFinite(ms)) {
      return roundSvg((r0 + r1) / 2);
    }
    const ratio = (ms - d0) / span;
    return roundSvg(r0 + ratio * (r1 - r0));
  };
}

export function linearScale(
  domain: readonly [number, number],
  range: readonly [number, number],
): (value: number) => number {
  const d0 = domain[0];
  const d1 = domain[1];
  const r0 = range[0];
  const r1 = range[1];
  const span = d1 - d0;
  if (!Number.isFinite(span) || span === 0) {
    const mid = roundSvg((r0 + r1) / 2);
    return () => mid;
  }
  return (value: number): number => {
    const ratio = (value - d0) / span;
    return roundSvg(r0 + ratio * (r1 - r0));
  };
}

export function stepPath(points: readonly StepPoint[]): string {
  if (points.length === 0) {
    return "";
  }
  const first = points[0];
  if (first === undefined) {
    return "";
  }
  if (points.length === 1) {
    const x = roundSvg(first.x);
    const y = roundSvg(first.y);
    return `M ${x} ${y} L ${x} ${y}`;
  }
  const commands: string[] = [`M ${roundSvg(first.x)} ${roundSvg(first.y)}`];
  for (let i = 1; i < points.length; i += 1) {
    const prev = points.at(i - 1);
    const curr = points.at(i);
    if (prev === undefined || curr === undefined) {
      continue;
    }
    const cx = roundSvg(curr.x);
    const cy = roundSvg(curr.y);
    if (curr.gapBefore === true) {
      commands.push(`M ${cx} ${cy}`);
      continue;
    }
    const py = roundSvg(prev.y);
    const px = roundSvg(prev.x);
    if (cx !== px) {
      commands.push(`L ${cx} ${py}`);
    }
    if (cy !== py || cx === px) {
      commands.push(`L ${cx} ${cy}`);
    }
  }
  return commands.join(" ");
}

export function bandPath(
  points: readonly BandPoint[],
  halfWidth = 6,
): string {
  if (points.length === 0) {
    return "";
  }
  const runs: BandPoint[][] = [];
  for (const point of points) {
    if (point.gapBefore === true || runs.length === 0) {
      runs.push([point]);
    } else {
      const currentRun = runs[runs.length - 1];
      if (currentRun !== undefined) {
        currentRun.push(point);
      }
    }
  }

  const subpaths: string[] = [];
  const hw = Math.max(1, halfWidth);
  for (const run of runs) {
    const first = run[0];
    const last = run[run.length - 1];
    if (first === undefined || last === undefined) {
      continue;
    }
    const sameX = run.every((pt) => roundSvg(pt.x) === roundSvg(first.x));
    if (run.length === 1 || sameX) {
      const xLeft = roundSvg(first.x - hw);
      const xRight = roundSvg(first.x + hw);
      const yTop = roundSvg(
        Math.min(...run.map((pt) => Math.min(pt.yTop, pt.yBottom))),
      );
      const yBottom = roundSvg(
        Math.max(...run.map((pt) => Math.max(pt.yTop, pt.yBottom))),
      );
      subpaths.push(
        `M ${xLeft} ${yTop} L ${xRight} ${yTop} L ${xRight} ${yBottom} L ${xLeft} ${yBottom} Z`,
      );
      continue;
    }

    const upper = run.map(
      (pt, index) =>
        `${index === 0 ? "M" : "L"} ${roundSvg(pt.x)} ${roundSvg(pt.yTop)}`,
    );
    const lower: string[] = [];
    for (let i = run.length - 1; i >= 0; i -= 1) {
      const pt = run.at(i);
      if (pt !== undefined) {
        lower.push(`L ${roundSvg(pt.x)} ${roundSvg(pt.yBottom)}`);
      }
    }
    subpaths.push(`${upper.join(" ")} ${lower.join(" ")} Z`);
  }
  return subpaths.join(" ");
}

export function ticksFor(
  domain: readonly [number, number],
  count = 5,
): readonly number[] {
  if (count <= 0) {
    return [];
  }
  const d0 = domain[0];
  const d1 = domain[1];
  if (!Number.isFinite(d0) || !Number.isFinite(d1)) {
    return [];
  }
  if (d0 === d1 || count === 1) {
    return [roundSvg(d0)];
  }
  const step = (d1 - d0) / (count - 1);
  const ticks: number[] = [];
  for (let i = 0; i < count; i += 1) {
    ticks.push(roundSvg(d0 + step * i));
  }
  return ticks;
}
