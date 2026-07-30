import { useEffect, useState } from "react";
import { Dock, type OutputMode } from "./components/Dock";
import { PageHost } from "./components/PageHost";
import { TitleBar } from "./components/TitleBar";
import type { PageId } from "./lib/nav";
import { HelpPage } from "./pages/HelpPage";
import { HomePage } from "./pages/HomePage";
import { ModelsPage } from "./pages/ModelsPage";
import { MorePage } from "./pages/MorePage";
import { PlazaPage } from "./pages/PlazaPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  const [page, setPage] = useState<PageId>("home");
  const [compactNav, setCompactNav] = useState(false);
  const [pitch, setPitch] = useState(15);
  const [formant, setFormant] = useState(1.2);
  const [mode, setMode] = useState<OutputMode>("vc");
  const [running, setRunning] = useState(false);
  const [voiceId, setVoiceId] = useState("anon");

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 520px)");
    const fn = () => setCompactNav(mq.matches);
    fn();
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);

  const profileSummary =
    pitch === 0 && formant === 0
      ? "默认（原始参数）"
      : `开黑日常 · 音高 ${pitch >= 0 ? "+" : ""}${pitch} 共鸣 ${formant.toFixed(2)}`;

  return (
    <div className="h-full flex flex-col bg-[var(--bg)] text-[var(--ink)] overflow-hidden">
      <TitleBar
        page={page}
        onPage={setPage}
        plazaUnread
        compactNav={compactNav}
      />

      <PageHost page={page}>
        {(id) => {
          switch (id) {
            case "home":
              return (
                <HomePage
                  currentId={voiceId}
                  onOpenModels={() => setPage("models")}
                  onSelect={setVoiceId}
                />
              );
            case "plaza":
              return <PlazaPage />;
            case "models":
              return <ModelsPage />;
            case "settings":
              return <SettingsPage />;
            case "help":
              return <HelpPage />;
            case "more":
              return <MorePage />;
          }
        }}
      </PageHost>

      <Dock
        voiceName={voiceId === "anon" ? "Anon" : voiceId === "soyo" ? "Soyo" : "Rana"}
        pitch={pitch}
        formant={formant}
        onPitch={setPitch}
        onFormant={setFormant}
        mode={mode}
        onMode={setMode}
        running={running}
        onToggleRun={() => setRunning((r) => !r)}
        profileSummary={profileSummary}
        statusTitle={running ? "变声中" : "引擎待命"}
        statusSub={running ? "（演示 · 未接 worker）" : "就绪"}
      />
    </div>
  );
}
