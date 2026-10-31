import { getTLocale, t } from "../i18n/t";

/**
 * 把几项信息连成一行的两种写法，界面上不用「·」拼接（规则见 TRM UI「文本要求」页）。
 * listText：同类的几项，按当前语言写成「A、B和C」。重复项保留，例如两块同型号显卡。
 * joinClauses：一行里的几段说明，用当前语言的分句标点连接，空的跳过。
 */
export function listText(values: readonly string[]): string {
  const items = values.map((v) => v.trim()).filter(Boolean);
  if (items.length < 2) return items[0] || "";
  try {
    const ListFormat = (Intl as unknown as {
      ListFormat?: new (locale: string, options: { type: "conjunction"; style: "short" }) => { format(v: string[]): string };
    }).ListFormat;
    if (ListFormat) return new ListFormat(getTLocale() || "zh-CN", { type: "conjunction", style: "short" }).format(items);
    return items.join(t("s.clauseSep"));
  } catch {
    return items.join(t("s.clauseSep"));
  }
}

export function joinClauses(parts: ReadonlyArray<string | false | null | undefined>): string {
  return parts.filter((p): p is string => !!p).join(t("s.clauseSep"));
}
