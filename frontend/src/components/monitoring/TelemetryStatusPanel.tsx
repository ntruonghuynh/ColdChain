import { AlertTriangle, Clock, Radio, ShieldQuestion, Thermometer } from 'lucide-react';
import type { ReactNode } from 'react';
import type { SensorStatus } from '../../api/types';
import { formatMinutes, formatUtc } from '../../format';
import { MonitoringStateBadge } from './MonitoringBadges';

function minutes(seconds: string | null): number | null {
  return seconds === null ? null : Number(seconds) / 60;
}

function Row({ icon, title, tone, children }: { icon: ReactNode; title: string; tone: 'ok' | 'warn' | 'bad' | 'muted'; children: ReactNode }) {
  const tones = {
    ok: 'border-emerald-200 bg-emerald-50/60',
    warn: 'border-amber-200 bg-amber-50/70',
    bad: 'border-rose-200 bg-rose-50/70',
    muted: 'border-slate-200 bg-slate-50',
  };
  return (
    <div className={`flex gap-3 rounded-lg border p-3 ${tones[tone]}`}>
      <div className="mt-0.5 shrink-0 text-slate-600">{icon}</div>
      <div className="min-w-0 text-sm">
        <p className="font-medium text-slate-900">{title}</p>
        <div className="mt-0.5 text-slate-700">{children}</div>
      </div>
    </div>
  );
}

/**
 * Plain-language status for non-technical users. Four separate questions:
 * temperature now, communication, confirmed missing data, incidents. A scheduled upload that has
 * not arrived yet is explained as normal communication, but never as "temperature safe".
 */
export function TelemetryStatusPanel({ status, reviewAtMin }: { status: SensorStatus; reviewAtMin: number }) {
  const c = status.communication;
  const sinceUpload = minutes(c.since_last_upload_s);
  const usual = minutes(c.observed_upload_interval_s);
  const longest = minutes(c.longest_recent_upload_interval_s);
  const unobserved = minutes(status.unobserved_duration_s);
  const lastTemp =
    status.last_observed_temperature_c !== null && status.last_observed_event_at
      ? `${Number(status.last_observed_temperature_c).toFixed(1)} °C at ${formatUtc(status.last_observed_event_at)}`
      : null;
  const gaps = status.confirmed_gaps;
  const gapTotal = gaps.SHORT_GAP + gaps.UNKNOWN + gaps.UNKNOWN_REVIEW_REQUIRED;
  const incidents = status.open_incidents_as_of;

  let temperature: ReactNode;
  let temperatureTone: 'ok' | 'warn' | 'bad' | 'muted' = 'muted';
  if (status.state === 'CURRENT') {
    temperature = <>Latest reading {lastTemp}. Readings are arriving on time.</>;
    temperatureTone = status.last_observed_temperature_state === 'IN_RANGE' ? 'ok' : 'bad';
  } else if (status.state === 'STALE' || status.state === 'UNKNOWN') {
    temperature = (
      <>
        <strong>Current temperature not known</strong> — no reading for {formatMinutes(unobserved)}
        {lastTemp ? <> (last observed {lastTemp})</> : null}. Missing data is never treated as safe.
      </>
    );
    temperatureTone = status.state === 'UNKNOWN' ? 'bad' : 'warn';
  } else if (status.state === 'ENDED') {
    temperature = <>Monitoring window has ended{lastTemp ? <>; last observed {lastTemp}</> : null}.</>;
  } else {
    temperature = <>Monitoring has not started yet.</>;
  }

  let communication: ReactNode;
  let communicationTone: 'ok' | 'warn' | 'bad' | 'muted' = 'muted';
  switch (c.status) {
    case 'WITHIN_RECENT_UPLOAD_INTERVALS':
      communication = (
        <>
          Waiting for the next scheduled upload. The last upload arrived {formatMinutes(sinceUpload)} ago; recent uploads
          came about every {formatMinutes(usual)} (longest {formatMinutes(longest)}). This is the normal upload rhythm, not a
          communication failure — but readings taken since the last upload are not known yet.
        </>
      );
      communicationTone = 'ok';
      break;
    case 'LONGER_THAN_RECENT_UPLOAD_INTERVALS':
      communication = (
        <>
          <strong>No upload for {formatMinutes(sinceUpload)}</strong> — longer than any of the last {c.recent_intervals_used}{' '}
          upload intervals (longest {formatMinutes(longest)}). Possible communication delay or outage. Buffered readings may
          still arrive later; readings that never arrive become confirmed missing data.
        </>
      );
      communicationTone = 'bad';
      break;
    case 'PATTERN_NOT_ESTABLISHED':
      communication = (
        <>
          Last upload {formatMinutes(sinceUpload)} ago. Too few uploads so far to describe the usual upload rhythm.
        </>
      );
      communicationTone = 'warn';
      break;
    case 'NO_UPLOAD_YET':
      communication = <>No upload received yet.</>;
      communicationTone = 'warn';
      break;
    case 'ENDED':
      communication = <>Monitoring window has ended{c.last_upload_received_at ? <>; last upload {formatUtc(c.last_upload_received_at)}</> : null}.</>;
      break;
    default:
      communication = <>Monitoring has not started yet.</>;
  }

  return (
    <section aria-label="Monitoring status in plain language" className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <Row icon={<Thermometer className="h-4 w-4" />} title="Temperature now" tone={temperatureTone}>
        <span className="mr-2"><MonitoringStateBadge state={status.state} /></span>
        {temperature}
      </Row>
      <Row icon={<Radio className="h-4 w-4" />} title="Communication" tone={communicationTone}>
        {communication}
        {!c.expected_schedule_configured && (
          <p className="mt-1 text-xs text-slate-500">
            Based on uploads actually received; no expected upload schedule is configured, so no upload is declared overdue.
          </p>
        )}
      </Row>
      <Row icon={<Clock className="h-4 w-4" />} title="Confirmed missing data" tone={gaps.UNKNOWN + gaps.UNKNOWN_REVIEW_REQUIRED > 0 ? 'warn' : 'muted'}>
        {gapTotal === 0
          ? 'No missing-reading interval confirmed so far.'
          : `${gapTotal} confirmed interval(s) without readings: ${gaps.SHORT_GAP} short, ${gaps.UNKNOWN} UNKNOWN, ${gaps.UNKNOWN_REVIEW_REQUIRED} needing quality review. Never counted as in range.`}
      </Row>
      <Row
        icon={(incidents.TEMPERATURE_EXCURSION ?? 0) + (incidents.DATA_GAP ?? 0) > 0 ? <AlertTriangle className="h-4 w-4" /> : <ShieldQuestion className="h-4 w-4" />}
        title="Open incidents"
        tone={(incidents.TEMPERATURE_EXCURSION ?? 0) + (incidents.DATA_GAP ?? 0) > 0 ? 'bad' : 'muted'}
      >
        {incidents.TEMPERATURE_EXCURSION ?? 0} temperature excursion(s), {incidents.DATA_GAP ?? 0} data-gap incident(s) pending
        quality review. A silence alone never opens an incident; only a confirmed gap of {reviewAtMin} min or more does.
      </Row>
    </section>
  );
}
