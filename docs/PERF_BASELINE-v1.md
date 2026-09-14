# 性能与音频测量基线 v1

日期：2026-09-14。依据：整改计划书 A-04 / B3 验收口径。本文只定义计时边界、设备矩阵与采样方法；代码级测量与真机验收分开，不互相替代。

## 计时边界

自动化可测（`scripts/dev/measure_start_baseline.py`，不开流）：

| 字段 | 边界 | 说明 |
|------|------|------|
| `spawn_ms` | spawn → status.json 首个 `pid>0` | 进程起来、协议可见 |
| `ready_ms` | spawn → `state=idle` | 含 torch/驱动导入与设备枚举，等价「引擎就绪」 |
| `cmd_ack_ms` | 写 `list_devices` → `status.last_cmd_seq` 认领 | 命令链路延迟（派发等待含在内） |
| `prewarm_ms` | `--prewarm` 时发 prewarm → 日志「预热：完成」 | 模型读权重；需已选音色；用 python.exe 捕获输出，含控制台分配开销 |

手动验收（专用时段、有人值守，不自动开流）：

| 边界 | 记录项 |
|------|--------|
| 首次开流 | 点「开启变声」→ status `state=running`；TeamSpeak 闭麦/丢设备与否；播放器进度是否停 |
| 停流/再开流 | 同上对照；端点事件 |
| 切换音色 | 点击 → 卡片 pending（即时）→「使用中」；重复点击只提交一次 |
| 独占模式 | 用户勾选 WASAPI 独占时单独验，标注可能排挤共享流 |

## 设备矩阵

对照组：相同后台负载、不运行 RVC Fabric。

| 层级 | 覆盖项 |
|------|--------|
| 必测 | 本机复现设备（报告用户的组合）、板载声卡 + VB-CABLE、TeamSpeak 通话 + 本地音乐/视频播放 |
| 应测 | USB 声卡/耳机、MME / WASAPI 共享两后端、蓝牙设备 |
| 选测 | ASIO / 用户勾选独占、多声卡并发 |
| 标注 | 未覆盖的驱动组合在报告里明确列出，不外推 |

## 采样方法

```bat
python scripts\dev\measure_start_baseline.py            :: 启动+命令链路一次
python scripts\dev\measure_start_baseline.py -n 3       :: 连测三次看波动
python scripts\dev\measure_start_baseline.py --prewarm  :: 加测预热
```

- 前置条件：软件不在运行（有活 worker 时脚本拒绝执行）；`Runtime/` 已补全。
- 记录自动追加到 `_local/perf_baseline.jsonl`（不入 Git），每条带时间戳与 worker pid。
- 报告里写清采样条件：机器、后端（cuda/dml/cpu）、第几次冷启动、后台负载。
- 本机首测（2026-09-14，cuda 变体）：`spawn≈0.1s`、`ready≈7.0s`、`cmd_ack≈51ms`；单次值只作参照点，不作验收数字。
