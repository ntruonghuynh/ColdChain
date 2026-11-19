import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';

export function LoginPage() {
  const { identity, login, busy } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      await login(username, password);
      setPassword('');
      navigate('/quality-review');
    } catch (reason) {
      setPassword('');
      setError(reason instanceof ApiError ? reason.message : 'Sign in failed. Check the account and try again.');
    }
  };

  return <>
    <PageHeader title="Sign in" description="Use an account configured by the local ColdChain backend. Credentials are not saved by this page." />
    <Card className="max-w-xl">
      {identity ? <div className="space-y-3 text-sm"><p>Signed in as <strong>{identity.username}</strong></p><p>Roles: {identity.roles.join(', ') || 'none'}</p><Link className="text-cyan-700 hover:underline" to="/">Return to Overview</Link></div> :
        <form className="space-y-4" onSubmit={submit}>
          <label className="block text-sm font-medium text-slate-700">Username<input className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
          <label className="block text-sm font-medium text-slate-700">Password<input className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error && <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
          <p className="text-xs text-slate-500">The bearer token is held in memory only and is cleared when the page reloads or the session is rejected.</p>
          <Button type="submit" variant="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</Button>
        </form>}
    </Card>
  </>;
}
