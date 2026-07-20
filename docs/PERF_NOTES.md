# 实时推理性能纪要（持续更新）

> 记录基准数据、平台结论与优化台账。基准工具:`tools/benchmark_realtime.py`;
> 用户侧数据来源:`User_Data/perf_reports/`（本地 JSON,停止变声时自动生成,用户手动分享,不上传）。

## 1. 基准数据

### GTX 1060 3GB · fp32 · kikiV1(40k v1) · fcpe · block 250ms · 无 index（2026-07-20）

| 版本 | mean | p50 | p95 | max | RTF | 首块 |
|------|------|-----|-----|-----|-----|------|
| tm-release 基线 | 68.2ms | 67.2 | 76.4 | 91.5 | 0.27 | ~20.8s |
| 优化分支(张量缓存+cudnn autotune 等) | **55.6ms** | 54.4 | **61.9** | 76.5 | **0.22** | ~4.0s |

- 端到端 **-18.5%**;此时 GPU index 检索路径尚未参与(index_rate=0)。
- 待补:`--sync-stages` 精确分段、带 `--index`、`--block-time 0.15`、RTX 3050(Ampere,验证 fp16+TF32 路径)。

## 2. 平台结论(重要,别再踩)

| 结论 | 说明 |
|------|------|
| 分段耗时默认不可信 | CUDA 异步排队,`Spent time` 只测到提交时刻;要真实占比必须 `--sync-stages` |
| Pascal(10 系)强制 fp32 是对的 | Pascal fp16 吞吐是 1/64 残废;16 系是 NaN 问题 |
| TF32 只对 Ampere+(30 系起)有效 | 对 10 系无效但无害;30/40/50 系 fp32 路径受益 |
| **torch.compile 在 Windows 不可用** | inductor 依赖 Triton,无 Windows 版;已从路线图移除,替代方案是手动 CUDA Graphs |
| 首块巨贵(4–20s) | fcpe 懒加载 + cudnn 调优 + CUDA 上下文;已用 start_vc 预热解决(见台账) |

## 3. 优化台账(全部只动推理侧,旧 .pth/.index 完全兼容)

| 状态 | 项 | 内容 |
|------|----|------|
| ✅ | 常量控制张量缓存 | padding mask / p_len / sid 等每块复用,不再重分配上传 |
| ✅ | cudnn.benchmark + TF32 | 实时进程形状固定,autotune 收益免费 |
| ✅ | GPU index 检索 | fp16 特征库常驻显存,精确 top-8 替代每块 CPU faiss(≤150 万行;失败自动回退) |
| ✅ | RMVPE 解码矢量化 | 去掉逐帧 Python 循环,批量管线同样受益 |
| ✅ | 引擎预热 | start_vc 音频流打开前跑 2 次哑推理,首块卡顿移出可听区 |
| ✅ | f0 后处理去分支 | torch.where 替代掩码赋值,消每块一次主机同步 |
| ✅ | 本地性能报告 | 停止变声时写 `User_Data/perf_reports/perf_*.json`,收集用户显卡数据用 |
| ⏳ | f0/HuBERT 双流并行 | 两者相互独立,理论可重叠;等 `--sync-stages` 数据确认 f0 真实占比再做 |
| ⏳ | CUDA Graphs(net_g) | Windows 可用的内核开销消除手段;等分段数据确认 model 占比 |
| ⏳ | HuBERT 上下文裁剪预设 | extra_time=2.5s 意味着每块 >10 倍重复编码;影响音质,须做成可选预设+试听验收 |
| ⏳ | ONNX 后端 | 主要为 DML(A/I 卡)补 fp32 短板;N 卡优先级低 |

## 4. 用户数据收集(定案:偶尔采样 + 用户自取)

- **机制(已实现,默认开、偶尔采样)**:软件会偶尔把变声性能信息保存在**本机**
  `User_Data/perf_reports/`(显卡/torch/块长/f0 法/延迟分布/超预算块数)。
  采样节流:每 30 分钟至多一份(`should_save`),忽略少于 40 块的瞬时会话;保留最近 30 份;
  **绝不自动上传**——由用户自己找到文件并选择是否发给团队。
  `TM_PERF_REPORT=0` 完全关闭,`=1` 强制每次保存(开发/基准用)。
- **待做(launcher 侧,为避免并行开发冲突暂缓)**:「其他」页加快捷按钮
  「**打开性能信息文件夹**」(`os.startfile(perf_reports 路径)` 一行),旁注说明
  "软件偶尔会在本机记录性能信息以帮助我们优化和适配,不会自动上传;
  如愿协助,可将文件夹内文件发送给团队"。
- **诊断包**:`Runtime\python.exe tools\collect_diagnostics.py` 一键打包
  日志 + 性能报告 + 配置 + 环境摘要到 `User_Data/diagnostics/diag_*.zip`
  (纯标准库,ML 栈坏了也能跑);「其他」页同样可加一个按钮调它(暂缓,同上)。
- 基准脚本可 `--json-out 文件名` 直接产出可发送的结果文件。
