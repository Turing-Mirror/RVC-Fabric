# launcher/main_app.py 分解说明与路线图

> 产品：**RVC Fabric**。  
> `main_app.py` 曾是 ~4460 行的巨类,承载全部页面构建、实时控制、快捷键、设置。
> 单文件过大 → 合并冲突频繁、难测、难维护。本文件记录**已完成的分解**、**安全模式**
> 与**目标终态**,供本人与协作者继续维护时照做。

## 已完成

### 1. 纯逻辑抽成独立可测模块（不依赖 Tk）

| 模块 | 内容 | 测试 |
|------|------|------|
| `launcher/app_presets.py` | 性能预设映射 `PERF_PRESETS`、`perf_preset_values/name`、延迟行格式化 `format_latency_line`、`recommend_perf_preset` | `tests/test_launcher_extracted.py` |
| `launcher/voice_history.py` | `VoiceParamHistory`（撤销/重做快照栈，去重/上限/分叉） | 同上 |
| `launcher/audio_devices.py` | `is_virtual_monitor_name`、`prefer_monitor_device`（监听设备选择启发式） | 同上 |
| `launcher/profiles.py` | 配置档案 `.tmvp` CRUD / schema（无 Tk） | `tests/test_profiles.py` |
| `launcher/hotkeys.py` | 快捷键规格解析 / 全局注册（无 GUI） | `tests/test_hotkeys.py` |

### 2. 页面与能力 mixin（`launcher/pages/`）

| mixin | 文件 | 内容 |
|-------|------|------|
| `HomePageMixin` | `home_page.py` | 首页舞台 + 轮播 |
| `ModelsPageMixin` | `models_page.py` | 模型网格、搜索排序、导入 |
| `MorePageMixin` | `more_page.py` | 其他页、强杀引擎、性能/诊断 |
| `OnboardingMixin` | `onboarding_page.py` | 首启引导 + 社区链接 |
| `HotkeysMixin` | `hotkeys_page.py` | 快捷键绑定、全局热键、设置区 UI、录制/应用 |
| `MonitorMixin` | `monitor_mixin.py` | 监听自己：校验、提示、热切换 |
| `RealtimeControlMixin` | `realtime_control.py` | 启停变声、状态 tick、切音色重启 |
| `DockVoiceMixin` | `dock_voice.py` | 底栏 MODE/参数、按音色持久化、撤销重做 |
| `ProfilesMixin` | `profiles_page.py` | 配置档案面板 + 应用 active profile |
| `ConsultMixin` | `consult_page.py` | 咨询包向导（样本 + 档案打包） |
| `SettingsPageMixin` | `settings_page.py` | 设置页（设备/加速/预设/Index/更新等） |

`class MainApp(...mixins...)` 组合；mixin 共享同一 `self`，跨页面属性/方法运行期解析。

**体量**：`main_app.py` ~4460 → **~930 行**（chrome + 模型选择 + 引擎入口 + lifecycle）。

### 3. 组合冒烟测试

`tests/test_main_app_composition.py`：import `MainApp`，断言 MRO 含各 mixin 且关键方法可调用（**不**实例化窗口）。

### 验证工具（关键）

- 全量产品单测：`scripts\run_tests.bat`（或 host Python 跑 `unittest discover`）
- 门禁子集：composition + launcher pure + hotkeys + profiles + online + gpu + …
- 新 mixin：`python -c "import launcher.main_app as m; assert hasattr(m.MainApp, '…')"`
- 有 pyflakes 时：`python -m pyflakes launcher/pages/x.py`（F821 = 漏 import）

## 安全模式（务必照做）

1. **一次移一个内聚块**：方法体剪切粘贴，不重写行为。
2. **共享方法留在主类**：`_select_model`、`_shift_model`、`show_page`、chrome、`run`/`_on_close`。
3. **公开方法名 / 签名 / `self.*` 键名不变**（设置页与快捷键靠运行期 `self` 解析）。
4. 每步：import + composition 测试 + 产品 unittest 全绿再 commit。
5. 清死导入；更新本文件与 `pages/__init__.py`。
6. 改 launcher **需重打 exe** 才能在发行包里看到（分解本身不改运行行为）。

## 主类仍保留（终态）

| 区域 | 方法簇 |
|------|--------|
| 生命周期 | `__init__`、`run`、`_on_close`、`_place_and_raise` |
| Chrome | `_build_chrome`、`_build_pages`、`show_page`、`_reflow_current_page`、`_set_status_visual` |
| 模型核心 | `_shift_model`、`_select_model`、`_sync_model_to_realtime_gui`、`_refresh_index_ui_for_model`、`_current_model_key`、`_is_active_model` |
| 引擎入口 | `open_webui`、`open_legacy_gui`、`_watch_realtime_gui`、`open_help`、`_show_cable_help` |
| 共享 vars | `_init_shared_voice_vars` |

## 后续（可选，非阻塞）

| 优先 | 项 | 说明 |
|------|----|------|
| 低 | chrome 再拆 `ChromeMixin` | 收益有限；主类已可读 |
| 低 | 错误文案抽纯函数 + 单测 | 仅当要改启停 UX 时顺带做 |
| 低 | 在 Runtime 装 pytest 后跑完整 math/bench 用例 | 无 pytest 时已 soft-skip，不挡 `unittest discover` |

目标终态已基本达成：`main_app.py` 只保留 shell；每页/每能力一个 mixin；纯逻辑在无 Tk 模块 + unittest。
