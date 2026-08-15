import { useCallback, useEffect, useMemo, useRef, useState, memo, type MouseEvent } from "react";
import { SegmentControl } from "../components/SegmentControl";
import { AdBanner } from "../components/AdBanner";
import { DspPresetGrid, type DspPreset } from "../components/DspPresetGrid";
import { DspPresetEditor } from "../components/DspPresetEditor";
import { openExternal, type PlazaItem } from "../lib/plaza";
import { tip } from "../lib/glossary";
import { resolveCover, useCoverCache } from "../lib/cover";
import { Block, Btn, Group, ListItem, PageHead, PagePad } from "../components/ui";
import { listen } from "@tauri-apps/api/event";
import { setHot } from "../lib/engine";
import { getConfig } from "../lib/config";
import { t } from "../i18n/t";
import { askConfirm, askPrompt } from "../lib/webDialog";
import {
  bindIndex,
  clearVoice,
  colsForWidth,
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

type SortKey = "default" | "name" | "index";
/** 列表看的是哪一种东西。RVC 音色和 DSP 预设不混排。 */
type Kind = "rvc" | "dsp";

export type ModelsPageProps = {
  /** 跳到广场。社区音色现在住在那儿。 */
  onOpenPlaza?: () => void;
  /** 从首页进来时直接停在 DSP 预设。 */
  focusKind?: Kind;
  /** 加一就再切一次 focusKind（连点首页入口也要生效）。 */
  focusNonce?: number;
  /** Models-page placement, owned by App so the feed is fetched once. */
  banner?: PlazaItem | null;
  onVoiceChange?: (info: {
    model: VoiceModel;
    pitch?: number;
    formant?: number;
    profileSummary?: string;
  }) => void;
};

function ModelsPageImpl({
  banner = null,
  onVoiceChange,
  onOpenPlaza,
  focusKind,
  focusNonce = 0,
}: ModelsPageProps) {
  const [models, setModels] = useState<VoiceModel[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("default");
  const [kind, setKind] = useState<Kind>("rvc");
  /** 当前生效的 DSP 预设 id；空串 = DSP 没开。 */
  const [dspId, setDspId] = useState("");
  /** 当前生效的那条预设本体，编辑器要拿它画滑条。 */
  const [dspActive, setDspActive] = useState<DspPreset | null>(null);
  /** 加一就让预设列表重拉（存了/删了自定义预设之后）。 */
  const [dspReload, setDspReload] = useState(0);

  // DSP 是热键，开关和换预设都不重开流。用完立刻回读配置，别让界面和引擎
  // 各记各的 —— 那种不一致用户看不出原因，只会觉得「点了没反应」。
  const applyDsp = useCallback(async (p: DspPreset | null) => {
    const next = p ? p.id : "";
    setDspId(next);
    setDspActive(p);
    const noVoice = !selectedKey;
    try {
      await setHot(
        p
          ? {
              dsp_enabled: true,
              dsp_preset: p.id,
              dsp_params: p.params,
              ...(noVoice ? { function: "fx" as const } : {}),
            }
          : { dsp_enabled: false, dsp_preset: "" },
      );
    } catch {
      /* 引擎没开着也没关系：配置已经写下去了，下次开启变声就生效 */
    }
  }, [selectedKey]);

  useEffect(() => {
    if (focusKind === "rvc" || focusKind === "dsp") setKind(focusKind);
  }, [focusKind, focusNonce]);

  // 进页面时把当前预设读回来，不然切走再切回来「使用中」的标记就没了。
  useEffect(() => {
    let alive = true;
    void getConfig()
      .then((c) => {
        if (!alive) return;
        setDspId(c?.dsp_enabled ? String(c?.dsp_preset || "") : "");
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  const [page, setPage] = useState(0);
  const [cols, setCols] = useState(5);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const dropVoice = useCallback(async () => {
    try {
      await clearVoice();
      setSelectedKey("");
      onVoiceChange?.({
        model: { name: "", path: "", dir: "", file: "" },
      });
      setMsg(t("s.dspCleared"));
    } catch (e) {
      setMsg(String(e));
    }
  }, [onVoiceChange]);
  const [indexItems, setIndexItems] = useState<IndexItem[]>([]);
  const [profiles, setProfiles] = useState<ProfileItem[]>([]);
  // 封面本地化：已装第三方音色的远程封面走本地缓存，不再每次全量重拉。
  const coverCache = useCoverCache(
    useMemo(() => models.map((m) => m.cover || "").filter(Boolean), [models]),
  );
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
    if (!models.length) return t("s.b4ac696046");
    if (query.trim() && view.length !== models.length) {
      return t("s.e5323dcb69", { v0: models.length, v1: view.length });
    }
    const cur = selected?.name || models[0]?.name || "—";
    return t("s.425fb93e79", { v0: models.length, v1: cur });
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
    if (!selected?.dir) return;
    let disposed = false;
    let un: (() => void) | undefined;
    void listen<{ hot?: Record<string, unknown> }>("config-changed", (ev) => {
      const hot = ev.payload?.hot;
      if (!hot) return;
      if (hot.pitch == null && hot.formant == null) return;
      void reloadPanels(selected);
    }).then((fn) => {
      if (disposed) fn();
      else un = fn;
    });
    return () => {
      disposed = true;
      un?.();
    };
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

  // 点别处、按 Esc 都关。菜单自己 stopPropagation，所以点菜单里的项不会
  // 先被这条关掉。
  useEffect(() => {
    const close = () => setMenu(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(null);
    };
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  /**
   * 「⋯」按钮打开菜单。位置从按钮量，不是从鼠标量。
   *
   * 菜单右边缘对齐按钮右边缘：卡片在最后一列时，从按钮左边缘往右展开会顶出
   * 窗口。宽度和 MoreMenu 里的 min-w 对上。
   */
  const openMenu = (e: MouseEvent<HTMLButtonElement>, model: VoiceModel) => {
    // 不让这一下冒泡到上面那个「点别处就关」，否则刚开就被关掉。
    e.stopPropagation();
    if (menu && modelKey(menu.model) === modelKey(model)) {
      setMenu(null);
      return;
    }
    const r = e.currentTarget.getBoundingClientRect();
    const w = 168;
    setMenu({
      x: Math.max(8, Math.min(r.right - w, window.innerWidth - w - 8)),
      y: r.bottom + 6,
      model,
    });
  };

  const onUse = async (m: VoiceModel) => {
    if (m.missing) {
      setMsg(t("s.314a72cba4"));
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
    ? t("s.279450164a")
    : selected.missing
      ? t("s.8f61254fa2")
      : promotable
        ? t("s.57da23c608")
        : !manageable
          ? t("s.3620fe63a3")
          : "";

  return (
    <PagePad>
      <PageHead
        title={t("s.0d63fa301f")}
        sub={statusSub}
        actions={
          <>
            {/* 社区音色搬到广场了（那边是整页，放得下封面网格；这里的
                对话框最宽 720px，只塞得下一列文字行）。入口留着 —— 用户
                找音色的第一反应是来模型页，不该让他自己猜要去广场。 */}
            <Btn primary onClick={() => onOpenPlaza?.()}>{t("s.b2be174f0f")}</Btn>
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
                  if (String(e) !== t("s.a5ffdc95ee")) setMsg(String(e));
                } finally {
                  setBusy(false);
                }
              }}
            >{t("s.54b3625b92")}</Btn>
            <Btn
              onClick={async () => {
                await reload();
                setMsg(t("s.58b4af2771"));
              }}
            >{t("s.38108eaa1d")}</Btn>
            <Btn
              onClick={() => {
                void openModelsDir().catch((e) => setMsg(String(e)));
              }}
            >{t("s.031c105578")}</Btn>
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
            placeholder={t("s.fc3bad4cea")}
            className="inline-flex min-w-[230px] px-[13px] py-[7px] rounded-[var(--rs)] text-[13px] text-[var(--ink)] bg-transparent shadow-[inset_0_0_0_1px_var(--line)] outline-none focus:shadow-[inset_0_0_0_1px_var(--accent)]"
          />
          {/* RVC 音色 / DSP 预设二选一。故意不给「全部」—— 两种东西混在
              一个列表里，小白分不清自己点的是音色还是效果。 */}
          <SegmentControl<Kind>
            value={kind}
            onChange={(v) => {
              setKind(v);
              setPage(0);
            }}
            options={[
              { id: "rvc", label: t("s.dspKindRvc") },
              { id: "dsp", label: t("s.dspKindDsp") },
            ]}
          />
          {kind === "rvc" ? (
            <span className="ml-auto">
              <SegmentControl<SortKey>
                value={sort}
                onChange={setSort}
                options={[
                  { id: "default", label: t("s.c8d09cf955") },
                  { id: "name", label: t("s.1be7ae4fc2") },
                  { id: "index", label: t("s.225f6a39ca") },
                ]}
              />
            </span>
          ) : null}
        </div>

        {kind === "dsp" ? (
          <div ref={gridRef}>
            {selectedKey ? (
              <div className="mb-4 flex items-center gap-3 flex-wrap">
                <p className="m-0 text-[12.5px] text-[var(--ink-muted)] leading-snug flex-1 min-w-[220px]">
                  {t("s.dspOverlayHint")}
                </p>
                <Btn onClick={() => void dropVoice()}>{t("s.dspClearVoice")}</Btn>
              </div>
            ) : (
              <p className="m-0 mb-4 text-[12.5px] text-[var(--ink-muted)] leading-snug">
                {t("s.dspOnlyHint")}
              </p>
            )}
            <DspPresetGrid
              cols={cols}
              query={query}
              activeId={dspId}
              busy={busy}
              reloadToken={dspReload}
              onActive={setDspActive}
              onUse={(p) => void applyDsp(p)}
              onStop={() => void applyDsp(null)}
            />
            {dspActive ? (
              <DspPresetEditor
                preset={dspActive}
                onApply={(params) =>
                  void setHot({
                    dsp_enabled: true,
                    dsp_preset: dspActive.id,
                    dsp_params: params,
                  }).catch(() => {})
                }
                onSaved={() => setDspReload((n) => n + 1)}
              />
            ) : null}
          </div>
        ) : (
        <div
          ref={gridRef}
          className="grid gap-x-4 gap-y-[22px]"
          style={{
            gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
          }}
        >
          {!models.length ? (
            <div className="col-span-full text-[13.5px] text-[var(--ink-muted)] py-10 px-2">{t("s.c9efc20514")}</div>
          ) : !view.length ? (
            <div className="col-span-full text-[13.5px] text-[var(--ink-muted)] py-10 px-2">
              {t("s.041c85897b", { v0: query })}
            </div>
          ) : (
            pageView.map((v) => {
              const cur = modelKey(v) === selectedKey;
              const src = resolveCover(v.cover, coverCache);
              return (
                <div key={modelKey(v)}>
                  <div className="aspect-[4/3] rounded-[var(--r)] grid place-items-center relative overflow-hidden bg-[color-mix(in_srgb,var(--ink)_7%,transparent)] text-[color-mix(in_srgb,var(--ink)_32%,transparent)] text-2xl">
                    {src ? (
                      <img
                        src={src}
                        alt=""
                        // contain：官方 1:1 与框内一致不裁；第三方竖立绘用 cover 会
                        // 只剩胸口或腿。与首页 HomePage 一致。
                        className="absolute inset-0 w-full h-full object-contain"
                        draggable={false}
                      />
                    ) : (
                      <span>{(v.name || "?").slice(0, 4)}</span>
                    )}
                    {cur ? (
                      <span className="absolute top-2.5 right-2.5 text-[11px] text-[var(--accent)] font-semibold drop-shadow">{t("s.e6aa2cbd7b")}</span>
                    ) : null}
                    {v.has_index || v.index ? (
                      <span className="absolute right-2.5 bottom-2 text-[11px] text-[var(--meta)]">{t("s.ec673c54d6")}</span>
                    ) : null}
                    {v.missing ? (
                      <span className="absolute left-2.5 top-2.5 text-[11px] text-[#c44]">{t("s.2fe9b75856")}</span>
                    ) : null}
                  </div>
                  <div className="text-[11.5px] text-[var(--meta)] mt-2.5">
                    {v.tag || t("s.c4301894a2")}
                  </div>
                  <div className="text-[14.5px] font-semibold mt-0.5 truncate">
                    {v.name}
                  </div>
                  <div className="text-xs text-[var(--meta)] mt-0.5 truncate">
                    {v.author ? t("s.7feea73fa3", { v0: v.author }) : t("s.2af26573b0")}
                  </div>
                  <div className="mt-2.5 flex items-center gap-1.5">
                    {cur ? (
                      <Btn on uw disabled>{t("s.e6aa2cbd7b")}</Btn>
                    ) : (
                      <Btn uw disabled={busy || !!v.missing} onClick={() => void onUse(v)}>{t("s.0e2d3a3c09")}</Btn>
                    )}
                    {/* 改名 / 删除 / 看作者主页原来藏在右键里，没人找得到。
                        一条都没有的模型不画这个按钮 —— 点开只写着「无可用
                        操作」的菜单，比没有按钮更让人恼火。 */}
                    {hasMoreActions(v) ? (
                      <Btn
                        className="px-2.5"
                        ariaLabel={t("models.more")}
                        onClick={(e) => openMenu(e, v)}
                      >
                        ⋯
                      </Btn>
                    ) : null}
                  </div>
                </div>
              );
            })
          )}
        </div>

        )}

        {kind === "rvc" && view.length > pageSize ? (
          <div className="flex items-center justify-center gap-3 mt-[26px] text-[12.5px] text-[var(--meta)]">
            <Btn
              disabled={pageClamped <= 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >{t("s.b41561d807")}</Btn>
            <span>
              {t("s.40a021ed44", {
                v0: pageClamped + 1,
                v1: totalPages,
                v2: view.length,
              })}
            </span>
            <Btn
              disabled={pageClamped >= totalPages - 1}
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            >{t("s.67a246a344")}</Btn>
          </div>
        ) : null}
      </Block>

      <Block
        title={t("s.713782084c")}
        titleTip={tip(t("s.225f6a39ca"))}
        note={manageable ? t("s.22b8661995") : undefined}
        action={
          manageable ? (
            <Btn
              onClick={async () => {
                try {
                  const r = await bindIndex(selected!.dir);
                  setIndexItems(r.items || []);
                  await reload();
                } catch (e) {
                  if (String(e) !== t("s.a5ffdc95ee")) setMsg(String(e));
                }
              }}
            >{t("s.8f84a93f91")}</Btn>
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
                      setMsg(t("s.1784a97067"));
                    } catch (e) {
                      setMsg(String(e));
                    }
                  }}
                >{t("s.4e504ca0d3")}</Btn>
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
                      <Btn on uw disabled>{t("s.e6aa2cbd7b")}</Btn>
                    ) : (
                      <Btn
                        uw
                        onClick={async () => {
                          const r = await applyIndex(selected!.dir, it.path);
                          setIndexItems(r.items || []);
                          await reload();
                        }}
                      >{t("s.0e2d3a3c09")}</Btn>
                    )}
                    {it.path && !it.active ? (
                      <Btn
                        onClick={async () => {
                          const r = await unbindIndex(selected!.dir, it.path);
                          setIndexItems(r.items || []);
                          await reload();
                        }}
                      >{t("s.80d59b5959")}</Btn>
                    ) : null}
                  </>
                }
              />
            ))}
          </Group>
        )}
      </Block>

      <Block
        title={t("s.5ec6f626c3")}
        note={t("s.0096454995")}
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
                        <Btn on uw disabled>{t("s.e6aa2cbd7b")}</Btn>
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
                        >{t("s.0e2d3a3c09")}</Btn>
                      )}
                      {p.id ? (
                        <Btn
                          onClick={async () => {
                            if (
                              !(await askConfirm(
                                t("s.b8863a5222", { v0: p.name }),
                              ))
                            )
                              return;
                            await deleteProfile(selected!.dir, p.id);
                            const pr = await listProfiles(selected!.dir);
                            setProfiles(pr.items || []);
                          }}
                        >{t("s.3755f56f2f")}</Btn>
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
                        const name = await askPrompt(t("s.6b863e8f98"), t("s.b0bef96a4b"));
                        if (name == null) return;
                        await saveProfile(selected!.dir, name);
                        const pr = await listProfiles(selected!.dir);
                        setProfiles(pr.items || []);
                      }}
                    >{t("s.e5e9953e15")}</Btn>
                    <Btn
                      onClick={async () => {
                        try {
                          await importProfile(selected!.dir);
                          const pr = await listProfiles(selected!.dir);
                          setProfiles(pr.items || []);
                        } catch (e) {
                          if (String(e) !== t("s.a5ffdc95ee")) setMsg(String(e));
                        }
                      }}
                    >{t("s.93ccffa7cc")}</Btn>
                    <Btn
                      onClick={async () => {
                        try {
                          await exportProfile(selected!.dir);
                          setMsg(t("s.fc70c44b85"));
                        } catch (e) {
                          if (String(e) !== t("s.a5ffdc95ee")) setMsg(String(e));
                        }
                      }}
                    >{t("s.7213716bfe")}</Btn>
                  </>
                }
              />
            </Group>
          </>
        )}
      </Block>

      {menu ? (
        <MoreMenu
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

    </PagePad>
  );
}

