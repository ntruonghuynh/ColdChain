import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../api/client';

export type AsyncState<T> =
  | { status: 'loading'; data: null; error: null }
  | { status: 'success'; data: T; error: null }
  | { status: 'error'; data: null; error: ApiError };

/**
 * Runs an API call on mount (and on `reload`). Cancels the request on unmount.
 * `fetcher` must be stable (define it outside the component or wrap in useCallback).
 */
export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T>): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading', data: null, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: 'loading', data: null, error: null });
    fetcher(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: 'success', data, error: null });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const error =
          err instanceof ApiError ? err : new ApiError({ kind: 'invalid_response', message: String(err) });
        setState({ status: 'error', data: null, error });
      });
    return () => controller.abort();
  }, [fetcher, attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { ...state, reload };
}
