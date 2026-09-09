export function safeNavigationUrl(value) {
  try {
    if (/[\\\u0000-\u001f]/.test(value)) return "";
    const url = new URL(value.trim());
    return ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : "";
  } catch {
    return "";
  }
}

export function serviceUrl(port, hostname) {
  const host =
    hostname.includes(":") && !hostname.startsWith("[")
      ? `[${hostname}]`
      : hostname;
  const url = new URL(
    `${port.scheme === "https" ? "https" : "http"}://${host}:${Number(port.hostPort)}`,
  );
  const path = String(port.path || "/");
  // Set the path on the selected NAS origin; a // prefix must never replace the host.
  const separator = path.indexOf("?");
  url.pathname = separator < 0 ? path : path.slice(0, separator);
  url.search = separator < 0 ? "" : path.slice(separator);
  return url.href;
}

export function dockerBookmark(container, port, hostname) {
  if (port.accessMode !== "web") throw new Error("请先将端口配置为 Web 服务");
  return {
    name: `${container.name}${port.label ? ` · ${port.label}` : ""}`.slice(
      0,
      120,
    ),
    url: serviceUrl(port, hostname),
    icon: container.containerIcon || "",
    group: "Docker",
    notes: "",
    sortOrder: 0,
    sourceKey:
      `docker:${container.name}:${port.proto || "tcp"}:${port.hostPort}`.slice(
        0,
        256,
      ),
  };
}

export async function navigationIcon(source) {
  if (!source) return "";
  const objectUrl = source instanceof Blob ? URL.createObjectURL(source) : null;
  if (
    !objectUrl &&
    !/^data:image\/(png|jpeg|webp|gif|svg\+xml)[;,]/.test(source)
  )
    return "";
  try {
    const image = new Image();
    image.src = objectUrl || source;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 96;
    const scale = Math.min(96 / image.width, 96 / image.height);
    canvas
      .getContext("2d")
      .drawImage(
        image,
        (96 - image.width * scale) / 2,
        (96 - image.height * scale) / 2,
        image.width * scale,
        image.height * scale,
      );
    const encoded = canvas.toDataURL("image/png");
    if (encoded.length > 32768)
      throw new Error("图标压缩后仍然过大，请换一张简单的图标");
    return encoded;
  } finally {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  }
}
