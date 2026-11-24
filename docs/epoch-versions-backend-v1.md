# 训练轮次版本后端报告 v1

日期：2026-11-25。仓库：RVC Fabric，分支：`tm-release`。按任务卡执行 RVC 部分，未提交、推送、checkout 或 stash。

## 改动文件

| 文件 | 改动 |
| --- | --- |
| `app/src-tauri/src/model_versions.rs` | 新增轮次来源解析、精确枚举、四种当前状态、SHA-256 缓存、候选与 target 校验、安装及失败回滚；附 13 项测试。 |
| `app/src-tauri/src/lib.rs` | 注册 `model_versions_list`、`model_version_apply`；阻塞文件操作在后台线程执行，应用成功广播 `voices-changed`。 |
| `app/src-tauri/src/train.rs` | 轮次切换接入同一 `START_GATE`；训练占用、实时运行及启动/停止期间拒绝切换；保存中途权重缺省改为 true，并测试显式 false 的序列化保留。 |
| `app/src-tauri/src/worker.rs` | 增加空闲模型缓存失效请求及确认等待。 |
| `app/src-tauri/src/voices.rs` | 收拢已安装音色对应实验的中途权重，保留当前选中的中途模型；增加导出不含 `training` 的断言；复用现有目录校验与配置写入函数。 |
| `tools/train_worker.py` | 发布音色时合并写入训练来源与最终总轮数；保留作者、封面等字段；保存中途权重缺省改为 true。 |
| `gui_v1.py` | 清除旧实时模型和预热引用并确认；预热任务使用代次判定，失效前启动的任务不能把旧权重重新放回缓存。 |
| `app/src/lib/modelVersions.ts` | 新增约定类型与 `listModelVersions`、`applyModelVersion` invoke 封装。 |
| `app/src/lib/modelVersions.test.ts` | 验证命令名、参数、返回对象与错误传递。 |
| `app/src/components/TrainPanel.tsx` | 仅将 `saveWeights` 初始值由 false 改为 true。 |
| `app/i18n/locales/zh-CN.json` | 新增下列 4 个错误键，其他语言文件未改。 |
| `tests/test_train_worker.py` | 更新默认值断言；增加显式 false、训练来源、最终轮数和原有字段保留测试。 |
| `tests/test_model_versions_cache.py` | 从实际 worker 源码提取处理函数，测试缓存失效确认及旧预热线程不能恢复过期权重。 |
| `docs/epoch-versions-backend-v1.md` | 本报告。 |
| `app/src-tauri/engine-payload/` | 使用准备脚本重新生成；本次 Python 改动的副本已同步。该目录已被忽略。 |

没有修改其他页面组件、布局或其他语言文案。现有 RVC 训练循环在最后一轮独立导出正式权重，本次未修改 `infer/modules/train/train.py` 的导出条件。

## 新增命令与实际返回

`model_versions_list({ target })` 返回 `ModelVersions`。
`model_version_apply({ target, kind, file })` 重新枚举并校验候选，RVC 只接受 `kind: "rvc"`，成功后返回更新后的 `ModelVersions`。

以下数据来自 `model_versions::tests::report_sample` 的实际输出，文件为单测夹具。该次调用的 target 为：

```text
C:\Users\Ka251\AppData\Local\Temp\trm-t-epoch-versions-32784-11\User_Data\models\voice
```

列表返回：

```json
{
  "experiment": "voice",
  "weights_dir": "C:\\Users\\Ka251\\AppData\\Local\\Temp\\trm-t-epoch-versions-32784-11\\assets\\weights",
  "weights": [
    {
      "kind": "rvc",
      "current": {
        "state": "matched",
        "file": "voice.pth",
        "epoch": 20,
        "step": null
      },
      "versions": [
        {
          "file": "voice_e2_s40.pth",
          "epoch": 2,
          "step": 40,
          "is_final": false,
          "current": false
        },
        {
          "file": "voice_e10_s200.pth",
          "epoch": 10,
          "step": 200,
          "is_final": false,
          "current": false
        },
        {
          "file": "voice.pth",
          "epoch": 20,
          "step": null,
          "is_final": true,
          "current": true
        }
      ]
    }
  ]
}
```

随后以同一个 target 调用 `model_version_apply({ target, kind: "rvc", file: "voice_e2_s40.pth" })`，返回：

```json
{
  "experiment": "voice",
  "weights_dir": "C:\\Users\\Ka251\\AppData\\Local\\Temp\\trm-t-epoch-versions-32784-11\\assets\\weights",
  "weights": [
    {
      "kind": "rvc",
      "current": {
        "state": "matched",
        "file": "voice_e2_s40.pth",
        "epoch": 2,
        "step": 40
      },
      "versions": [
        {
          "file": "voice_e2_s40.pth",
          "epoch": 2,
          "step": 40,
          "is_final": false,
          "current": true
        },
        {
          "file": "voice_e10_s200.pth",
          "epoch": 10,
          "step": 200,
          "is_final": false,
          "current": false
        },
        {
          "file": "voice.pth",
          "epoch": 20,
          "step": null,
          "is_final": true,
          "current": false
        }
      ]
    }
  ]
}
```

