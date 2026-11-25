import { ErrorNote } from "./ErrorNote";
import { useState } from "react";
import { invokeFor } from "../lib/invoke";
import { errorWithTitle } from "../lib/diagnostics";
import { useI18n as useUiI18n, Group, Modal, SearchBox, Toggle } from "trm-ui";
import { Btn, Warn } from "./ui";
import { useI18n } from "../i18n";
import { CatalogTransition } from "./CatalogTransition";

type ExportVoice = { id: string; name: string };
type ExportResult = { folder: string; packs: Array<{ name: string; error?: string }> };

export function ExportVoicePackages({ open, voices, onClose }: {
  open: boolean;
  voices: ExportVoice[];
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { t: uiText } = useUiI18n();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ExportResult>();
  const [requestedIds, setRequestedIds] = useState<string[]>([]);
  const search = query.trim().toLocaleLowerCase();
  const visible = voices.filter((voice) => voice.name.toLocaleLowerCase().includes(search));
  const ids = voices.filter((voice) => selected.has(voice.id)).map((voice) => voice.id);
  const allShown = visible.length > 0 && visible.every((voice) => selected.has(voice.id));
  const failures = result?.packs.filter((row) => row.error) ?? [];
  const retryIds = result?.packs.flatMap((row, index) => {
    const id = requestedIds[index];
    return row.error && id ? [id] : [];
  }) ?? [];

  function close() {
    if (busy) return;
    onClose();
  }

  function toggle(changes: string[], checked: boolean) {
    setSelected((previous) => {
      const next = new Set(previous);
      for (const id of changes) {
        if (checked) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  async function start(dirs: string[]) {
    setBusy(true);
    setError("");
    try {
      const exported = await invokeFor<ExportResult | null>("importexport", "publication_export_packs", { dirs });
      if (exported) {
        setRequestedIds(dirs);
        setResult(exported);
      }
    } catch (cause) {
      setError(errorWithTitle(cause, "publication.packReadError", "importexport"));
    } finally {
      setBusy(false);
    }
  }

  const title = t("publication.exportPacks");
  return (
    <Modal open={open} onClose={close} label={title} width={640}>
      <div className="space-y-4 p-6">
        <h2 className="m-0 text-[16px] font-semibold">{title}</h2>
        {error && <Warn><ErrorNote text={error} feature="importexport" /></Warn>}
        <CatalogTransition scope={result ? "result" : "selection"} order={["selection", "result"]}>
          {result ? (
            <div className="space-y-3 text-[13px]" role="status">
              <p className="m-0">{t("publication.exportedCount", { v0: result.packs.length - failures.length, v1: result.packs.length })}</p>
              {result.packs.length > failures.length && <p className="break-all text-[var(--help)]">{result.folder}</p>}
              {failures.length > 0 && <Group>
                <ul className="m-0 max-h-[36vh] list-none space-y-3 overflow-y-auto p-0">
                  {failures.map((row, index) => <li key={index}>
                    <p className="m-0">{t("publication.packFailed", { v0: row.name })}</p>
                    <ErrorNote text={row.error} feature="importexport" />
                  </li>)}
                </ul>
              </Group>}
            </div>
          ) : (
            <div className="space-y-3">
              <SearchBox full value={query} onChange={setQuery} ariaLabel={uiText("ui.common.search")} />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Toggle look="inline" checked={allShown} disabled={busy || !visible.length}
                  label={t(search ? "publication.selectResults" : "publication.selectAll")}
                  onChange={(checked) => toggle(visible.map((voice) => voice.id), checked)} />
                <span className="text-[11.5px] tabular-nums text-[var(--help)]" aria-live="polite">
                  {t("publication.selectedCount", { v0: ids.length })}
                </span>
              </div>
              {visible.length ? <Group>
                <div className="max-h-[36vh] divide-y divide-[var(--hairline)] overflow-y-auto">
                  {visible.map((voice) => (
                    <div key={voice.id} className="flex items-center justify-between gap-3 py-2">
                      <Toggle look="inline" className="min-w-0 break-words" checked={selected.has(voice.id)}
                        disabled={busy} label={voice.name} onChange={(checked) => toggle([voice.id], checked)} />
                    </div>
                  ))}
                </div>
              </Group> : <p className="text-[13px] text-[var(--help)]">{t("publication.noMatchingModels")}</p>}
            </div>
          )}
        </CatalogTransition>
        <div className="flex flex-wrap justify-end gap-2">
          <Btn disabled={busy} onClick={close}>{uiText(result ? "ui.common.close" : "ui.common.cancel")}</Btn>
          {result ? retryIds.length > 0 && <Btn primary busy={busy} disabled={busy}
            onClick={() => void start(retryIds)}>{t("publication.retryExport")}</Btn>
            : <Btn primary busy={busy} disabled={!ids.length || busy} onClick={() => void start(ids)}>{title}</Btn>}
        </div>
      </div>
    </Modal>
  );
}
