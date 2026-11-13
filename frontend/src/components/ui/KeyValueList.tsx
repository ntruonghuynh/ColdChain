import type { ReactNode } from 'react';

export function KeyValueList({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="divide-y divide-slate-100">
      {items.map((item) => (
        <div key={item.label} className="grid grid-cols-1 gap-1 py-2.5 sm:grid-cols-3 sm:gap-4">
          <dt className="text-sm text-slate-500">{item.label}</dt>
          <dd className="text-sm font-medium break-words text-slate-900 sm:col-span-2">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
