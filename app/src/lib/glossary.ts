/**
 * Compatibility shim — terms live in `app/i18n/locales/*.json`.
 * Prefer `useGlossary` / `tip` from `../i18n` in new code.
 */
export {
  tip,
  getGlossary,
  termsFrom,
  type GlossaryTerm,
} from "../i18n/glossary";
export { useGlossary, useGlossarySectionTitle } from "../i18n/index";

import { getGlossary } from "../i18n/glossary";

/**
 * @deprecated Snapshot of zh-CN terms at first access. Prefer useGlossary().
 * Help pages that still import GLOSSARY get a live getter via this proxy.
 */
export const GLOSSARY = new Proxy([] as import("../i18n/glossary").GlossaryTerm[], {
  get(_target, prop, receiver) {
    const list = getGlossary();
    if (prop === "length") return list.length;
    if (prop === Symbol.iterator) {
      return list[Symbol.iterator].bind(list);
    }
    if (typeof prop === "string" && /^\d+$/.test(prop)) {
      return list[Number(prop)];
    }
    const v = Reflect.get(list, prop, receiver);
    return typeof v === "function" ? v.bind(list) : v;
  },
});
