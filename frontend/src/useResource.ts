import { useEffect, useState } from 'react';
import { api, message } from './api';
export function useResource<T>(path: string | null) {
  const [state, setState] = useState<{
    path: string | null;
    data: T | null;
    error: string;
    loading: boolean;
  }>({ path, data: null, error: '', loading: true });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    api<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ path, data, error: '', loading: false });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setState({ path, data: null, error: message(error), loading: false });
      });
    return () => controller.abort();
  }, [path, attempt]);
  useEffect(() => {
    if (!path || !/^\/(emails|alerts|dashboard)(\?|\/|$)/.test(path)) return;
    const update = () => setAttempt((value) => value + 1);
    window.addEventListener('bec-live-update', update);
    return () => window.removeEventListener('bec-live-update', update);
  }, [path]);
  return {
    ...state,
    data: state.path === path ? state.data : null,
    loading: state.path !== path || state.loading,
    reload: () => {
      setState({ path, data: null, error: '', loading: true });
      setAttempt((n) => n + 1);
    },
  };
}
