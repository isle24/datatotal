export function createLatestRequest() {
  let generation = 0;
  let controller = null;
  return {
    get busy() { return controller !== null; },
    cancel() {
      generation++;
      controller?.abort();
      controller = null;
    },
    async run(request, apply) {
      this.cancel();
      const current = generation;
      const active = new AbortController();
      controller = active;
      try {
        const value = await request(active.signal);
        if (current === generation) await apply(value);
      } catch (error) {
        if (current === generation && !active.signal.aborted) throw error;
      } finally {
        if (current === generation) controller = null;
      }
    },
  };
}

export function createPollLoop(task, delay, {
  shouldRun = () => true, onError = () => {}, setTimer = setTimeout, clearTimer = clearTimeout,
} = {}) {
  let generation = 0;
  let timer;
  const schedule = (current) => {
    timer = setTimer(async () => {
      if (current !== generation) return;
      try { if (shouldRun()) await task(); } catch (error) { onError(error); }
      if (current === generation) schedule(current);
    }, delay);
  };
  return {
    start() { this.stop(); schedule(generation); },
    stop() { generation++; clearTimer(timer); },
  };
}