切换保留检索库、预设和其他音色资料，并写入 `training.selected.rvc = {file, epoch, step, sha256}`。安装失败或缓存确认失败时恢复旧权重及原配置。已选中的音色会清除实时 worker 缓存；空闲的离线转换常驻缓存也会释放。

无 `training` 的旧音色按目录名和默认 `assets/weights` 精确回退。枚举不使用前缀或模糊匹配。正式版本总轮数取 `training.final.rvc.epoch`，没有记录时为 null。

## 新增 i18n 键

只增加 `zh-CN.json`，其他语言按任务卡交由后续补充。

| 键 | 简体中文 |
| --- | --- |
| `modelVersions.invalidTarget` | 音色不存在或不在音色库中。 |
| `modelVersions.invalidVersion` | 该轮次模型不存在。 |
| `modelVersions.engineBusy` | 请先停止变声或训练，再切换轮次。 |
| `modelVersions.installFailed` | 切换模型失败。 |

缓存等待失败复用已有 `s.modelApplyUnconfirmed`。

## 测试命令与输出末尾

### Rust

工作目录：`app/src-tauri`。

```powershell
$env:CARGO_TARGET_DIR = "target/export"
cargo test --locked --lib
```

```text
test download::tests::first_byte_timeout_tries_the_next_catalog_url ... ok

test result: ok. 541 passed; 0 failed; 4 ignored; 0 measured; 0 filtered out; finished in 75.28s
```

4 项为仓库已有忽略项：3 项在线资源验收及 1 项要求 Windows 桌面会话的窗口测试。模拟服务用例均通过，本轮没有需按失败单独复跑的服务用例。

轮次模块与 JSON 样例：

```powershell
$env:CARGO_TARGET_DIR = "target/export"
cargo test --locked --lib model_versions::tests -- --nocapture
```

```text
test result: ok. 13 passed; 0 failed; 0 ignored; 0 measured; 532 filtered out; finished in 0.12s
```

覆盖正则特殊字符及同前缀实验、数值排序、旧音色回退、四种当前状态、非候选与越界 target 拒绝、配置记录、空文件拒绝、写配置失败及缓存失败回滚、自定义训练目录、相同内容候选的选中判定、收拢例外、哈希缓存修改时间更新。训练保存开关和导出剔除训练来源由其他 Rust 用例覆盖。

### 前端

工作目录：`app`。

```powershell
npm test
```

```text
Test Files  54 passed (54)
      Tests  304 passed (304)
   Start at  02:42:51
   Duration  5.74s (transform 5.37s, setup 0ms, import 10.31s, tests 9.17s, environment 26.48s)
```

```powershell
npx tsc --noEmit
```

退出码 0，无错误输出。

### Python

工作目录：仓库根目录。

```powershell
python -m unittest tests.test_train_worker tests.test_train_cpu_route tests.test_prewarm tests.test_model_apply tests.test_model_versions_cache
```

```text
----------------------------------------------------------------------
Ran 80 tests in 0.662s

FAILED (failures=1)
```

唯一失败项是 `tests.test_train_worker.TrainPartialWarningUiTests.test_panel_keeps_skip_text_on_msg`，断言当前 `TrainPanel.tsx` 必须包含旧的 `phase === "skip"` 源码字符串。任务开始时保存的原始面板副本也不含该字符串；本次面板只有保存开关默认值的一行变化。未修改这项旧 UI 断言或扩大页面改动。

另将这一个既有 UI 断言排除，执行其余同组后端测试：

```powershell
python TEMP/epoch-versions-v1/run_python_backend.py
```

```text
----------------------------------------------------------------------
Ran 79 tests in 0.525s

OK
```

本地辅助脚本明确排除上述测试类；完整 80 项命令仍按失败记录，不计作全部通过。

### 引擎负载同步

工作目录：仓库根目录。

```powershell
python scripts/prepare_engine_payload.py
```

```text
[exe] skipped
[payload] setup_package.json → installer=tauri_nsis
[payload] app\src-tauri\engine-payload 就绪，6.5 MB
[payload] 检查通过
```

逐字节核对 `tools/`、`infer/` 中 163 份已复制的 Python 文件，全部一致；另核对 `gui_v1.py` 一致。本次两个 Python 改动文件的根目录与负载副本 SHA-256 均相同：

| 文件 | SHA-256 |
| --- | --- |
| `tools/train_worker.py` | `bb8e5f0a89d5f560a781faf84951bf6e0ee70f5a0086c75a530ef19f62e5b210` |
| `gui_v1.py` | `40dd951a580ffcdb260d731e872fac16a60c10c555382f4faa0d9594be09a3dd` |

## 与任务卡不一致及验证边界

Python 完整相关测试保留 1 项上述既有 UI 源码断言失败；其余 79 项通过。未为修复该断言扩大页面修改范围。其他 RVC 功能按卡实现。

本次验证未启动真实 GPU 训练或实时音频流。已验证文件安装、配置回滚、协议处理、预热结果失效和回归测试；长时间训练与实际音频效果未作实机验收。

检查了现有 `.gitignore`：`TEMP/`、`app/src-tauri/target/`、`app/src-tauri/engine-payload/` 已忽略，本次无需新增忽略项。验证日志、原始文件副本和本地辅助脚本位于 `TEMP/epoch-versions-v1/`。未改其他仓库。

