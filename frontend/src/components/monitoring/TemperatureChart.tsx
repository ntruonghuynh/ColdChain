import type { DataGap, ReadingPoint, TemperatureRun } from '../../api/types';

const W = 900;
const H = 280;
const PAD = { left: 44, right: 12, top: 12, bottom: 34 };

function ms(iso: string): number {
  return Date.parse(iso);
}

function tickLabel(t: number): string {
  const d = new Date(t).toISOString();
  return `${d.slice(5, 10)} ${d.slice(11, 16)}`;
}

/**
 * Temperature by sensor event time. Lines are drawn only between continuous readings
 * (at most `maxContinuousS` apart): nothing is drawn or interpolated across missing data.
 * Confirmed gaps and the not-yet-received tail are hatched and labelled UNKNOWN, never
 * coloured as in range.
 */
export function TemperatureChart({
  readings,
  gaps,
  runs = [],
  minC,
  maxC,
  maxContinuousS,
  xStart,
  xEnd,
  notReceivedFrom,
  title,
}: {
  readings: ReadingPoint[];
  gaps: DataGap[];
  runs?: TemperatureRun[];
  minC: number;
  maxC: number;
  maxContinuousS: number;
  xStart?: string | null;
  xEnd?: string | null;
  notReceivedFrom?: string | null;
  title: string;
}) {
  const points = readings.map((r) => ({ t: ms(r.event_at), c: Number(r.temperature_c), state: r.temperature_state }));
  const times = points.map((p) => p.t);
  const temps = points.map((p) => p.c);
  const x0 = xStart ? ms(xStart) : Math.min(...times, ...gaps.map((g) => ms(g.start_at)));
  let x1 = xEnd ? ms(xEnd) : Math.max(...times, ...gaps.map((g) => ms(g.end_at)));
  if (!Number.isFinite(x0) || !Number.isFinite(x1)) {
    return <p className="text-sm text-slate-500">No readings received for this view.</p>;
  }
  if (x1 <= x0) x1 = x0 + 60_000;
  const y0 = Math.floor(Math.min(minC, ...temps) - 1);
  const y1 = Math.ceil(Math.max(maxC, ...temps) + 1);
  const sx = (t: number) => PAD.left + ((t - x0) / (x1 - x0)) * (W - PAD.left - PAD.right);
  const sy = (c: number) => PAD.top + ((y1 - c) / (y1 - y0)) * (H - PAD.top - PAD.bottom);

  const segments: string[] = [];
  let current = '';
  let previous: number | null = null;
  for (const p of points) {
    const continuous = previous !== null && p.t - previous <= maxContinuousS * 1000;
    previous = p.t;
    const pt = `${sx(p.t).toFixed(1)},${sy(p.c).toFixed(1)}`;
    if (!continuous) {
      if (current) segments.push(current);
      current = `M${pt}`;
    } else {
      current += ` L${pt}`;
    }
  }
  if (current) segments.push(current);

  const yTicks: number[] = [];
  for (let c = y0; c <= y1; c += Math.max(1, Math.round((y1 - y0) / 8))) yTicks.push(c);
  const xTicks = Array.from({ length: 6 }, (_, i) => x0 + ((x1 - x0) * i) / 5);
  const visible = (a: number, b: number) => b > x0 && a < x1;
  const clampX = (t: number) => sx(Math.min(Math.max(t, x0), x1));
  const tail = notReceivedFrom ? ms(notReceivedFrom) : null;

  return (
    <figure className="w-full">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-auto w-full"
        role="img"
        aria-label={`${title}: ${readings.length} readings, ${gaps.length} confirmed gaps`}
      >
        <defs>
          <pattern id="hatch-unknown" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#f1f5f9" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="#94a3b8" strokeWidth="2" />
          </pattern>
          <pattern id="hatch-tail" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#ffffff" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="#cbd5e1" strokeWidth="1.5" />
          </pattern>
        </defs>
        <rect x={PAD.left} y={sy(maxC)} width={W - PAD.left - PAD.right} height={sy(minC) - sy(maxC)} fill="#ecfdf5" />
        {[minC, maxC].map((c) => (
          <g key={c}>
            <line x1={PAD.left} x2={W - PAD.right} y1={sy(c)} y2={sy(c)} stroke="#059669" strokeDasharray="4 3" />
            <text x={W - PAD.right - 4} y={sy(c) - 3} textAnchor="end" fontSize="10" fill="#047857">
              {c} °C limit
            </text>
          </g>
        ))}
        {runs
          .filter((r) => r.meets_policy_duration && visible(ms(r.first_event_at), ms(r.last_event_at)))
          .map((r) => (
            <rect
              key={r.run_key}
              x={clampX(ms(r.first_event_at))}
              y={PAD.top}
              width={Math.max(2, clampX(ms(r.last_event_at)) - clampX(ms(r.first_event_at)))}
              height={H - PAD.top - PAD.bottom}
              fill="#fecdd3"
              opacity="0.6"
            >
              <title>{`Policy excursion (${r.direction}) ${r.observed_duration_min} min observed`}</title>
            </rect>
          ))}
        {gaps
          .filter((g) => visible(ms(g.start_at), ms(g.end_at)))
          .map((g) => {
            const a = clampX(ms(g.start_at));
            const b = clampX(ms(g.end_at));
            return (
              <g key={g.gap_key}>
                <rect x={a} y={PAD.top} width={Math.max(2, b - a)} height={H - PAD.top - PAD.bottom} fill="url(#hatch-unknown)">
                  <title>{`Missing data ${g.gap_status}: bracketing span ${g.bracketing_span_min} min`}</title>
                </rect>
                {b - a > 46 && (
                  <text x={(a + b) / 2} y={PAD.top + 14} textAnchor="middle" fontSize="10" fill="#334155">
                    {g.gap_status === 'SHORT_GAP' ? 'missing' : 'UNKNOWN'}
                  </text>
                )}
              </g>
            );
          })}
        {tail !== null && tail < x1 && (
          <g>
            <rect
              x={clampX(tail)}
              y={PAD.top}
              width={Math.max(2, sx(x1) - clampX(tail))}
              height={H - PAD.top - PAD.bottom}
              fill="url(#hatch-tail)"
            >
              <title>Not yet received (no reading after this time)</title>
            </rect>
            {sx(x1) - clampX(tail) > 70 && (
              <text x={(clampX(tail) + sx(x1)) / 2} y={PAD.top + 28} textAnchor="middle" fontSize="10" fill="#475569">
                not yet received
              </text>
            )}
          </g>
        )}
        {segments.map((d, i) => (
          <path key={i} d={d} fill="none" stroke="#0f172a" strokeWidth="1.4" />
        ))}
        {points.map((p) =>
          p.state && p.state !== 'IN_RANGE' ? <circle key={p.t} cx={sx(p.t)} cy={sy(p.c)} r="2.4" fill="#e11d48" /> : null,
        )}
        {yTicks.map((c) => (
          <text key={c} x={PAD.left - 6} y={sy(c) + 3} textAnchor="end" fontSize="10" fill="#64748b">
            {c}
          </text>
        ))}
        {xTicks.map((t) => (
          <text key={t} x={sx(t)} y={H - 12} textAnchor="middle" fontSize="10" fill="#64748b">
            {tickLabel(t)}
          </text>
        ))}
        <line x1={PAD.left} x2={W - PAD.right} y1={H - PAD.bottom} y2={H - PAD.bottom} stroke="#cbd5e1" />
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        <span>Time axis: sensor event time (UTC)</span>
        <span><span className="mr-1 inline-block h-2 w-3 bg-emerald-100 align-middle" />policy range</span>
        <span><span className="mr-1 inline-block h-2 w-3 bg-slate-300 align-middle" />missing data (never in range)</span>
        <span><span className="mr-1 inline-block h-2 w-3 bg-rose-200 align-middle" />confirmed policy excursion</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-rose-600 align-middle" />out-of-range reading</span>
      </figcaption>
    </figure>
  );
}
