# launcher/main_app.py 分解说明与路线图

> `main_app.py` 曾是 ~4460 行的巨类,承载全部页面构建、实时控制、快捷键、设置。
> 单文件过大 → 合并冲突频繁、难测、难维护。本文件记录**已完成的分解**、**安全模式**
> 与**后续路线**,供本人与协作者继续拆分时照做。

## 已完成（本轮）

### 1. 纯逻辑抽成独立可测模块（不依赖 Tk）

| 模块 | 内容 | 测试 |
|------|------|------|
| `launcher/app_presets.py` | 性能预设映射 `PERF_PRESETS`、`perf_preset_values/name`、延迟行格式化 `format_latency_line` | `tests/test_launcher_extracted.py` |
| `launcher/voice_history.py` | `VoiceParamHistory`（撤销/重做快照栈，去重/上限/分叉） | 同上 |
| `launcher/audio_devices.py` | `is_virtual_monitor_name`、`prefer_monitor_device`（监听设备选择启发式） | 同上 |

`main_app.py` 相应方法改为**薄委托**（如 `_format_latency_line` 一行调用），行为不变。

### 2. 页面构建器抽成 mixin（`launcher/pages/`）

| mixin | 文件 | 方法 |
|-------|------|------|
| `HomePageMixin` | `launcher/pages/home_page.py` | `_page_home`、轮播 `_render_carousel`、`_update_home_current_label`、`_show_switch_toast`、`_schedule_carousel_reflow` |
| `ModelsPageMixin` | `launcher/pages/models_page.py` | `_page_models`、`refresh_models`、`_apply_models_filter`、`_use_model_from_grid`、`import_model`、`_schedule_models_reflow` |

`class MainApp(HomePageMixin, ModelsPageMixin)` 组合；mixin 共享同一 `self`，跨页面的
`self.*` 属性/方法在组合实例上运行期解析。**main_app.py 4461 → 4018 行。**

## 安全模式（务必照做）

1. **一次移一个内聚页面**：把 `_page_X` 及其**仅服务该页**的辅助方法整体搬到
   `launcher/pages/x_page.py` 的 `class XPageMixin:`，补齐该文件的模块级 import。
2. **共享方法留在主类**：被多处（如快捷键）调用的（`_shift_model`、`_select_model`…）不要移。
3. **验证导入解析**（本仓库容器 Python 3.11 无 tkinter，但 **3.12 有**）：
   ```bash
   python3.12 -c "import launcher.main_app as m; assert hasattr(m.MainApp,'_page_x'); print('OK')"
   ```
   这一步能抓到「漏 import → 运行期 NameError」——py_compile 抓不到。
4. **跑测试**：`python3 -m pytest tests -q`（纯逻辑模块有覆盖）。
5. **清死导入**：方法移走后，主文件里只出现 1 次（即 import 行本身）的符号删掉。
6. 改完 launcher **需重打 exe** 才能实机看到（本机分解不改运行行为）。

## 后续路线（未做，按上表模式机械推进）

| 优先 | 抽取项 | 说明 / 风险 |
|------|--------|-------------|
| 中 | `MorePageMixin`（`_page_more` + `_open_perf_reports`/`_collect_diagnostics`/`_force_kill_engine`/`open_bootstrap`） | 内聚、近文件尾，低风险 |
| 中 | `SettingsPageMixin`（`_page_settings` ~800 行 + index/设备/加速/预设处理） | **最大块**；但协作者近期在此改动（FX/快捷键/引导），先协调再动，避免冲突 |
| 中 | `HotkeysMixin`（`_build_hotkeys_settings_section` + 捕获/全局/应用） | 同上，协作者活跃区 |
| 低 | `RealtimeControlMixin`（`toggle_vc`/`_start_vc`/`_stop_vc`/`_tick_status`/状态徽章） | 与实时协议耦合，仔细搬 |
| 低 | `MonitorMixin`（监听设备 UI：`_refresh_monitor_hint`/`_on_monitor_*`/`_toggle_monitor`） | 纯启发式已抽到 `audio_devices.py`，UI 部分可再分 |

目标终态：`main_app.py` 只保留 `__init__`、窗口/chrome 骨架、`show_page`、页面组合与
跨页面共享方法；每个页面一个 mixin 文件；纯逻辑在无 Tk 的可测模块里。
