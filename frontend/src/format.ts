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
