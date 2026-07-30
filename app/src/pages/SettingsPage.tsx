import { useState, type ReactNode } from "react";
import { SegmentControl } from "../components/SegmentControl";
import { Block, Btn, HelpMark, PagePad } from "../components/ui";

const TABS = [
  "设备与音频",
  "变声参数",
  "性能设置",
  "声音效果",
  "外观",
  "常规",
  "快捷键",
  "在线更新",
] as const;

type Tab = (typeof TABS)[number];

/** Settings page shell (fields wire to config/store later). */
export function SettingsPage() {
  const [tab, setTab] = useState<Tab>("设备与音频");

  return (
    <div>
      <div className="px-[30px] pt-4 max-[1020px]:px-[22px] max-[720px]:px-4 overflow-x-auto">
        <SegmentControl
          options={TABS.map((t) => ({ id: t, label: t }))}
          value={tab}
          onChange={setTab}
          className="!inline-flex !ml-0 max-w-full"
        />
      </div>

      <PagePad>
        {tab === "设备与音频" ? <DeviceAudio /> : null}
        {tab === "变声参数" ? <VoiceParams /> : null}
        {tab !== "设备与音频" && tab !== "变声参数" ? (
          <Block title={tab}>
            <p className="text-[12.5px] text-[var(--help)] m-0 leading-relaxed max-w-[76ch]">
              本标签页字段与现有设置页一致，将按项接入配置与帮助文案。
            </p>
          </Block>
        ) : null}
      </PagePad>
    </div>
  );
}

function DeviceAudio() {
  return (
    <Block title="设备与音频" className="!mt-6">
      <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[76ch]">
        输入＝真实麦克风 · 输出＝CABLE Input · 游戏麦克风＝CABLE Output。
        <br />
        勾选「变声时监听自己」并选耳机，可以一边开黑一边听自己的变声效果。
      </p>
      <div className="bg-[var(--group)] rounded-[var(--r)] px-5 py-[22px] flex flex-col gap-6">
        <Field
          label="加速后端"
          tip="加速后端说明"
          inline
          control={<FakeSelect value="cuda" width={170} />}
          note="加速：NVIDIA CUDA · 探测未确认（偏好 cuda → cuda）· 未检出 CUDA，确认使用了对应显卡发行包 Runtime\n发行包：NVIDIA CUDA"
        />
        <Field label="设备类型" tip="设备类型说明" control={<FakeSelect value="MME" full />} />
        <Field
          label="输入设备"
          tip="输入设备说明"
          control={<FakeSelect value="麦克风 (Realtek(R) Audio)" full />}
        />
        <Field
          label="麦克风增益 dB"
          tip="麦克风增益说明"
          control={<FakeSlider value={6} display="6.00" pct={64} />}
        />
        <Field
          label="输出设备"
          tip="输出设备说明"
          control={<FakeSelect value="CABLE Input (VB-Audio Virtual Cable)" full />}
        />
        <label className="flex items-center gap-[11px] cursor-pointer">
          <HelpMark title="监听自己说明" />
          <span className="w-[15px] h-[15px] rounded shadow-[inset_0_0_0_1px_var(--line)]" />
          <span className="text-sm">变声时监听自己</span>
        </label>
        <Field
          label="监听设备"
          desc="关闭时只走「输出设备」（通常 CABLE）；开启后在耳机里听变声"
          control={<FakeSelect value="扬声器 (Realtek(R) Audio)" full />}
        />
        <div className="flex items-center gap-[11px] flex-wrap">
          <span className="w-[15px] h-[15px] rounded shadow-[inset_0_0_0_1px_var(--line)]" />
          <span className="text-sm">WASAPI 独占（一般不要勾）</span>
          <span className="ml-auto flex items-center gap-2.5 flex-wrap">
            <span className="text-[12.5px] text-[var(--meta)]">采样率</span>
            <FakeSelect value="sr_device" width={140} />
            <Btn>重载设备列表</Btn>
          </span>
        </div>
        <div className="flex">
          <Btn className="!ml-auto">实体声卡连接说明</Btn>
        </div>
      </div>
    </Block>
  );
}

