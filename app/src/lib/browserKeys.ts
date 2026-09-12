export function isBrowserKey(e: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "shiftKey" | "altKey">): boolean {
  const key = e.key.toLowerCase();
  const mod = e.ctrlKey || e.metaKey;
  if (!mod && !e.altKey && ["f1", "f3", "f5", "f6", "f7", "f9", "f12"].includes(key)) return true;
  if (mod && !e.altKey && ["r", "p", "f", "g", "s", "u", "+", "-", "=", "0"].includes(key)) return true;
  return mod && e.shiftKey && ["i", "j", "c"].includes(key);
}
