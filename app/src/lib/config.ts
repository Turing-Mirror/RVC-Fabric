import { invoke } from "@tauri-apps/api/core";

export type Config = Record<string, unknown>;

export type ConfigWrite = {
  config: Config;
  hot: Record<string, unknown>;
  /** Cold keys in this patch — the stream must be restarted for them. */
  needs_restart: string[];
};

export async function getConfig(): Promise<Config> {
  return await invoke<Config>("config_get");
}

export async function setConfig(patch: Config): Promise<ConfigWrite> {
  return await invoke<ConfigWrite>("config_set", { patch });
}

/** Detailed help behind every ? in the settings page. Text carries over from
 *  the Python shell's SETTING_TIPS unchanged — users rely on it. */
export const TIPS: Record<string, string> = {
  sg_hostapi:
    "音频接口类型：\n• MME：兼容性最好，几乎不挑设备；\n• WASAPI：延迟更低，但对设备更挑。\n修改后需重新「开启变声」生效。",
  sg_input_device:
    "你实际说话用的麦克风。\n不要选 CABLE Output。",
  in_gain_db:
    "调节麦克风输入音量：说话声太小就调高；已经够大还调高会削波破音。",
  sg_output_device:
    "变声后的声音送到这里。\n让游戏/语音里的人听到：输出选 CABLE Input，再把游戏里的麦克风设为 CABLE Output。",
  monitor_self:
    "开启后，变声声音除送往「输出设备」外，还会在「监听设备」再放一份给你听。\n监听设备选真实耳机或音箱，不要选 CABLE 等虚拟声卡。\n若开启后听不到声音，重新开启一次变声，并检查系统默认播放设备。",
  monitor_device:
    "选你实际使用的耳机或音箱。\n选到虚拟声卡会听不到声音，还可能回环啸叫。",
  sg_wasapi_exclusive:
    "开启后延迟更低，但会独占声卡，其他程序可能无声。\n一般保持关闭。",
  sr_type:
    "决定用哪个采样率工作：\n• 跟随设备：使用声卡采样率（推荐）；\n• 跟随模型：使用音色模型自带的采样率。\n不确定就保持「跟随设备」。",
  threhold:
    "输入噪声门：低于此响度的环境杂音（键盘、风扇声）会被过滤，不触发变声。\n正常说话时，底栏电平条应明显越过竖线。",
  pitch:
    "音高（Pitch）：男声变女声通常 +12，女声变男声通常 −12。\n变声中可实时拖动试听。",
  formant:
    "共鸣/共振峰（Formant）：微调声音的粗细感，配合音高一起调，让声音更贴近目标角色。",
  index_rate:
    "越高越贴近目标音色，但吐字可能变糊；越低越保留你自己的发音。\n未绑定 .index 检索库时此项无效。",
  rms_mix_rate: "控制输出音量跟随原声的程度，越低越接近训练音色本身的响度。",
  f0method:
    "音高提取算法（F0）：\n• RMVPE：效果最好也最快，一般不用改；\n• Harvest：更稳但较慢；\n• PM：最快但容易破音；\n• FCPE / Crepe：可选的高精度算法。",
  block_time:
    "切片块时长（Block Size）：每次处理的音频切片长度。数值越小延迟越低，但越吃 GPU/CPU，过小会导致声音断断续续。\n修改后需重新「开启变声」生效。",
  crossfade_length:
    "相邻音频块的过渡时长：过小接缝处会咔哒响，过大会发糊。保持默认即可。",
  extra_time:
    "给算法更多上下文：数值越大音质与音高越稳，但延迟随之增加。",
  n_cpu: "用于 Harvest 等 CPU 算法的线程数；用 RMVPE 等 GPU 算法时基本无影响。",
  cuda_graph:
    "预录制 GPU 推理指令，减少 CPU 与 GPU 的交互开销，可降低延迟、减少显存占用。\n仅 NVIDIA 显卡有效；环境不兼容时自动退回传统模式。",
  I_noise_reduce: "变声前先对麦克风声音降噪：输出更干净，但延迟略增。",
  O_noise_reduce: "对变声后的声音再降一次噪。通常开输入降噪就够，仅在底噪明显时开启。",
  use_pv: "改变音频块的拼接方式，部分音色衔接更自然。开着试听对比即可。",
  fx_enabled:
    "变声后依次经过噪声门、压缩器、均衡器。\n关闭则直接输出模型原生声音，下方所有设置失效。运行中可实时开关。",
  fx_eq_enabled: "5 段参数均衡器（EQ）：微调变声后的各频段响度。不确定怎么调，先套用下方预设。",
  fx_eq_preset:
    "预置的调音曲线：选一个直接套用，也能选完再拖下面的推子微调。\n手动拖动后会显示「自定义」。",
  fx_gate_enabled: "说话间隙自动压低底噪，比响应阈值更柔和。",
  fx_gate_threshold_db:
    "低于此电平的声音会被压低。\n环境吵就往上调（接近 −20）；调太高会把气音也切掉。",
  fx_comp_enabled: "把忽大忽小的音量压平，听感更稳。",
  fx_comp_threshold_db: "超过此响度才开始压缩，越低压得越多。",
  fx_comp_ratio:
    "压缩强度，4:1 是常用值。比例越大越「平」，过大会发闷、失去起伏。",
  fx_out_gain_db: "压缩或均衡处理后整体音量偏小的话，在这里补回来。",
  theme_mode: "跟随系统，或固定浅色 / 深色。",
  wallpaper_path:
    "本地 PNG/JPG 静态图片。没有大小限制，但图片越大加载越慢，建议别超过 4K 分辨率。",
  wallpaper_blur: "背景图的模糊（高斯模糊）强度。",
  wallpaper_opacity: "背景图的显示透明度，越低越淡。",
  close_action:
    "点击标题栏 X 或 Alt+F4 时：\n• 每次询问：弹窗选择「最小化到托盘 / 直接关闭」；\n• 最小化到托盘：隐藏到托盘，变声继续；\n• 直接退出：停止变声并退出。",
  hotkeys_enabled: "开启后，即使软件在后台或最小化，也能用快捷键控制变声。",
  telemetry_opt_in:
    "匿名用户数量统计（用于寻求赞助、维持免费开发）：\n只发送随机设备编号、软件版本与显卡加速类型，不收集账号、音色、录音或任何个人信息。\n可在「设置 → 常规」随时关闭。",
};
