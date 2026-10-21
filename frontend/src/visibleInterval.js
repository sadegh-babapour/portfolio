// Like setInterval, but only while the page is visible. A background tab stops polling
// the API and redrawing the map; when it is shown again, `onResume` runs, then `task`
// runs at once and the interval restarts. Returns a cleanup function.
export function startVisibleInterval(task, intervalMs, { onResume, doc = globalThis.document } = {}) {
  let timer = null;

  const isHidden = () => doc?.visibilityState === "hidden";
  const start = () => {
    if (timer === null) timer = setInterval(task, intervalMs);
  };
  const stop = () => {
    if (timer !== null) clearInterval(timer);
    timer = null;
  };
  const onVisibilityChange = () => {
    if (isHidden()) {
      stop();
    } else if (timer === null) {
      onResume?.();
      task();
      start();
    }
  };

  if (!isHidden()) {
    task();
    start();
  }
  doc?.addEventListener?.("visibilitychange", onVisibilityChange);

  return () => {
    stop();
    doc?.removeEventListener?.("visibilitychange", onVisibilityChange);
  };
}
