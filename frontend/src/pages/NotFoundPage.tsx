import { Link } from 'react-router';
import { EmptyState } from '../components/ui/States';

export function NotFoundPage() {
  return (
    <EmptyState
      title="Page not found"
      description={
        <>
          This address does not exist. <Link className="font-medium text-cyan-700 hover:underline" to="/">Go to the overview</Link>.
        </>
      }
    />
  );
}
