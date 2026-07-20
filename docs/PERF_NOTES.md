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
- 待补:RTX 3050(Ampere,验证 fp16+TF32 路径)。

### 精确分段(--sync-stages,2026-07-20,同机 · torch 2.0.0+cu118)

| 模型 | fea(HuBERT) | index | f0(fcpe) | model(net_g) | 合计 |
|------|------------|-------|----------|--------------|------|
| kikiV1(40k v1) | 24.2ms(41%) | 0 | 4.3ms(7%) | **29.8ms(51%)** | 58.4 |
| Miku(48k v2) | 29.6ms(46%) | 0 | 3.8ms(6%) | **30.7ms(48%)** | 64.3 |

**真相:合成器(net_g)最贵,HuBERT 第二,fcpe 便宜到可以忽略**——早前异步失真的日志里
"f0 很贵"是假象。据此:

- **f0/HuBERT 双流并行:取消**(f0 只有 4ms,无肉可割)。
- **GPU index 检索:实测确认**(Miku.index 44226 行上 GPU,每块 ~1ms,端到端 64.3→65.2ms 基本无感;
  旧 CPU faiss 路径此处会是数毫秒+强制同步)。
- **150ms 块可行**(kiki p95 62.2 / Miku p95 63.8,预算 120ms;但 kiki 出现过 209ms 离群块,
  3GB 显存机器建议默认仍 250ms,低延迟作为预设选项)——现有性能预设
  (low_latency 0.12/1.5s、balanced 0.22/2.5s、stable 0.40/3.5s)与数据吻合,无需改。
- **下一刀优先级**:① CUDA Graphs 包住 net_g(占 ~50%,fp32 小核多,launch 开销占比高,
  Windows 可用,torch 2.0 有 API);② HuBERT 上下文(fea 随 extra_time 近似线性,
  低延迟预设已把 2.5s→1.5s,更激进需试听);③ 无第三刀——f0/index 已榨干。

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
| ✖ | f0/HuBERT 双流并行 | **数据否决**:fcpe 实测仅 ~4ms/块,无并行价值 |
| ⏳ | CUDA Graphs(net_g) | **当前第一优先**:net_g 占 ~50%;Windows 可用,torch 2.0 有 API;需静态缓冲改造 |
| ⏳ | HuBERT 上下文裁剪 | 已由性能预设承载(低延迟档 extra 1.5s);更激进需试听验收 |
| ⏳ | ONNX 后端 | 主要为 DML(A/I 卡)补 fp32 短板;N 卡优先级低 |
| ✅ | 「其他」页快捷按钮 | 打开性能信息文件夹 + 生成诊断包(launcher 解锁后补上) |

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
