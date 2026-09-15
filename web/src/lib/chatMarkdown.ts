export function renderChatMarkdown(text: string): string {
  const codeBlocks: string[] = [];
  let out = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang: string, code: string) => {
    const ph = `\x00CB${codeBlocks.length}\x00`;
    codeBlocks.push(
      `<pre class="bg-background my-2 overflow-x-auto rounded-lg border p-3 text-xs"><code>${esc(code.trim())}</code></pre>`,
    );
    return ph;
  });
  out = escKeepPlaceholders(out);
  out = out.replace(/`([^`]+)`/g, '<code class="bg-muted rounded px-1 text-[0.9em]">$1</code>');
  out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/\*(.+?)\*/g, "<em>$1</em>");
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, label: string, url: string) => {
    if (/^(https?:|mailto:|\/)/i.test(url)) {
      return `<a class="text-primary underline" href="${url.replace(/"/g, "&quot;")}" target="_blank" rel="noreferrer">${label}</a>`;
    }
    return label;
  });
  out = out.replace(/^### (.+)$/gm, '<h4 class="mt-2 mb-1 font-medium">$1</h4>');
  out = out.replace(/^## (.+)$/gm, '<h3 class="mt-3 mb-1 font-medium">$1</h3>');
  out = out.replace(/^# (.+)$/gm, '<h2 class="mt-3 mb-1 text-lg font-medium">$1</h2>');
  out = out.replace(/^&gt; (.+)$/gm, '<blockquote class="border-border text-muted-foreground my-1 border-l-2 pl-3 text-sm">$1</blockquote>');
  out = out.replace(/^---+$/gm, '<hr class="border-border my-3">');
  out = out.replace(/^- (.+)$/gm, "• $1");
  out = out.replace(/\n/g, "<br>");
  for (let i = 0; i < codeBlocks.length; i++) {
    out = out.replace(`\x00CB${i}\x00`, codeBlocks[i]);
  }
  return out;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escKeepPlaceholders(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
