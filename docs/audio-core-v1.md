# 独立音频核心 v1

## 当前范围

这是音频功能的第一批基础实现，不是已接入应用的完整播放器。代码在 app/audio-core，独立编译，不依赖 Tauri、Python、Torch 或 RVC 运行时。现有变声输出链未修改；没有新增页面、快捷键或悬浮窗控制，没有构建、发布安装包。

已实现：

- 本地 FFmpeg/ffprobe 共用路径发现、音频时长探测。
- 后台流式解码、采样率和声道转换、按帧选区。
- 有界无锁 PCM 队列，取消时终止并回收本次解码进程。
- 原生 WASAPI 设备枚举、按稳定设备 ID 打开输出，不回落到系统默认设备。
- 回调内的多路 PCM 混合、独立音量、暂停、停止、进度、欠载计数和声道联动峰值控制。固定输入拓扑仅用于本批原型，不是音效数量上限。
- 安装资源规则保留产品根目录的 ffmpeg.exe/ffprobe.exe；音频与原 RVC 共用，不在 Runtime 或 User_Data 中增加副本。

## 开发验证

在仓库根目录运行：

```powershell
cargo test --manifest-path app/audio-core/Cargo.toml
$env:FABRIC_AUDIO_TOOLS = (Get-Location).Path
cargo test --manifest-path app/audio-core/Cargo.toml --test decoder -- --include-ignored
cargo clippy --manifest-path app/audio-core/Cargo.toml --all-targets -- -D warnings
python -m unittest tests.test_audio_tools_payload tests.test_installer_unification
cargo run --manifest-path app/audio-core/Cargo.toml --example audio_probe -- list
```

普通 Rust 测试不打开设备；decoder 集成测试显式提供 FFmpeg 路径，仅在系统临时目录生成合成 WAV，并验证源文件不变。忽略标记代表需要外部工具，不代表已执行。list 只枚举设备，不播放。

人工出声测试必须明确传入设备 ID、文件和选区：

```text
audio_probe play TOOL_ROOT INPUT DEVICE_ID START END
```

此开发入口尚无产品级试听隔离策略，不得自动选择 CABLE 或其他设备作为本地试听。不要在通话中直接运行。

## 本批证据

2026-09-22，Windows，rustc 1.97.1，CPAL 0.18.2，rtrb 0.4.0。

- 8 项核心单元测试通过。
- 3 项真实 FFmpeg 集成测试通过：44.1kHz 单声道转 48kHz 双声道、0.25–0.75 秒选区精确输出 24000 帧、取消满缓冲、损坏文件与越界范围。
- 23 项音频资源和安装器回归通过。
- 原生枚举得到 11 个输出端点，包括 CABLE、实体声卡和其他虚拟设备，读取到 44.1/48kHz 格式。未打开真实输出流。

这不是实际延迟、听感、长时间稳定性或 TeamSpeak 共存验收。

## 后续接入边界

A00 尚未全部验收：真实声卡、设备断开、延迟基线、旧 PortAudio 后端兼容差异及 Python PCM 协议仍待验证。暂不替换现有变声链。

B01–B03 仍需常驻服务、动态播放实例、替换交接、循环/seek、平滑包络、源格式变化和试听隔离。当前范围从文件头解码后裁剪，长文件靠后选区的启动优化未完成；ffprobe 同步探测必须由后台控制线程调用，不能直接放入 UI 或实时回调。峰值控制属于无前瞻的原型，不代表最终听感处理已通过。

后续再接音频库、动态快捷键、首页、音频页、片段编辑与悬浮窗。编号数量和快捷键数量不得由原型输入拓扑决定。

## 安装资源

本批按用户授权采用安装包内置音频组件。构建时使用仓库根现有 FFmpeg/ffprobe，缺任意一个则明确失败；不从用户运行时收集或复制。旧 engine-core 包仍可用于补齐模型资源，落地路径相同，不会安装第二份工具；旧包重复传输和覆盖版本问题须在后续资源更新接入时处理。

当前本机 ffmpeg 是 BtbN n4.3.2 LGPL 构建，ffprobe 是 Gyan 2022-04-07 GPLv3 构建，两者并非同一套。开发验证沿用现有文件，本批不分发二进制。正式打包前应固定成套构建并核对对应来源、许可文本和源码获取说明，不能用现有 LGPL 单条说明代指 GPL ffprobe。也未测量实际安装包压缩体积。

## 官方接口依据

- [CPAL](https://docs.rs/cpal/0.18.2/cpal/)。
- [rtrb](https://docs.rs/rtrb/0.4.0/rtrb/)。
- [FFmpeg](https://ffmpeg.org/ffmpeg.html)。
