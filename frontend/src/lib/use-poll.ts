"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Loads data now and every `intervalMs` while the tab is visible. Pass a memoized `load`
 * (useCallback): a new one restarts polling, so filters take effect at once.
 */
export function usePoll<T>(load: () => Promise<T>, intervalMs: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const loadRef = useRef(load);

  const reload = useCallback(async () => {
    const current = loadRef.current;
    try {
      const result = await current();
      // Ignore answers for a loader that was replaced meanwhile (an old filter).
      if (loadRef.current === current) {
        setData(result);
        setError("");
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    loadRef.current = load;
    reload();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") reload();
    }, intervalMs);
    return () => clearInterval(timer);
  }, [load, intervalMs, reload]);

  return { data, setData, error, reload };
}
