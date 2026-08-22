/**
 * 把工人甩过来的一长段报错拆成「正文 + 详情」。
 *
 * 规格书 1.3：正文 = 最后一行真实报错，完整 traceback 进「详情」/复制/日志。
 * 以前 ErrorNote 取的是第一行 —— traceback 的第一行永远是
 * `Traceback (most recent call last):`，26.8.22/4 截图里用户看到的就是这个。
 */

export function splitErrorText(text: string): {
  head: string;
  detail: string;
  hasMore: boolean;
} {
  const raw = text || "";
  const lines = raw
    .split("\n")
    .map((l) => l.trimEnd())
    .filter((l) => l.trim().length > 0);
  if (lines.length === 0) {
    return { head: raw, detail: "", hasMore: false };
  }
  const looksTb =
    /^traceback\b/i.test(lines[0].trim()) ||
    lines.some((l) => /^\s*File\s+".+"/.test(l));
  if (looksTb) {
    let last = lines[lines.length - 1].trim();
    for (let i = lines.length - 1; i >= 0; i--) {
      const ln = lines[i].trim();
      if (ln.startsWith("File ") || /^traceback\b/i.test(ln)) continue;
      last = ln;
      break;
    }
    return { head: last, detail: raw, hasMore: true };
  }
  return {
    head: lines[0],
    detail: lines.slice(1).join("\n"),
    hasMore: lines.length > 1,
  };
}
