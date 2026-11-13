import { NotImplemented } from '../components/ui/NotImplemented';
import { PageHeader } from '../components/ui/PageHeader';

export function TemperatureMonitoringPage() {
  return (
    <>
      <PageHeader title="Temperature Monitoring" description="Temperature timeline per shipment." />
      <NotImplemented
        milestone="Milestones 3 and 7"
        planned={[
          'Temperature timeline by sensor event time, with the policy range shown as a band.',
          'Missing-data indicator: gaps shown as UNKNOWN, never as in-range.',
          'Markers for readings that arrived late (received time vs event time).',
          'Threshold baseline and ML detections overlaid for comparison.',
        ]}
      />
    </>
  );
}

export function ExcursionQueuePage() {
  return (
    <>
      <PageHeader title="Excursion Queue" description="Open incidents that need quality review." />
      <NotImplemented
        milestone="Milestones 3 and 7"
        planned={[
          'Incidents by category: temperature excursion, data gap, suspected sensor fault.',
          'Age, shipment and interval for each incident.',
          'Product-risk alerts kept separate from missing or faulty sensor data.',
        ]}
      />
    </>
  );
}

export function QualityReviewPage() {
  return (
    <>
      <PageHeader title="Quality Review" description="Evidence, response drafts and release or quarantine decisions." />
      <NotImplemented
        milestone="Milestones 5 to 7"
        planned={[
          'Evidence package for each incident.',
          'Procedure-based response draft citing the policy version and sensor interval (advisory only).',
          'Release or quarantine decision, recorded only by the Quality Officer role.',
          'Warehouse release blocked until an authorized release decision exists.',
        ]}
      />
    </>
  );
}

export function AuditHistoryPage() {
  return (
    <>
      <PageHeader title="Audit History" description="Quality decision history and blockchain reconciliation." />
      <NotImplemented
        milestone="Milestone 5"
        planned={[
          'Quality decision history: who decided, when, why, and on which evidence.',
          'Custody acceptance, incident and decision records anchored on the local blockchain.',
          'Reconciliation of database records against on-chain records.',
          'Partner verification of record and file hashes.',
        ]}
      />
    </>
  );
}
