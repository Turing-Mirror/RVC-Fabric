<div align="center">

<img src="assets/brand/logo_wordmark.png" alt="RVC Fabric" width="300">

# RVC Fabric

**把你的声音换成别人的**

基于 [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) 深度定制 · 由 [图灵镜 Turing Mirror](https://github.com/Turing-Mirror) 开发维护

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

**仓库**　[GitHub 源码](https://github.com/Turing-Mirror/RVC-Fabric)　·　[CNB 发布与制品](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**社媒**　[哔哩哔哩 @图灵镜](https://space.bilibili.com/3546871148579062)　·　[抖音 @图灵镜](https://v.douyin.com/6NxXcrKK9cc)（抖音号 `TuringMirror`）　·　[小红书 @图灵镜](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094)（小红书号 `TuringMirror`）

**赞助推广**　[首月五折　·　性价比云服务器 / 游戏云 / 面板服　·　雨云](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## 这是干嘛的

开黑的时候,队友听到的是你本来的声音。RVC Fabric 让你换掉它:选一个音色,点「开启变声」,你说话,对面听到的是那个音色——实时,不用等文件处理完。

它有音色库、社区商店、配置档案,音高和共鸣可以边说边调。游戏、QQ、Discord、直播间,声音从哪出就从哪变。

它不是网页工具。原版 RVC 是给研究者和调参佬的:自己装 Python、装 PyTorch、下预训练模型、开浏览器点 Gradio 页面。RVC Fabric 把这些全塞进一个 Windows 安装程序,装完点图标就进主界面。

## 怎么开始

1. 下载 [`RVC_Fabric_Setup.exe`](https://github.com/Turing-Mirror/RVC-Fabric/releases)(只有一个通用包,不用分辨显卡型号,装到英文路径更稳妥)
2. 打开程序,按引导走:自动识别显卡 → 推荐并下载对应运行时(Python + PyTorch,数 GB)→ 下载引擎核心 → 装虚拟声卡 VB-Cable
3. 接线,然后点「开启变声」

### 接线

变声软件改不了游戏的麦克风。游戏只会读你选定的麦克风,所以中间要虚拟声卡转一手:

| 位置 | 选什么 |
|---|---|
| 软件输入 | 你真实的麦克风 |
| 软件输出 | **CABLE Input** |
| 监听(可选) | 你的耳机,只有你自己听得到 |
| 游戏 / QQ 麦克风 | **CABLE Output** |
| Windows 默认播放 | 耳机,**不要**选 CABLE |

想靠软件内置声卡「监听自己」来听效果也行,但游戏里听到你变声,必须有 VB-Cable 这一环。装不上也不挡主界面,之后在「说明」页能补装。

## 功能

**实时变声** — 选音色 → 选设备 → 开启变声。音高、共鸣边说边调,立即生效,不用停下重启。「原声旁路」模式不变声只透传,用来测麦克风有没有接对。电平表带响应阈值刻度,一眼看出软件有没有听到你。

**音色管理** — 本地音色网格浏览、搜索、排序。每个音色可以绑定检索库(`.index`),不绑也能用。参数按音色单独保存,切回来还是上次那套。

**配置档案** — 同一个音色存多套参数(音高 / 音效 / 性能),点「使用」即切换。档案能导出分享,也能导入别人调好的。

**社区音色** — 双源商店:图灵镜自有音色 + 第三方公开源(如 Hugging Face 直链)。并发下载、断点续传、系列专区、按上传时间分页。第三方内容与官方无关,装之前自己判断。

**显卡支持** — NVIDIA(CUDA)、AMD / Intel(DirectML)。启动器自动识别你的显卡,下载对应的运行时,不用手动装驱动依赖。

**其他** — 全局快捷键(可自定义)、托盘常驻、自定义背景图、诊断包一键生成(含性能测试)、在线更新。

## 边界

- **改不了游戏的麦克风。** 游戏里要听到变声,必须接虚拟声卡(见上)。
- **音色决定效果。** 转换质量取决于你选的音色模型。社区音色鱼龙混杂,装第三方的东西,后果自负。
- **训练不在这里。** 训练自己的音色走随包保留的 RVC WebUI(高级功能),RVC Fabric 主界面不做训练。

## 与上游的关系

fork 自 [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI),深度魔改,不是套壳。

**没动的部分:** 网络结构与底模。`infer/lib/infer_pack/`(VITS 网络、attention、F0 预测器)与上游一致,没有重新训练。检索式转换、hubert 特征提取、RMVPE 音高提取都来自上游。

**大改的部分** — 实时推理链路:

| 文件 | 改了啥 |
|---|---|
| `gui_v1.py` | 无窗 worker 模式、文件协议驱动、真实延迟指标、参数热更 |
| `infer/lib/rtrvc.py` | GPU 上做检索、常量控制张量复用、推理期关梯度、引擎预热 |
| `infer/lib/rmvpe.py` | 解码向量化、f0 后处理去分支 |

**新增的部分(上游没有):** 麦克风输入增益、变声后 DSP 效果链(噪声门、压缩器、五段 EQ)、「监听自己」、无窗后台 worker + 单实例 + 孤儿进程清理、Python 3.9 兼容。

其余上游代码(训练与推理 WebUI、UVR5、ONNX 导出、IPEX 支持)基本原样,作为高级功能保留。

## 更新与版本号

版本号只有 `1.2.3` 三位数这一种。修了 bug 就升一个小版本号,不搞 `-hotfix` 之类的后缀,同一个版本号也绝不发两次——你看到版本号变了,东西就是真的变了。

更新分两种:界面和设置这类小改动,软件里在线更新,不用重装;需要换新安装包的大版本,软件会提示你去下载。

## 参与开发

**环境:** Windows + PowerShell;Node 20+ / Rust stable(壳);CPython 3.13(打包与脚本;运行时推理用下载的 3.9 Runtime);文件一律 UTF-8。

**启动**

```bat
cd app
npm install
npm run tauri:dev              :: 桌面壳开发(需 WebView2 + MSVC)
npm run dev                    :: 仅浏览器预览 UI
scripts\dev\go-web.bat         :: 上游训练 / 推理 WebUI
scripts\dev\go-realtime-gui.bat :: 上游实时面板(需本机 Runtime)
```

**测试:** `scripts\run_tests.bat`。测试有 `unittest.TestCase` 和 pytest 函数式两种风格,`unittest discover` 收集不到后者,两个都要跑;缺 numpy / torch 的用例自动跳过。

**打包:** `python scripts\build_setup.py --clean`(通用薄安装包)、`python scripts\build_release.py --variant nvidia|amd|nvidia50`(全量离线包)、`python scripts\build_catalog.py build --diff`(在线清单)。

**架构:** 外壳是 Tauri + Rust + React(单一 `RVC Fabric.exe`),推理在下载来的 Python 3.9 运行时里跑,两者通过 `User_Data/runtime_control/` 下的 JSON 文件通信:

```
RVC Fabric.exe(Tauri + Rust + React)
   │  JSON 文件协议(command.json / status.json / worker.pid)
   ▼
Runtime\pythonw.exe tools/realtime_worker.py(Python 3.9 + CUDA / DirectML)
   → runpy gui_v1.py → rtrvc + AudioIoProcess
```

两个进程是刻意拆的:Rust 里塞不进 torch;需要 torch 或 sounddevice 的事(音频设备枚举、加速能力探测)都留给 worker,Rust 去问它。

**目录归属:** 上游为主 `infer/` `configs/` `tools/` `gui_v1.py` `infer-web.py`;本项目自有 `app/`(Tauri 壳)`scripts/`(打包与运营)`installer/`(Inno 脚本,待 NSIS 验证后撤)`tests/`。制品暂存 `CNB-GIT-RELEASE/`(gitignore)→ 对应 CNB 仓 [RVC-Fabric-Releases](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)。

**仓库不含什么:** 运行时、模型权重、ffmpeg 二进制、`dist/`、`build/`、用户数据都不进 Git,发布制品在 CNB。

## 许可

MIT([LICENSE](./LICENSE)),与上游一致。模型权重、音色包、第三方内容各自遵循原始许可与条款;社区音色由各自作者提供,与图灵镜官方无关。

**请勿将本软件用于伪造身份、诈骗、骚扰或任何未经授权的用途。** 使用他人声音训练或转换前,须先取得本人明确授权;因违规使用产生的一切后果,由使用者自行承担。

## 致谢

**项目基础:** [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 本项目由此 fork 而来

**模型与架构:** [ContentVec](https://github.com/auspicious3000/contentvec/)(内容特征提取)· [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan)(合成器与解码器)· [RMVPE](https://github.com/Dream-High/RMVPE)(音高提取,权重由 [yxlllc](https://github.com/yxlllc/RMVPE) 与 [RVC-Boss](https://github.com/RVC-Boss) 训练与测试)

**实时链路:** [faiss](https://github.com/facebookresearch/faiss)(top1 检索)· [TorchGate](https://github.com/timsainb/noisereduce)(实时降噪,vendored 在 `tools/torchgate/`)

**可选音高算法:** [pyworld](https://github.com/JeremyCCHsu/Python-Wrapper-for-World-Vocoder)(harvest)· [praat-parselmouth](https://github.com/YannickJadoul/Parselmouth)(pm)· [torchcrepe](https://github.com/maxrmorrison/torchcrepe)· [FCPE](https://github.com/CNChTu/FCPE)

**随包的高级功能:** [Gradio](https://github.com/gradio-app/gradio)(训练/推理 WebUI)· [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui)(人声伴奏分离)· [audio-slicer](https://github.com/openvpi/audio-slicer)(训练数据切片)

**外部组件:** [FFmpeg](https://github.com/FFmpeg/FFmpeg)(转码)· [VB-Audio Virtual Cable](https://vb-audio.com/Cable/)(虚拟声卡,游戏里听到变声靠它)

感谢上游及以上所有项目的作者与贡献者。
