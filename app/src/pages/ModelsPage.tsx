import { useCallback, useEffect, useMemo, useRef, useState, memo } from "react";
import { StoreDialog } from "../components/StoreDialog";
import { SegmentControl } from "../components/SegmentControl";
import { AdBanner } from "../components/AdBanner";
import { openExternal, type PlazaItem } from "../lib/plaza";
import { tip } from "../lib/glossary";
import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";
import { setHot } from "../lib/engine";
import {
  bindIndex,
  colsForWidth,
  coverSrc,
  deleteProfile,
  deleteVoice,
  exportProfile,
  filterSortModels,
  importProfile,
  importVoices,
  listIndex,
  listProfiles,
  listVoices,
  modelKey,
  openModelsDir,
  promoteLegacy,
  renameVoice,
  saveProfile,
  selectVoice,
  unbindIndex,
  applyIndex,
  applyProfile,
  type IndexItem,
  type ProfileItem,
  type VoiceModel,
} from "../lib/voices";

export type ModelsPageProps = {
  /** Models-page placement, owned by App so the feed is fetched once. */
  banner?: PlazaItem | null;
  onVoiceChange?: (info: {
    model: VoiceModel;
    pitch?: number;
    formant?: number;
    profileSummary?: string;
  }) => void;
};

type SortKey = "default" | "name" | "index";

