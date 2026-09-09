import { isPageHidden } from "./visibility.js";

export const browserTransport = {
  hidden: isPageHidden,
  fetch: (...args) => globalThis.fetch(...args),
  hostname: () => location.hostname,
  authenticationRequired: () => {
    location.href = "/login";
  },
  logout: async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    location.href = "/login";
  },
  confirm: async (message) => window.confirm(message),
  prompt: async (message, value = "") => window.prompt(message, value),
  open: (url) => window.open(url, "_blank", "noopener,noreferrer"),
};

// Each mounted NAS view owns one transport. Switching targets never retargets an old request.
export function createNasTransport({
  profile,
  invoke,
  Channel,
  confirm,
  prompt,
  onAuthenticationRequired,
  onThemeChange,
}) {
  const pending = new Map();
  let disposed = false;
  const abortError = () => new DOMException("请求已取消", "AbortError");
  return {
    hidden: isPageHidden,
    hostname: () => new URL(profile.url).hostname,
    authenticationRequired: onAuthenticationRequired,
    themeChanged: (value) => onThemeChange?.(value),
    confirm: (message) => confirm(`${profile.name}\n${message}`),
    prompt,
    open: (url) => invoke("open_external", { url }),
    logout: async () => {
      try {
        await invoke("nas_logout", { id: profile.id });
      } finally {
        onAuthenticationRequired();
      }
    },
    dispose() {
      disposed = true;
      for (const cancel of pending.values()) cancel();
    },
    fetch(path, options = {}) {
      if (disposed || options.signal?.aborted)
        return Promise.reject(abortError());
      return new Promise((resolve, reject) => {
        const id = crypto.randomUUID();
        const channel = new Channel();
        let controller;
        let finished = false;
        let receivedHeaders = false;
        const cleanup = () => {
          finished = true;
          pending.delete(id);
          options.signal?.removeEventListener("abort", cancel);
        };
        const fail = (error) => {
          if (finished) return;
          controller?.error(error);
          reject(error);
          cleanup();
        };
        const cancel = () => {
          if (!finished) {
            invoke("nas_cancel", { id }).catch(() => {});
            fail(abortError());
          }
        };
        const body = new ReadableStream({
          start(c) {
            controller = c;
          },
          cancel,
        });
        pending.set(id, cancel);
        options.signal?.addEventListener("abort", cancel, { once: true });
        channel.onmessage = (packet) => {
          if (finished) return;
          if (packet.type === "headers") {
            receivedHeaders = true;
            resolve(
              new Response(
                [204, 205, 304].includes(packet.status) ? null : body,
                { status: packet.status },
              ),
            );
          } else if (packet.type === "chunk") {
            controller.enqueue(new Uint8Array(packet.bytes));
          } else if (packet.type === "done") {
            controller.close();
            cleanup();
          }
        };
        invoke("nas_request", {
          request: {
            profileId: profile.id,
            requestId: id,
            path,
            method: options.method || "GET",
            body: options.body ?? null,
          },
          onPacket: channel,
        })
          .then(() => {
            if (!receivedHeaders && !finished)
              fail(new Error("NAS 未返回响应"));
          })
          .catch((error) =>
            fail(error instanceof Error ? error : new Error(String(error))),
          );
      });
    },
  };
}
