export function updateController(state, check) {
  let update;
  const busy = () =>
    ["checking", "downloading", "installing", "installed"].includes(
      state.phase,
    );
  return {
    async check() {
      if (busy()) return;
      state.phase = "checking";
      state.error = "";
      state.version = "";
      try {
        await update?.close();
        update = null;
        update = await check({ timeout: 15000 });
        state.version = update?.version || "";
        state.notes = update?.body || "";
        state.phase = update ? "available" : "current";
      } catch (e) {
        state.phase = "error";
        state.error = String(e?.message || e);
      }
    },
    async install() {
      if (!update || busy()) return;
      state.error = "";
      state.phase = "downloading";
      state.downloaded = 0;
      state.total = 0;
      try {
        await update.download(
          (event) => {
            if (event.event === "Started")
              state.total = event.data.contentLength || 0;
            if (event.event === "Progress")
              state.downloaded += event.data.chunkLength;
          },
          { timeout: 300000 },
        );
        state.phase = "installing";
        await update.install();
        state.phase = "installed";
        await update.close();
        update = null;
      } catch (e) {
        state.phase = "available";
        state.error = String(e?.message || e);
      }
    },
  };
}
