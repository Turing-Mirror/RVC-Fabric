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

## 4. 用户数据收集(现状与下一步)

- **机制(已实现,默认关)**:引擎在开流时读 `User_Data/app_config.json` 的
  **`perf_report_enabled`**(布尔,默认 `false` = 不收集);开启后每次停止变声写本地报告
  (显卡/torch/块长/f0 法/延迟分布/超预算块数),保留最近 30 份,**不上传**。
  开发/基准可用环境变量 `TM_PERF_REPORT=1/0` 强制覆盖。
- **待做(launcher 侧,为避免并行开发冲突暂缓)**:设置页加开关
  「**收集您的变声器性能信息以帮助我们优化和适配**」,说明文案注明"仅记录在本机
  `User_Data/perf_reports`,不会自动上传";开关写入 `app_config.json` 的
  `perf_report_enabled` 键(config_store 一行即可)。
- **更远(待定)**:在线更新通道加可选「上传性能报告」(再次明确征得同意,默认关)。
- 客服话术:"发一下 `User_Data\perf_reports` 里最新的 json"。
- 基准脚本同理可 `--json-out 文件名` 直接产出可发送的结果文件。
