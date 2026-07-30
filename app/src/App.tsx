import { useEffect, useState } from "react";
import { Dock, type OutputMode } from "./components/Dock";
import { PageHost } from "./components/PageHost";
import { ProvisionGate } from "./components/ProvisionGate";
import { TitleBar } from "./components/TitleBar";
import { useEngine } from "./hooks/useEngine";
import { ensureEngine, forceKillEngine, getProvisionStatus } from "./lib/engine";
import type { PageId } from "./lib/nav";
import { currentVoice } from "./lib/voices";
import { HelpPage } from "./pages/HelpPage";
import { HomePage } from "./pages/HomePage";
import { ModelsPage } from "./pages/ModelsPage";
import { MorePage } from "./pages/MorePage";
import { PlazaPage } from "./pages/PlazaPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  const [page, setPage] = useState<PageId>("home");
  const [compactNav, setCompactNav] = useState(false);
  const [pitch, setPitch] = useState(0);
  const [formant, setFormant] = useState(0);
  const [mode, setMode] = useState<OutputMode>("vc");
  const [voiceName, setVoiceName] = useState("未选择模型");
  const [voiceId, setVoiceId] = useState("");
  const [profileSummary, setProfileSummary] = useState("默认（原始参数）");
  const [showProvision, setShowProvision] = useState(false);
  const [provisionDismissed, setProvisionDismissed] = useState(false);

  const engine = useEngine();

  useEffect(() => {
    if (engine.provision.need_provision && !provisionDismissed) {
      setShowProvision(true);
    }
  }, [engine.provision.need_provision, provisionDismissed]);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 520px)");
    const fn = () => setCompactNav(mq.matches);
    fn();
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);

  useEffect(() => {
    void currentVoice()
      .then((c) => {
        if (c.model) {
          setVoiceName(String(c.model.name || "未选择模型"));
          setVoiceId(String(c.model.path || c.model.dir || c.model.name || ""));
        }
        if (c.pitch != null) setPitch(Number(c.pitch));
        if (c.formant != null) setFormant(Number(c.formant));
        if (c.profile_summary) setProfileSummary(c.profile_summary);
      })
      .catch(() => {
        /* browser preview */
      });
  }, []);

  const handlePitch = (v: number) => {
    setPitch(v);
    engine.onPitch(v);
  };
  const handleFormant = (v: number) => {
    setFormant(v);
    engine.onFormant(v);
  };
  const handleMode = (m: OutputMode) => {
    setMode(m);
    engine.onMode(m);
  };

  return (
    <div className="h-full flex flex-col bg-[var(--bg)] text-[var(--ink)] overflow-hidden relative">
      <TitleBar
        page={page}
        onPage={setPage}
        plazaUnread
        compactNav={compactNav}
      />

      <ProvisionGate
        open={showProvision}
        initial={engine.provision}
        onDone={async () => {
          setShowProvision(false);
          setProvisionDismissed(false);
          try {
            await getProvisionStatus();
            await ensureEngine();
          } catch {
            /* refresh via hook poll */
          }
          await engine.refresh();
        }}
        onDismiss={() => {
          setShowProvision(false);
          setProvisionDismissed(true);
        }}
      />

      <PageHost page={page}>
        {(id) => {
          switch (id) {
            case "home":
              return (
                <HomePage
                  currentId={voiceId}
                  onOpenModels={() => setPage("models")}
                  onSelect={(id) => setVoiceId(id)}
                />
              );
            case "plaza":
              return <PlazaPage />;
            case "models":
              return (
                <ModelsPage
                  onVoiceChange={({ model, pitch: p, formant: f, profileSummary: ps }) => {
                    setVoiceName(model.name || "未选择模型");
                    setVoiceId(model.path || model.dir || model.name || "");
                    if (p != null) setPitch(Number(p));
                    if (f != null) setFormant(Number(f));
                    if (ps) setProfileSummary(ps);
                  }}
                />
              );
            case "settings":
              return (
                <SettingsPage
                  status={engine.status}
                  onReloadDevices={() => void engine.refresh()}
                />
              );
            case "help":
              return <HelpPage />;
            case "more":
              return (
                <MorePage
                  status={engine.status}
                  provision={engine.provision}
                  onForceKill={async () => {
                    await forceKillEngine();
                    await engine.refresh();
                  }}
                  onOpenProvision={() => {
                    setProvisionDismissed(false);
                    setShowProvision(true);
                  }}
                />
              );
          }
        }}
      </PageHost>

      <Dock
        voiceName={voiceName}
        pitch={pitch}
        formant={formant}
        onPitch={handlePitch}
        onFormant={handleFormant}
        mode={mode}
        onMode={handleMode}
        running={engine.running || engine.starting}
        onToggleRun={() => void engine.toggleRun()}
        profileSummary={profileSummary}
        statusTitle={engine.title}
        statusSub={engine.sub}
        meterLevel={engine.meterLevel}
        threshold={engine.threshold}
      />
    </div>
  );
}