function VoiceParams() {
  return (
    <Block title="变声参数" note="运行中可热更新 · 按音色保存" className="!mt-6">
      <p className="text-[12.5px] text-[var(--help)] leading-relaxed m-0 mb-4 max-w-[80ch]">
        音高 / 共鸣 / 阈值 / Index / 响度 / 算法会写入当前音色目录的 config.json；切换音色时自动恢复该音色上次的参数。底栏可快速调节。
      </p>
      <div className="bg-[var(--group)] rounded-[var(--r)] px-5 py-[22px] flex flex-col gap-6">
        <Field label="响应阈值" tip="响应阈值" control={<FakeSlider value={-45} display="−45" pct={28} />} />
        <Field label="音高 Pitch" tip="音高" control={<FakeSlider value={15} display="15" pct={81} />} />
        <Field label="共鸣 Formant" tip="共鸣" control={<FakeSlider value={1.2} display="1.20" pct={80} />} />
        <Field label="Index 检索强度" tip="Index" control={<FakeSlider value={0.75} display="0.75" pct={75} />} />
        <Field label="响度包络" tip="响度" control={<FakeSlider value={0.3} display="0.30" pct={30} />} />
        <Field
          label="音高算法"
          tip="算法"
          inline
          control={<FakeSelect value="rmvpe" width={150} />}
        />
      </div>
    </Block>
  );
}

function Field({
  label,
  tip,
  desc,
  note,
  control,
  inline = false,
}: {
  label: string;
  tip?: string;
  desc?: string;
  note?: string;
  control: ReactNode;
  inline?: boolean;
}) {
  if (inline) {
    return (
      <div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-sm">
            {label} {tip ? <HelpMark title={tip} /> : null}
          </div>
          <div className="ml-auto">{control}</div>
        </div>
        {note ? (
          <div className="text-xs text-[var(--help)] mt-2 leading-relaxed whitespace-pre-line">
            {note}
          </div>
        ) : null}
      </div>
    );
  }
  return (
    <div>
      <div className="flex items-center gap-2 mb-2 text-sm">
        {label} {tip ? <HelpMark title={tip} /> : null}
      </div>
      {desc ? (
        <div className="text-[12.5px] text-[var(--help)] -mt-1 mb-2 leading-relaxed">{desc}</div>
      ) : null}
      {control}
      {note ? (
        <div className="text-xs text-[var(--help)] mt-2 leading-relaxed whitespace-pre-line">
          {note}
        </div>
      ) : null}
    </div>
  );
}

function FakeSelect({
  value,
  full = false,
  width,
}: {
  value: string;
  full?: boolean;
  width?: number;
}) {
  return (
    <span
      className={[
        "inline-flex justify-between gap-3 items-center px-[13px] py-[7px] rounded-[var(--rs)] text-[13px]",
        "shadow-[inset_0_0_0_1px_var(--line)]",
        full ? "w-full" : "",
      ].join(" ")}
      style={width ? { minWidth: width } : undefined}
    >
      {value}
      <span className="text-[var(--meta)] text-[9px]">▼</span>
    </span>
  );
}

function FakeSlider({
  display,
  pct,
}: {
  value: number;
  display: string;
  pct: number;
}) {
  return (
    <div className="flex items-center gap-[15px] w-full">
      <div className="relative flex-1 h-[3px] rounded-sm bg-[color-mix(in_srgb,var(--ink)_11%,transparent)]">
        <div
          className="absolute inset-y-0 left-0 bg-[var(--accent)] rounded-sm"
          style={{ width: `${pct}%` }}
        />
        <div
          className="absolute top-1/2 w-3 h-3 -mt-1.5 -ml-1.5 rounded-full bg-[var(--surface)] shadow-[0_1px_4px_rgba(0,0,0,.24),inset_0_0_0_1px_var(--line)]"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="text-[13px] min-w-[56px] text-right">{display}</div>
    </div>
  );
}
