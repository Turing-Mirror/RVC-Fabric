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
    "音频接口类型。MME 兼容性最好；WASAPI 延迟更低但对设备更挑。\n换了这项需要重新「开启变声」。",
  sg_input_device:
    "你实际说话用的麦克风。\n不要选 CABLE Output —— 那是虚拟声卡的出口，会把变声后的声音再吃回来，造成回环。",
  in_gain_db:
    "麦克风输入增益，在响应阈值和电平表之前生效。\n麦太小声就调高；已经很响还调高会削波失真。",
  sg_output_device:
    "变声后的声音送到哪里。\n想让游戏 / QQ 里的人听到，这里必须选 CABLE Input，然后在游戏里把麦克风选成 CABLE Output。",
  monitor_self:
    "开启后：游戏 / 语音仍走「输出设备」（一般是 CABLE Input），\n同时在「监听设备」再放一份变声后的声音给你听。\n监听请选真实耳机 / 音箱，不要选 CABLE、Steam Streaming、虚拟声卡。\n运行中可开关；若仍无声：停一次变声再开，并确认系统默认播放设备。",
  monitor_device:
    "监听用的真实设备。选你的耳机；选到虚拟声卡会听不到或造成回环。",
  sg_wasapi_exclusive:
    "WASAPI 独占模式：延迟更低，但会占住整块声卡，其他程序可能出不了声。\n一般不要勾。",
  sr_type:
    "采样率来源。sr_device 跟随设备，sr_model 跟随模型。\n不确定就保持 sr_device。",
  threhold:
    "响应阈值（噪声门）。比这个还轻的声音被判定为安静，不做变声。\n用来滤掉键盘声和风扇声。说话时底栏电平条应明显越过这条竖线。",
  pitch: "音高。男声变女声通常 +12 左右，女声变男声 −12 左右。运行中可实时调。",
  formant: "共鸣（共振峰）。微调音色的粗细，配合音高一起找像的位置。",
  index_rate:
    "检索强度。越高越贴近训练音色，但吐字可能变糊；越低越保留你自己的发音。\n没有绑定检索库时这一项无效。",
  rms_mix_rate: "响度包络。控制输出音量跟随原声的程度，越低越接近训练音色的响度。",
  f0method:
    "音高提取算法。rmvpe 效果最好也最快，一般不用改。\nharvest 更稳但慢，pm 最快但容易破音。",
  block_time:
    "采样块时长。越小延迟越低，但对 CPU / GPU 要求越高，太小会断断续续。\n改后需重新「开启变声」。",
  crossfade_length:
    "交叉淡化时长。块与块之间的衔接，太小会有咔哒声，太大会糊。",
  extra_time:
    "额外推理时长。给算法更多上下文，音质更稳但延迟增加。",
  n_cpu: "用于 harvest 等 CPU 算法的线程数。用 rmvpe 时基本无影响。",
  I_noise_reduce: "输入降噪。更干净，代价是多几毫秒延迟。",
  O_noise_reduce: "输出降噪。对变声后的声音再降一次噪，一般不需要。",
  use_pv: "相位声码器。某些音色上衔接更自然，可以开着试听对比。",
  theme_mode: "界面配色。跟随系统，或固定浅色 / 深色。",
  wallpaper_path: "自定义背景图。静态图，最大 20 MB，最长边 4096。",
  wallpaper_blur: "背景图的磨砂（高斯模糊）强度。",
  wallpaper_opacity: "背景图的不透明度，越低越淡。",
  close_action:
    "点标题栏 X 或 Alt+F4 时的行为：\n· 每次询问：弹出「到托盘 / 直接关闭」\n· 最小化到托盘：不再询问，直接藏到右下角（变声继续）\n· 直接退出：不再询问，停止变声并退出",
  hotkeys_enabled: "全局快捷键。开启后在任何程序里都能切换变声开关和模式。",
  telemetry_opt_in:
    "匿名用户统计。只发送一个随机编号、软件版本、显卡加速方式，\n不发送账号、音色、录音或任何能定位到你的信息。",
};