function ModelsPageImpl({ banner = null, onVoiceChange }: ModelsPageProps) {
  const [models, setModels] = useState<VoiceModel[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("default");
  const [page, setPage] = useState(0);
  const [cols, setCols] = useState(5);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [storeOpen, setStoreOpen] = useState(false);
  const [indexItems, setIndexItems] = useState<IndexItem[]>([]);
  const [profiles, setProfiles] = useState<ProfileItem[]>([]);
  const [menu, setMenu] = useState<{
    x: number;
    y: number;
    model: VoiceModel;
  } | null>(null);
  const gridRef = useRef<HTMLDivElement>(null);

  const selected = useMemo(
    () => models.find((m) => modelKey(m) === selectedKey) || null,
    [models, selectedKey],
  );

  const view = useMemo(
    () => filterSortModels(models, query, sort),
    [models, query, sort],
  );

  const pageSize = cols * 3;
  const totalPages = Math.max(1, Math.ceil(view.length / pageSize) || 1);
  const pageClamped = Math.min(page, totalPages - 1);
  const pageView = view.slice(
    pageClamped * pageSize,
    pageClamped * pageSize + pageSize,
  );

  const statusSub = useMemo(() => {
    if (!models.length) return "共 0 个音色";
    if (query.trim() && view.length !== models.length) {
      return `共 ${models.length} 个 · 匹配 ${view.length} 个`;
    }
    const cur = selected?.name || models[0]?.name || "—";
    return `共 ${models.length} 个 · 使用中：${cur}`;
  }, [models, query, view.length, selected]);

  const reload = useCallback(async () => {
    try {
      const cat = await listVoices();
      setModels(cat.models || []);
      const idx = cat.selected_idx ?? -1;
      if (idx >= 0 && cat.models?.[idx]) {
        setSelectedKey(modelKey(cat.models[idx]));
      } else if (cat.models?.[0]) {
        setSelectedKey(modelKey(cat.models[0]));
      } else {
        setSelectedKey("");
      }
    } catch (e) {
      setMsg(String(e));
    }
  }, []);

  const reloadPanels = useCallback(async (m: VoiceModel | null) => {
    if (!m || m.source !== "user_data" || !m.dir || m.missing) {
      setIndexItems([]);
      setProfiles([]);
      return;
    }
    try {
      const [ix, pr] = await Promise.all([
        listIndex(m.dir),
        listProfiles(m.dir),
      ]);
      setIndexItems(ix.items || []);
      setProfiles(pr.items || []);
    } catch {
      setIndexItems([]);
      setProfiles([]);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    void reloadPanels(selected);
  }, [selected, reloadPanels]);

  useEffect(() => {
    const el = gridRef.current?.parentElement || gridRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width || window.innerWidth;
      setCols(colsForWidth(w));
    });
    ro.observe(el);
    setCols(colsForWidth(el.clientWidth || window.innerWidth));
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    setPage(0);
  }, [query, sort]);

  useEffect(() => {
    if (page > totalPages - 1) setPage(Math.max(0, totalPages - 1));
  }, [page, totalPages]);

  useEffect(() => {
    const close = () => setMenu(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, []);

  const onUse = async (m: VoiceModel) => {
    if (m.missing) {
      setMsg("这个音色的模型文件缺失或没下载完整");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const res = await selectVoice(m);
      setSelectedKey(modelKey(m));
      if (res.pitch != null || res.formant != null) {
        try {
          await setHot({
            pitch: Number(res.pitch ?? 0),
            formant: Number(res.formant ?? 0),
          });
        } catch {
          /* worker may be idle */
        }
      }
      onVoiceChange?.({
        model: (res.model as VoiceModel) || m,
        pitch: res.pitch as number | undefined,
        formant: res.formant as number | undefined,
        profileSummary: res.profile_summary,
      });
      await reload();
    } catch (e) {
      setMsg(String(e));
    } finally {
      setBusy(false);
    }
  };

  const manageable =
    selected &&
    selected.source === "user_data" &&
    !!selected.dir &&
    !selected.missing;
  const promotable =
    selected &&
    selected.source === "legacy_weights" &&
    !!selected.path &&
    !selected.missing;
  const blockReason = !selected
    ? "还没有选择音色。"
    : selected.missing
      ? "这个音色的模型文件缺失或没下载完整，先修好或删除后再绑定。"
      : promotable
        ? "这是旧版散装音色，先「转为可管理音色」就能绑定检索库和配置档案。"
        : !manageable
          ? "这个音色不支持绑定。"
          : "";

  return (
    <PagePad>
      <PageHead
        title="音色目录"
        sub={statusSub}
        actions={
          <>
            <Btn primary onClick={() => setStoreOpen(true)}>
              社区音色
            </Btn>
            <Btn
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                try {
                  const r = await importVoices(selected?.dir);
                  if (r.errors?.length) {
                    setMsg(r.errors.map((e) => e.error).join("；"));
                  }
                  await reload();
                } catch (e) {
                  if (String(e) !== "已取消") setMsg(String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              导入音色…
            </Btn>
            <Btn
              onClick={async () => {
                await reload();
                setMsg("已刷新");
              }}
            >
              刷新
            </Btn>
            <Btn
              onClick={() => {
                void openModelsDir().catch((e) => setMsg(String(e)));
              }}
            >
              打开目录
            </Btn>
          </>
        }
      />

      {msg ? (
        <div className="text-[12.5px] text-[var(--meta)] mt-2">{msg}</div>
      ) : null}

      <AdBanner banner={banner} />

      <Block>
        <div className="flex items-center gap-3 flex-wrap mb-[18px]">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索音色 / 标签…"
            className="inline-flex min-w-[230px] px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]"
          />
          <span className="ml-auto">
            <SegmentControl<SortKey>
              value={sort}
              onChange={setSort}
              options={[
                { id: "default", label: "默认" },
                { id: "name", label: "名称" },
                { id: "index", label: "检索库" },
              ]}
            />
          </span>
        </div>

        <div
          ref={gridRef}
          className="grid gap-x-4 gap-y-[22px]"
          style={{
            gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
          }}
        >
          {!models.length ? (
            <div className="col-span-full text-[13.5px] text-[var(--ink-muted)] py-10 px-2">
              还没有音色。点「社区音色」在线下载，或点「导入音色」添加你自己的音色文件。
            </div>
          ) : !view.length ? (
            <div className="col-span-full text-[13.5px] text-[var(--ink-muted)] py-10 px-2">
              没有匹配「{query}」的音色。清空搜索可看全部。
            </div>
          ) : (
            pageView.map((v) => {
              const cur = modelKey(v) === selectedKey;
              const src = coverSrc(v.cover);
              return (
                <div
                  key={modelKey(v)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setMenu({ x: e.clientX, y: e.clientY, model: v });
                  }}
                >
                  <div className="aspect-[4/3] rounded-[var(--r)] grid place-items-center relative overflow-hidden bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] text-[color-mix(in_srgb,var(--ink)_32%,transparent)] text-2xl">
                    {src ? (
                      <img
                        src={src}
                        alt=""
                        className="absolute inset-0 w-full h-full object-cover"
                        draggable={false}
                      />
                    ) : (
                      <span>{(v.name || "?").slice(0, 4)}</span>
                    )}
                    {cur ? (
                      <span className="absolute top-2.5 right-2.5 text-[11px] text-[var(--accent)] font-semibold drop-shadow">
                        使用中
                      </span>
                    ) : null}
                    {v.has_index || v.index ? (
                      <span className="absolute right-2.5 bottom-2 text-[11px] text-[var(--meta)]">
                        ✓ 检索库
                      </span>
                    ) : null}
                    {v.missing ? (
                      <span className="absolute left-2.5 top-2.5 text-[11px] text-[#c44]">
                        缺失
                      </span>
                    ) : null}
                  </div>
                  <div className="text-[11.5px] text-[var(--meta)] mt-2.5">
                    {v.tag || "音色"}
                  </div>
                  <div className="text-[14.5px] font-semibold mt-0.5 truncate">
                    {v.name}
                  </div>
                  <div className="text-xs text-[var(--meta)] mt-0.5 truncate">
                    {v.author ? `作者 : ${v.author}` : "作者 : —"}
                  </div>
                  <div className="mt-2.5">
                    {cur ? (
                      <Btn on uw disabled>
                        使用中
                      </Btn>
                    ) : (
                      <Btn uw disabled={busy || !!v.missing} onClick={() => void onUse(v)}>
                        使用
                      </Btn>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {view.length > pageSize ? (
          <div className="flex items-center justify-center gap-3 mt-[26px] text-[12.5px] text-[var(--meta)]">
            <Btn
              disabled={pageClamped <= 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              上一页
            </Btn>
            <span>
              第{" "}
              <b className="text-[var(--ink)] font-semibold">
                {pageClamped + 1}
              </b>{" "}
              /{" "}
              <b className="text-[var(--ink)] font-semibold">{totalPages}</b>{" "}
              页 · 共{" "}
              <b className="text-[var(--ink)] font-semibold">{view.length}</b>{" "}
              个
            </span>
            <Btn
              disabled={pageClamped >= totalPages - 1}
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            >
              下一页
            </Btn>
          </div>
        ) : null}
      </Block>

      <Block
        title="特征索引文件（.index）"
        titleTip={tip("检索库")}
        note={manageable ? "检索库可选；无 index 也能用" : undefined}
        action={
          manageable ? (
            <Btn
              onClick={async () => {
                try {
                  const r = await bindIndex(selected!.dir);
                  setIndexItems(r.items || []);
                  await reload();
                } catch (e) {
                  if (String(e) !== "已取消") setMsg(String(e));
                }
              }}
            >
              绑定 index 文件…
            </Btn>
          ) : undefined
        }
      >
        {!manageable ? (
          <div className="text-[13px] text-[var(--meta)]">
            {blockReason}
            {promotable ? (
              <div className="mt-2">
                <Btn
                  onClick={async () => {
                    try {
                      await promoteLegacy(selected!.path);
                      await reload();
                      setMsg("已转为可管理音色");
                    } catch (e) {
                      setMsg(String(e));
                    }
                  }}
                >
                  转为可管理音色
                </Btn>
              </div>
            ) : null}
          </div>
        ) : (
          <Group>
            {indexItems.map((it) => (
              <ListItem
                key={it.path || "__none__"}
                title={it.label}
                desc={it.badge || undefined}
                right={
                  <>
                    {it.active ? (
                      <Btn on uw disabled>
                        使用中
                      </Btn>
                    ) : (
                      <Btn
                        uw
                        onClick={async () => {
                          const r = await applyIndex(selected!.dir, it.path);
                          setIndexItems(r.items || []);
                          await reload();
                        }}
                      >
                        使用
                      </Btn>
                    )}
                    {it.path && !it.active ? (
                      <Btn
                        onClick={async () => {
                          const r = await unbindIndex(selected!.dir, it.path);
                          setIndexItems(r.items || []);
                          await reload();
                        }}
                      >
                        解绑
                      </Btn>
                    ) : null}
                  </>
                }
              />
            ))}
          </Group>
        )}
      </Block>

      <Block
        title="配置档案"
        note="同一个音色可存多套参数（音高／音效／性能），点「使用」即切换；可导出分享，也能导入其他档案"
      >
        {!manageable ? (
          <div className="text-[13px] text-[var(--meta)]">{blockReason}</div>
        ) : (
          <>
            <Group>
              {profiles.map((p) => (
                <ListItem
                  key={p.id || "__default__"}
                  meta={p.source_label}
                  title={p.name}
                  desc={p.desc || undefined}
                  right={
                    <>
                      {p.active ? (
                        <Btn on uw disabled>
                          使用中
                        </Btn>
                      ) : (
                        <Btn
                          uw
                          onClick={async () => {
                            const r = await applyProfile(selected!.dir, p.id);
                            if (r.profiles?.items) setProfiles(r.profiles.items);
                            else {
                              const pr = await listProfiles(selected!.dir);
                              setProfiles(pr.items || []);
                            }
                            if (r.hot) {
                              try {
                                await setHot({
                                  pitch:
                                    r.hot.pitch != null
                                      ? Number(r.hot.pitch)
                                      : undefined,
                                  formant:
                                    r.hot.formant != null
                                      ? Number(r.hot.formant)
                                      : undefined,
                                  index_rate:
                                    r.hot.index_rate != null
                                      ? Number(r.hot.index_rate)
                                      : undefined,
                                  rms_mix_rate:
                                    r.hot.rms_mix_rate != null
                                      ? Number(r.hot.rms_mix_rate)
                                      : undefined,
                                  threhold:
                                    r.hot.threhold != null
                                      ? Number(r.hot.threhold)
                                      : undefined,
                                });
                              } catch {
                                /* */
                              }
                            }
                            if (selected) {
                              onVoiceChange?.({
                                model: selected,
                                pitch: r.pitch as number | undefined,
                                formant: r.formant as number | undefined,
                                profileSummary: r.profile_summary,
                              });
                            }
                          }}
                        >
                          使用
                        </Btn>
                      )}
                      {p.id ? (
                        <Btn
                          onClick={async () => {
                            if (
                              !window.confirm(
                                `删除档案「${p.name}」？此操作无法撤销。`,
                              )
                            )
                              return;
                            await deleteProfile(selected!.dir, p.id);
                            const pr = await listProfiles(selected!.dir);
                            setProfiles(pr.items || []);
                          }}
                        >
                          删除
                        </Btn>
                      ) : null}
                    </>
                  }
                />
              ))}
              <ListItem
                right={
                  <>
                    <Btn
                      onClick={async () => {
                        const name = window.prompt("档案名称", "我的档案");
                        if (name == null) return;
                        await saveProfile(selected!.dir, name);
                        const pr = await listProfiles(selected!.dir);
                        setProfiles(pr.items || []);
                      }}
                    >
                      另存当前为档案
                    </Btn>
                    <Btn
                      onClick={async () => {
                        try {
                          await importProfile(selected!.dir);
                          const pr = await listProfiles(selected!.dir);
                          setProfiles(pr.items || []);
                        } catch (e) {
                          if (String(e) !== "已取消") setMsg(String(e));
                        }
                      }}
                    >
                      导入档案…
                    </Btn>
                    <Btn
                      onClick={async () => {
                        try {
                          await exportProfile(selected!.dir);
                          setMsg("档案已导出");
                        } catch (e) {
                          if (String(e) !== "已取消") setMsg(String(e));
                        }
                      }}
                    >
                      导出当前档案（可分享）…
                    </Btn>
                  </>
                }
              />
            </Group>
          </>
        )}
      </Block>

      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          model={menu.model}
          onClose={() => setMenu(null)}
          onDone={async () => {
            setMenu(null);
            await reload();
          }}
          onMessage={setMsg}
        />
      ) : null}

      <StoreDialog
        open={storeOpen}
        onClose={() => setStoreOpen(false)}
        onInstalled={() => {
          void reload();
        }}
      />
    </PagePad>
  );
}

function ContextMenu({
  x,
  y,
  model,
  onClose,
  onDone,
  onMessage,
}: {
  x: number;
  y: number;
  model: VoiceModel;
  onClose: () => void;
  onDone: () => void;
  onMessage: (s: string) => void;
}) {
  const items: { label: string; action: () => void; danger?: boolean }[] = [];
  if (model.source === "user_data" && model.dir) {
    items.push({
      label: "重命名",
      action: async () => {
        const n = window.prompt("新名称", model.name);
        if (!n) return;
        try {
          await renameVoice(model.dir, n);
          onDone();
        } catch (e) {
          onMessage(String(e));
        }
      },
    });
    items.push({
      label: "删除",
      danger: true,
      action: async () => {
        if (
          !window.confirm(
            "模型文件、绑定的配置档案会一起删除，无法撤销。\n\n确认删除？",
          )
        )
          return;
        try {
          await deleteVoice(model.dir);
          onDone();
        } catch (e) {
          onMessage(String(e));
        }
      },
    });
  }
  if (model.author_url) {
    const authorUrl = model.author_url;
    items.push({
      label: "打开作者链接",
      action: () => {
        // Through the shell so it lands in the user's own browser, and so the
        // http/https check applies — a catalog-supplied URL is untrusted.
        void openExternal(authorUrl);
        onClose();
      },
    });
  }
  if (model.source === "legacy_weights" && model.path) {
    items.push({
      label: "转为可管理音色",
      action: async () => {
        try {
          await promoteLegacy(model.path);
          onDone();
        } catch (e) {
          onMessage(String(e));
        }
      },
    });
  }
  if (!items.length) {
    items.push({
      label: "无可用操作",
      action: onClose,
    });
  }

  return (
    <div
      className="fixed z-[90] min-w-[160px] py-1 rounded-[var(--rs)] bg-[var(--surface)] shadow-[0_8px_28px_rgba(0,0,0,0.18)]"
      style={{ left: x, top: y }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((it) => (
        <button
          key={it.label}
          type="button"
          className={[
            "block w-full text-left border-0 bg-transparent px-3.5 py-2 text-[13px] cursor-pointer",
            it.danger
              ? "text-[#c44] hover:bg-[color-mix(in_srgb,#c44_10%,transparent)]"
              : "text-[var(--ink)] hover:bg-[color-mix(in_srgb,var(--ink)_5%,transparent)]",
          ].join(" ")}
          onClick={() => void it.action()}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

/**
 * Memoised: App re-renders on every engine status tick (2.5x a second while
 * converting). Without this the whole page tree was rebuilt each time for a
 * mic-level change that only the dock cares about.
 */
export const ModelsPage = memo(ModelsPageImpl);
