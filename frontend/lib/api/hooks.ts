"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./errors";

type State<T> = { baseKey: string | null; fullKey: string | null; data?: T; error?: Error };

export type ApiResource<T> = {
  data: T | undefined;
  error: Error | undefined;
  /** No data yet for this key. */
  loading: boolean;
  /** A reload is in flight while older data is shown. */
  refreshing: boolean;
  reload: () => void;
  /** Local optimistic update. */
  setData: (updater: (prev: T | undefined) => T | undefined) => void;
};

/**
 * Fetch `fetcher()` whenever `key` changes (null = skip). Data for a key is
 * kept while reloading, so polling and refetches never flash a skeleton.
 * Changing `rev` refetches the same key in the background (data is kept).
 */
export function useApi<T>(key: string | null, fetcher: () => Promise<T>, rev: number = 0): ApiResource<T> {
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<State<T>>({ baseKey: null, fullKey: null });
  const fullKey = key === null ? null : `${key}#${nonce}#${rev}`;

  useEffect(() => {
    if (fullKey === null) return;
    let alive = true;
    fetcherRef.current().then(
      (data) => alive && setState({ baseKey: key, fullKey, data }),
      (error: unknown) =>
        alive &&
        setState((s) => ({
          baseKey: key,
          fullKey,
          data: s.baseKey === key ? s.data : undefined,
          error: error instanceof Error ? error : new Error(String(error)),
        })),
    );
    return () => {
      alive = false;
    };
  }, [fullKey, key]);

  const sameKey = state.baseKey === key;
  const data = sameKey ? state.data : undefined;
  const pending = fullKey !== null && state.fullKey !== fullKey;
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback(
    (updater: (prev: T | undefined) => T | undefined) =>
      setState((s) => ({ ...s, data: updater(s.data), error: undefined })),
    [],
  );

  return {
    data,
    error: sameKey && !pending ? state.error : undefined,
    loading: pending && data === undefined,
    refreshing: pending && data !== undefined,
    reload,
    setData,
  };
}

/** Wraps an async action with pending and error state. Resolves to undefined on error. */
export function useMutation<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | Error | null>(null);

  const run = useCallback(async (...args: A): Promise<R | undefined> => {
    setPending(true);
    setError(null);
    try {
      return await fnRef.current(...args);
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)));
      return undefined;
    } finally {
      setPending(false);
    }
  }, []);

  const clear = useCallback(() => setError(null), []);
  return { run, pending, error, clear };
}

/** Calls `fn` every `ms` while `enabled`, and pauses while the tab is hidden. */
export function usePoll(fn: () => void, ms: number, enabled = true) {
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") fnRef.current();
    }, ms);
    return () => window.clearInterval(id);
  }, [ms, enabled]);
}

/**
 * `usePoll` with a ceiling: polls every `ms` while `enabled`, for at most
 * `maxMs` per `key`. Returns true once the ceiling is hit for the current key;
 * a new key (e.g. a newly pending document) starts a fresh window.
 */
export function useBoundedPoll(
  fn: () => void,
  ms: number,
  enabled: boolean,
  { maxMs, key }: { maxMs: number; key: string },
): boolean {
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  const [expiredKey, setExpiredKey] = useState<string | null>(null);
  const expired = expiredKey === key;
  useEffect(() => {
    if (!enabled || expired) return;
    const started = Date.now();
    const id = window.setInterval(() => {
      if (Date.now() - started >= maxMs) {
        window.clearInterval(id);
        setExpiredKey(key);
        return;
      }
      if (document.visibilityState === "visible") fnRef.current();
    }, ms);
    return () => window.clearInterval(id);
  }, [ms, enabled, expired, maxMs, key]);
  return expired;
}

/** `Date.now()`, refreshed every `ms` (0 until the first tick after mount, so SSR matches). */
export function useNow(ms: number): number {
  const [now, setNow] = useState(0);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = window.setTimeout(tick, 0);
    const id = window.setInterval(tick, ms);
    return () => {
      window.clearTimeout(first);
      window.clearInterval(id);
    };
  }, [ms]);
  return now;
}

/** User-facing message for a failed request. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 501) return "This part of the backend isn't live yet.";
    if (e.status === 403) return "Your role can't do that.";
    if (e.status === 404) return "Not found. It may have been deleted.";
    if (e.status === 409) return e.message || "Someone else changed this. Reload and try again.";
    if (e.status >= 500) return "The server hit an error. Try again in a moment.";
    return e.message;
  }
  if (e instanceof Error) return e.message === "Failed to fetch" ? "Can't reach the server." : e.message;
  return "Something went wrong.";
}
