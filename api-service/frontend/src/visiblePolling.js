export function startVisiblePolling(poll, doc = document) {
  let timer, stopped = false, inFlight = false;
  async function run() {
    if (stopped || doc.hidden || inFlight) return;
    inFlight = true;
    try {
      const again = await poll();
      if (again && !stopped && !doc.hidden) timer = setTimeout(run, 3000);
    } finally { inFlight = false; }
  }
  function onVisibility() { clearTimeout(timer); if (!doc.hidden) run(); }
  doc.addEventListener('visibilitychange', onVisibility);
  run();
  return () => { stopped = true; clearTimeout(timer); doc.removeEventListener('visibilitychange', onVisibility); };
}
