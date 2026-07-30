<div align="center">

# RVC Fabric

**Windows 桌面实时变声器**

基于 [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) 深度定制 · 由 [图灵镜 Turing Mirror](https://github.com/Turing-Mirror) 开发维护

[![Licence](https://img.shields.io/badge/LICENSE-MIT-green.svg?style=flat-square)](./LICENSE)
[![Based on RVC](https://img.shields.io/badge/based%20on-RVC%20WebUI-1289F0?style=flat-square)](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)

**仓库**　[GitHub 源码](https://github.com/Turing-Mirror/RVC-Fabric)　·　[CNB 发布与制品](https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases)

**社媒**　[哔哩哔哩 @图灵镜](https://space.bilibili.com/3546871148579062)　·　抖音 @图灵镜（抖音号 `TuringMirror`）　·　[小红书 @图灵镜](https://www.xiaohongshu.com/user/profile/65f56bf1000000000b00e094)（小红书号 `TuringMirror`）

**赞助推广**　[首月五折　·　性价比云服务器 / 游戏云 / 面板服　·　雨云](https://www.rainyun.com/m1rror_?s=RVC-Fabric)

</div>

---

## 这是什么

RVC Fabric 是一个装完就能用的 Windows 实时变声软件。选一个音色、选好声卡、点「开启变声」，游戏、QQ、Discord 里的人听到的就是变声后的你。

它**不是**原版 RVC WebUI 的换皮版。原版是给会调参的人用的网页工具链——要自己配 Python 环境、装 PyTorch、下预训练模型、开浏览器点 Gradio 页面。RVC Fabric 把这一整套包成了普通用户能用的桌面程序：

- 一个安装包，装完点图标就开始用，不碰命令行、不配环境
- Python 运行时和模型权重由启动器按你的显卡自动下载补全
- 音色库、社区音色下载、配置档案、快捷键、托盘常驻、虚拟声卡引导都在界面里
- 推理跑在后台无窗进程，主界面卡不卡不影响出声

## 与上游的关系

这是一个**深度魔改**的 fork，不只是套了个壳。

| | 上游 RVC WebUI | RVC Fabric |
|---|---|---|
| 定位 | 训练 / 推理研究工具链 | 面向普通用户的成品软件 |
| 交互 | 浏览器里的 Gradio 页面 | 原生 Windows 桌面程序 |
| 环境 | 自己装 Python + PyTorch | 安装包 + 自动补全运行时 |
| 音色来源 | 自己训练 / 自己找 | 内置音色库 + 社区下载 + 自己导入 |
| 实时变声 | `gui_v1.py`，需手动配置 | 主界面一键，参数随音色保存，后台无窗进程 |

### 沿用上游的部分

**网络结构与底模没有改动，也没有重新训练。** `infer/lib/infer_pack/`（VITS 网络、attention、F0 预测器等）与上游一致。检索式音色转换的核心思路、hubert 特征提取、RMVPE 音高提取模型本身都来自上游。

### 我们改了什么

**实时推理链路做了大量改造**（相对初始 fork）：

| 文件 | 改动 | 内容 |
|---|---|---|
| `gui_v1.py` | +2939 / −314 | 无窗 worker 模式、文件协议驱动、真实延迟指标、参数热更 |
| `infer/lib/rtrvc.py` | +692 / −68 | GPU 上做检索、常量控制张量复用、fp32 强制卡的 dtype 处理、推理期关梯度、引擎预热 |
| `infer/lib/rmvpe.py` | +676 / −15 | 解码向量化、f0 后处理去分支、cudnn autotune |

**新增的引擎侧功能**（上游没有的）：

- 麦克风输入增益 `in_gain_db`，可运行中热更
- 变声后的 DSP 效果链：噪声门、压缩器、五段 EQ
- 「监听自己」——变声后的声音同时送一份到耳机
- 无窗后台 worker 架构，单实例保证与孤儿进程清理
- Python 3.9 兼容性改造（发行运行时是 3.9）

其余上游代码（`infer-web.py` 训练与推理 WebUI、UVR5、ONNX 导出、IPEX 支持）基本保持原样，作为高级功能保留。

### 目录归属

- 上游为主：`infer/`、`configs/`、`tools/`、`gui_v1.py`、`infer-web.py`（其中实时相关部分见上表）
- 本项目自有：`launcher/`（产品外壳）、`scripts/`（打包与运营）、`installer/`、`tests/`

上游仓库：**https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI**
上游多语言文档保留在 `docs/en`、`docs/jp`、`docs/kr`、`docs/fr`、`docs/pt`、`docs/tr`。

## 主要功能

**日常变声**
选音色 → 选设备 → 开启变声。音高、共鸣可以边说边调，立即生效。「原声旁路」模式不变声只透传，用来测麦克风和接线。麦克风电平表带响应阈值刻度，一眼看出软件有没有听到你。

**音色管理**
本地音色网格浏览、搜索、排序。每个音色可以绑定特征索引文件（`.index`，检索库），也可以不绑——没有 index 一样能用。参数按音色单独保存，切回来还是上次那套。

**配置档案**
同一个音色可以存多套参数（音高 / 音效 / 性能），点「使用」即切换。档案可以导出分享，也能导入别人调好的。

**社区音色**
双源音色库：图灵镜自有源 + 第三方公开源（如 Hugging Face 直链）。支持并发下载、断点续传、系列专区、按上传时间分页。第三方内容与官方无关，安装前请自行判断。

**显卡支持**
NVIDIA（CUDA）、AMD / Intel（DirectML）。启动器自动识别你的显卡并下载对应运行时，不用手动装驱动依赖，也不用自己挑安装包。

**其他**
全局快捷键、托盘常驻、自定义背景图、诊断包一键生成（含性能测试）、在线更新。

## 安装与使用

### 安装

从 [Releases](https://github.com/Turing-Mirror/RVC-Fabric/releases) 或图灵镜发布渠道下载 `RVC_Fabric_Setup.exe`。

**只有一个通用安装包**，不用自己分辨显卡型号。安装包是薄包，只含程序本体和引擎源码。首次打开时启动器会引导你：

1. **自动识别你的显卡**，推荐对应的运行时（Python + PyTorch，数 GB，来自 CNB）。推荐项已经选好并说明了理由，你也可以自己改选
2. 下载引擎核心（hubert、rmvpe、ffmpeg）
3. 安装虚拟声卡 VB-Cable（想让游戏里的人听到变声，这一步必需）

装到英文路径下更稳妥。

### 接线

变声软件改不了游戏的麦克风，中间要靠虚拟声卡转一手：

| 位置 | 选什么 |
|---|---|
| 软件输入 | 你真实的麦克风 |
| 软件输出 | **CABLE Input** |
| 监听（可选） | 你的耳机，只有你自己听得到 |
| 游戏 / QQ 麦克风 | **CABLE Output** |
| Windows 默认播放 | 耳机，**不要**选 CABLE |

软件内「说明」页有完整版本，包含实体声卡 / 调音台的接法。

### 版本号

稳定版本号只有 `X.Y.Z` 一种形态。任何修补都按 `+0.0.1` 发新的小版本，不存在 `-hotfix` 之类的后缀，同一个版本号不会二次投递。

## 参与开发

### 环境

- Windows，PowerShell
- 完整 CPython 3.13（打包机必需，要带 tkinter）
- 所有文件 UTF-8

### 启动

```bat
OpenApp.vbs      :: 主界面（launcher/main_app.py）
OpenSetup.vbs    :: 启动器（launcher/bootstrap.py）
scripts\dev\go-web.bat             :: 上游训练 / 推理 WebUI
scripts\dev\go-realtime-gui.bat    :: 上游实时面板
```

不要直接 `python launcher/main_app.py`，除非在调试。

### 测试

```bat
scripts\run_tests.bat
```

测试同时存在 `unittest.TestCase` 和 pytest 函数式两种风格，`unittest discover` 收集不到后者，两个都要跑。需要 numpy / torch 的用例在缺依赖时自动跳过。

### 打包

```bat
python scripts\build_setup.py --clean                          :: 通用薄安装包
python scripts\build_release.py --variant nvidia|amd|nvidia50  :: 全量离线包（按显卡分版）
python scripts\build_catalog.py build --diff                   :: 在线清单
```

安装包只有一个通用版本；分显卡的只有全量离线包和 CNB 上的运行时。

### 架构

主程序是 PyInstaller 冻结的 Python 3.13 外壳，**里面没有 torch 和 numpy**；推理跑在下载来的 Python 3.9 运行时里，两者通过 `User_Data/runtime_control/` 下的 JSON 文件通信。

```
变声器.exe（外壳，Tk 界面）
   │  JSON 文件协议
   ▼
Runtime\pythonw.exe tools/realtime_worker.py（Python 3.9 + CUDA / DirectML）
   → gui_v1.py → rtrvc + AudioIoProcess
```

因此外壳里 import 的任何模块都必须在没有 numpy / torch 的情况下能干净导入。

> 界面层正在迁移到 Tauri + React。迁移期间以 `git log` 和源码为准。

### 仓库不含什么

运行时、模型权重、ffmpeg 二进制、`dist/`、`build/`、用户数据都不进 Git。发布制品在 CNB（`Turing-Mirror/RVC-Fabric-Releases`）。

## 许可

本项目在 [MIT 许可证](./LICENSE)下发布，与上游 RVC WebUI 一致。

模型权重、音色包、第三方内容各自遵循其原始许可与使用条款。社区音色由各自作者提供，与图灵镜官方无关。

**请勿将本软件用于伪造他人身份、诈骗、骚扰或任何未获对方同意的用途。** 使用他人声音训练或转换前请取得授权。

## 致谢

**项目基础**

- [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — 本项目由此 fork 而来

**模型与架构**

- [ContentVec](https://github.com/auspicious3000/contentvec/) — 内容特征提取（`hubert_base.pt`，经 [fairseq](https://github.com/facebookresearch/fairseq) 加载）
- [VITS](https://github.com/jaywalnut310/vits) · [HiFi-GAN](https://github.com/jik876/hifi-gan) — 合成器与解码器架构来源（沿用上游实现与致谢）
- [RMVPE](https://github.com/Dream-High/RMVPE) — 默认音高提取；预训练权重由 [yxlllc](https://github.com/yxlllc/RMVPE) 与 [RVC-Boss](https://github.com/RVC-Boss) 训练与测试

**实时链路**

- [faiss](https://github.com/facebookresearch/faiss) — top1 特征检索，「检索式」这三个字就靠它
- [TorchGate](https://github.com/timsainb/noisereduce) — 实时降噪（谱门控的 PyTorch 实现，作者 Asaf Zorea，vendored 在 `tools/torchgate/`）
- [FreeSimpleGUI](https://github.com/spyoungtech/FreeSimpleGUI) — 上游实时面板的界面框架

**可选音高算法**

- [pyworld](https://github.com/JeremyCCHsu/Python-Wrapper-for-World-Vocoder)（harvest）· [praat-parselmouth](https://github.com/YannickJadoul/Parselmouth)（pm）· [torchcrepe](https://github.com/maxrmorrison/torchcrepe) · [FCPE](https://github.com/CNChTu/FCPE)

**随包的高级功能**

- [Gradio](https://github.com/gradio-app/gradio) — 训练 / 推理 WebUI 界面
- [Ultimate Vocal Remover](https://github.com/Anjok07/ultimatevocalremovergui) — UVR5 人声伴奏分离
- [audio-slicer](https://github.com/openvpi/audio-slicer) — 训练数据切片预处理

**外部组件**

- [FFmpeg](https://github.com/FFmpeg/FFmpeg) — 音频转码
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) — 虚拟声卡，游戏里听到变声靠它

感谢上游及以上所有项目的作者与贡献者。

---

<div align="center">
<sub>Turing Mirror · Veritas, Claritas, Amor</sub>
</div>
