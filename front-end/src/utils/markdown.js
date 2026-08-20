export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

export function safeMarkdownUrl(value) {
  const cleaned = String(value || "").trim().replace(/&amp;/g, "&");
  return /^(https?:\/\/|mailto:|\/(?!\/)|#)/i.test(cleaned) ? cleaned : "#";
}

function renderInlineMarkdown(value) {
  const code = [];
  let html = escapeHtml(value).replace(/`([^`\n]+)`/g, (_match, content) => {
    const marker = `@@NTLCODE${code.length}@@`;
    code.push(`<code>${content}</code>`);
    return marker;
  });
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)/g, (_match, label, url) => {
    const href = escapeHtml(safeMarkdownUrl(url));
    return `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  html = html.replace(/~~([^~]+)~~/g, "<del>$1</del>");
  html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  code.forEach((snippet, index) => {
    html = html.replace(`@@NTLCODE${index}@@`, snippet);
  });
  return html;
}

export function renderMarkdown(value) {
  const lines = String(value || "").replace(/\r\n?/g, "\n").split("\n");
  const output = [];
  let paragraph = [];
  let listType = "";
  let listItems = [];
  let codeLanguage = "";
  let codeLines = null;
  const flushParagraph = () => {
    if (paragraph.length) output.push(`<p>${paragraph.map(renderInlineMarkdown).join("<br>")}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (listItems.length) output.push(`<${listType}>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</${listType}>`);
    listItems = [];
    listType = "";
  };
  const flushCode = () => {
    if (codeLines === null) return;
    const languageClass = codeLanguage ? ` class="language-${escapeHtml(codeLanguage)}"` : "";
    output.push(`<pre><code${languageClass}>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    codeLines = null;
    codeLanguage = "";
  };
  for (const line of lines) {
    const fence = line.match(/^```([A-Za-z0-9_-]{0,32})\s*$/);
    if (fence) {
      if (codeLines === null) {
        flushParagraph();
        flushList();
        codeLines = [];
        codeLanguage = fence[1] || "";
      } else flushCode();
      continue;
    }
    if (codeLines !== null) {
      codeLines.push(line);
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      output.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    if (/^\s*(?:---+|___+|\*\*\*+)\s*$/.test(line)) {
      flushParagraph();
      flushList();
      output.push("<hr>");
      continue;
    }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      flushList();
      output.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }
    const unordered = line.match(/^\s*[-+*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const nextType = unordered ? "ul" : "ol";
      if (listType && listType !== nextType) flushList();
      listType = nextType;
      listItems.push((unordered || ordered)[1]);
      continue;
    }
    flushList();
    paragraph.push(line);
  }
  flushParagraph();
  flushList();
  flushCode();
  return output.join("");
}
