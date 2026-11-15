/** Formats an ISO timestamp in UTC with an explicit "UTC" suffix (timestamps are stored in UTC). */
export function formatUtc(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

/** Formats a decimal string from the API (e.g. "8.00") as a temperature. */
export function formatTempC(value: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(1)} °C` : `${value} °C`;
}

/** Formats an optional ISO timestamp; missing values are shown as a dash, never as a default time. */
export function formatOptionalUtc(iso: string | null | undefined): string {
  return iso ? formatUtc(iso) : '—';
}

/** Minutes with up to two decimals (exact values come from the API). */
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || !Number.isFinite(minutes)) return '—';
  const rounded = Math.round(minutes * 100) / 100;
  return `${rounded} min`;
}