/**
 * 这个模型有没有「⋯」里能做的事。
 *
 * 条件要和 `MoreMenu` 里往 items 塞东西的判断逐条对上：这边多判一个，用户
 * 会点开一个空菜单；这边少判一个，某些模型的改名 / 删除就再也没有入口了。
 */
function hasMoreActions(m: VoiceModel): boolean {
  if (m.source === "user_data" && m.dir) return true;
  if (m.author_url) return true;
  if (m.source === "legacy_weights" && m.path) return true;
  return false;
}

/**
 * 模型卡片上「⋯」按钮弹的菜单：改名、删除、看作者主页、把老权重收进音色库。
 *
 * 这些以前是右键菜单。右键在桌面软件里是个没人会去试的入口——用户不知道有，
 * 就等于没做。现在它挂在「使用」旁边一个看得见的按钮上。
 */
function MoreMenu({
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
      label: t("s.1cd80fd7a8"),
      action: async () => {
        const n = await askPrompt(t("s.b8659855b0"), model.name);
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
      label: t("s.3755f56f2f"),
      danger: true,
      action: async () => {
        if (
          !(await askConfirm(
            t("s.29abc60b6f"),
          ))
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
      label: t("s.468c96d425"),
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
      label: t("s.4e504ca0d3"),
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
