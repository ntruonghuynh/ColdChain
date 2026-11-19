import type { ButtonHTMLAttributes } from 'react';

export function Button({
  variant = 'secondary',
  className = '',
  type = 'button',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' }) {
  const styles =
    variant === 'primary'
      ? 'bg-navy-800 text-white hover:bg-navy-700'
      : 'bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50';
  return (
    <button
      type={type}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${styles} ${className}`}
      {...props}
    />
  );
}
