export function navigationRepository(api, transport) {
  return {
    list: async () => {
      try {
        const data = await api("/api/navigation", { localError: true });
        if (!Array.isArray(data?.entries))
          throw Object.assign(new Error("Invalid navigation response"), {
            code: "NON_JSON_RESPONSE",
          });
        return data.entries;
      } catch (error) {
        if (
          error.status === 404 ||
          (error.code === "NON_JSON_RESPONSE" &&
            (!error.status || error.status === 200))
        ) {
          throw Object.assign(
            new Error(
              "此 NAS 尚未支持服务导航。请更新 NAS 服务端至 2026.09.09-2 或更新版本；现有监控、Docker 和 AI 功能可继续使用。",
            ),
            { code: "NAVIGATION_UNAVAILABLE" },
          );
        }
        throw error;
      }
    },
    save: (entry) =>
      api("/api/navigation", {
        localError: true,
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(entry),
      }),
    remove: (id) =>
      api(`/api/navigation/${encodeURIComponent(id)}`, {
        localError: true,
        method: "DELETE",
      }),
    open: (url) => transport.open(url),
    confirm: (message) => transport.confirm(message),
  };
}
