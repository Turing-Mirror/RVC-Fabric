# RVC Fabric 用户可见错误清单 v1

审查日期：2026-11-25。仓库：`F:\Dev\Turing-Mirror\RVC-Fabric`；分支：`tm-release`；HEAD：`bcd7a23d0f9e242e2fa35a036c0d194c1ef67f6d`。

本报告依据当前工作区源码做静态链路盘点，未启动训练、推理、设备测试、安装器或更新。主清单 **666 行**（52 个功能分组）；原始透传索引 186 行；通用兜底索引 177 行；分类器 30 行；日志 19 行；边界说明 13 行。附表是主表的索引与补充，不重复计入主清单数量。

## 口径与路径

- `R/` 代表 `app/src-tauri/src/`；`UI/` 代表 `app/src/`。其他路径相对仓库根目录。行号是本次读取时的行号；同一文件的多个行号用“、”分隔。
- 以“消息模板/代码 + 功能显示链路”为一行；同一链路重复抛出位置合并列出。同一个 key 在多个功能使用时分别列行。动态异常按接收边界列行，底层库任意运行时异常不虚构固定文案。
- 有 key 的“zh-CN 原文”逐字取自 `app/i18n/locales/zh-CN.json`，保留占位符、标点和换行（表格内换行为 `<br>`）。无对应条目的硬编码、原版界面或依赖文案明确标注；“动态”是数据来源说明，不是虚构的语言包翻译。
- “原因”判断固定文字是否指出缺件、冲突、资源或其他条件，不将动态 `{e}` 一律当成已有原因。“步骤”表示存在操作指引，不评价是否具体、有效；自动重试的次数说明本身不算步骤。
- “原始透传”表示异常、stderr、traceback 或退出码可进入该入口的主提示/默认展开正文。仅在折叠详情或 Finding 证据中的原文另说明。行内含多个入口时，只要有一个入口默认展示即为“是”；具体差异见备注和附表。
- “按钮”记录实际控件，包括同面板的重试/操作入口；只有注册了 errorActions 且组件传入 code 才算错误专用动作。普通 ErrorNote 有复制完整错误和打开日志；compact 没有这两个按钮。
- 本次核对了安装的 `trm-ui/fabric` 实现及本地 Runtime 中的 Gradio 3.14.0。NSIS 标准模板源码未保存在本仓库，其行记录仓库内语言绑定；自定义 MessageBox 的渲染位置可直接定位。
- 无代码修复、行为修改或建议。本报告不把静态可达路径当作已经复现的实际故障。

## 按功能的主清单

### 训练：校验、启动与队列

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E001 / s.950d0895e7 | 音色名长度超出限制 | R/train.rs:1117 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E002 / s.2a330f81d4 | 「mute」为系统保留名称，请更换其他名称。 | R/train.rs:1123 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E003 / s.7dc4ea39fd | 训练进程已退出但未返回结果，请展开底部日志排查原因 | R/train.rs:1600 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 否 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E004 / trainingQueue.Changed | 任务状态已改变，请重试。 | R/train_queue.rs:189 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E005 / trainingQueue.Conflict | 已有同名角色正在训练或等待。请更换角色名称。 | R/train_queue.rs:136; R/train_queue.rs:180 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E006 / trainingQueue.Missing | 该训练任务已被移除。 | R/train_queue.rs:165 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E007 / s.trainRmvpeMissing | 缺音高模型 rmvpe.pt，先补全引擎资源 | R/train.rs:1146 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E008 / s.dc92f52f68 | 运行环境未就绪，请先补全运行环境 | R/train.rs:1134 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E009 / s.5164f3e0db | 安装不完整：缺少训练组件，请重新安装 | R/train.rs:1137 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E010 / s.5ee0565f28 | 写请求文件失败：{e} | R/train.rs:1516 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 否 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 是 |  |
| E011 / s.47e57cab60 | 找不到 Runtime\python.exe | R/train.rs:1518 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E012 / s.217047672d | 训练进程启动失败：{e} | R/train.rs:1547 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 否 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 是 |  |
| E013 / s.c73d43b29b | 无法读取训练进程的输出 | R/train.rs:1553 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 否 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E014 / s.60a21a8105 | 训练失败 | R/train.rs:1572 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 否 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E015 / s.d21a4981b7 | 等待训练进程时出错：{e} | R/train.rs:1586 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 否 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 是 |  |
| E016 / s.trainNameInvalid | 实验名不合法：{} | R/train.rs:630 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote）；清理入口 UI/components/StorageSection.tsx:249 | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E017 / s.trainBusyNoReset | 训练正在进行中，无法清空中间产物。 | R/train.rs:633 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote）；清理入口 UI/components/StorageSection.tsx:249 | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E018 / s.trainExpMissing | 找不到实验「{}」。 | R/train.rs:637; R/train.rs:640 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote）；清理入口 UI/components/StorageSection.tsx:249 | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E019 / trainingQueue.EngineBusy | 训练正在进行中，请先停止训练。 | R/train.rs:995 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E020 / s.0dabaf60ef | 音色名不能为空 | R/train.rs:1114 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E021 / s.2633fe7d2f | 音色名不能含 \ / : * ? " &lt; &gt; 等字符 | R/train.rs:1120 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E022 / s.09d3c05d6b | 音色名不能以点开头 | R/train.rs:1126 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E023 / s.ab1660b1a1 | 不支持的采样率：{a0} | R/train.rs:1140 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E024 / s.trainF0Unsupported | 不支持的音高算法：{a0} | R/train.rs:1143 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E025 / s.c7a9f88925 | 缺少 {a0} 的训练底模，请先下载 | R/train.rs:1149 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E026 / s.c2b2787278 | 缺少 hubert_base.pt，请先补全引擎资源 | R/train.rs:1157 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E027 / s.625da2c547 | 缺少训练用的静音样本，安装不完整 | R/train.rs:1160 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 否 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E028 / s.6c4b38602a | 请先选好数据集目录 | R/train.rs:1165 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 否 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E029 / s.trainOutUnwritable | 无法创建存放目录 {a0}：{a1}。请更换可写入的位置后再开始。 | R/train.rs:1375 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 否 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 是 |  |
| E030 / s.fce4b463c1 | 当前已有训练任务正在运行，请等待完成后再试。 | R/train.rs:1411 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 是 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 否 |  |
| E031 / s.7803aff201 | 训练进程异常退出（{a0}）。详情见 logs/{a1}/train.log | R/train.rs:1595 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） | 否 | 是 | 复制完整错误、打开日志；失败任务重试/移除 | 是 |  |
| E032 / trainingQueue.Failed | 训练失败 | UI/components/TrainingQueue.tsx:11 | UI/components/TrainingQueue.tsx:41（Tag 状态标签） | 否 | 否 | 重试；删除 | 否 |  |
| E033 / raw.train.queue_io | 【无 app zh-CN 条目】动态：队列 JSON 解析、文件创建/写入/重命名或异步任务错误 | R/train_queue.rs:72、73、75、78、80、95; R/lib.rs:702、717 | UI/components/TrainingQueue.tsx:28（ErrorNote）；UI/components/TrainPanel.tsx:865 | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |
| E034 / s.trainOutRelative | 存放目录必须是完整路径（比如 D:\RVC音色），当前填的是「{a0}」。 | R/train.rs:1373 | UI/components/TrainPanel.tsx:865；UI/components/TrainingQueue.tsx:55（ErrorNote） | 是 | 是 | 复制完整错误；打开日志目录 | 否 |  |
| E035 / trainingQueue.Interrupted | 训练中断 | UI/components/TrainingQueue.tsx:10 | UI/components/TrainingQueue.tsx:41（Tag 状态标签） | 是 | 否 | 重试；移除 | 否 |  |

### 训练：Python 步骤错误

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E036 / msg.train.step_failed | 该步骤失败（退出码 {code}），详情见 {log} | tools/train_worker.py:528 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 否 | 是 | 复制完整错误、打开日志；重试/移除 | 是 | run_stage 的默认 stage_code；当前预处理/F0/特征/训练调用分别传入专用失败码。 |
| E037 / msg.train.preprocess_failed | 数据预处理失败（退出码 {code}），详情见 {log} | tools/train_worker.py:567 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 否 | 是 | 复制完整错误、打开日志；重试/移除 | 是 |  |
| E038 / msg.train.no_slices | 未找到可用的音频切片，请检查数据集中是否包含有效音频文件。 | tools/train_worker.py:572 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 是 | 复制完整错误、打开日志；重试/移除；errorActions.ts → 训练说明 | 否 |  |
| E039 / msg.train.rmvpe_missing | 缺少 assets/rmvpe/rmvpe.pt，请先补全引擎资源。 | tools/train_worker.py:632 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 是 | 复制完整错误、打开日志；重试/移除；errorActions.ts → 下载模型 | 否 |  |
| E040 / msg.train.f0_failed | 音高提取失败（退出码 {code}），详情见 {log} | tools/train_worker.py:650 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 否 | 是 | 复制完整错误、打开日志；重试/移除 | 是 |  |
| E041 / msg.train.no_f0 | 音高提取没有产出。换一种音高算法再试。 | tools/train_worker.py:654 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 是 | 复制完整错误、打开日志；重试/移除；errorActions.ts → 训练说明 | 否 |  |
| E042 / msg.train.feature_failed | 特征提取失败（退出码 {code}），详情见 {log} | tools/train_worker.py:670 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 否 | 是 | 复制完整错误、打开日志；重试/移除 | 是 |  |
| E043 / msg.train.no_feature | 特征提取没有产出。通常为 assets/hubert/hubert_base.pt 缺失或损坏。 | tools/train_worker.py:675 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 否 | 复制完整错误、打开日志；重试/移除；errorActions.ts → 下载模型 | 否 |  |
| E044 / msg.train.no_samples | 四类训练产物的条目无法对应，没有可用的训练样本。建议清空该实验后重新开始。 | tools/train_worker.py:695 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 是 | 复制完整错误、打开日志；重试/移除；errorActions.ts → 训练说明 | 否 |  |
| E045 / msg.train.mute_missing | 缺少训练用的静音样本，安装不完整。 | tools/train_worker.py:710 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 否 | 复制完整错误、打开日志；重试/移除；errorActions.ts → 下载模型 | 否 |  |
| E046 / msg.train.config_missing | 缺少 configs/{name} | tools/train_worker.py:731 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 否 | 复制完整错误、打开日志；重试/移除 | 否 |  |
| E047 / msg.train.pretrained_missing | 缺少 {sample_rate} 的底模（assets/pretrained_v2/f0G{sample_rate}.pth）。从零训练需要数十小时与上百小时的素材，本软件不支持该方式，请先下载对应底模。 | tools/train_worker.py:748 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 是 | 复制完整错误、打开日志；重试/移除；errorActions.ts → 下载模型 | 否 |  |
| E048 / msg.train.train_failed | 训练失败（退出码 {code}），详情见 {log} | tools/train_worker.py:772 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 否 | 是 | 复制完整错误、打开日志；重试/移除 | 是 |  |
| E049 / msg.train.name_invalid | 音色名不能为空，也不能含 \ / : * ? " &lt; &gt; &#124; | tools/train_worker.py:865 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 否 | 复制完整错误、打开日志；重试/移除 | 否 |  |
| E050 / msg.train.bad_sample_rate | 不支持的采样率：{sample_rate} | tools/train_worker.py:868 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 否 | 复制完整错误、打开日志；重试/移除 | 否 |  |
| E051 / msg.train.bad_f0_method | 不支持的音高算法：{method} | tools/train_worker.py:872 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 否 | 复制完整错误、打开日志；重试/移除 | 否 |  |
| E052 / msg.train.usage | 用法：train_worker.py &lt;request.json&gt; | tools/train_worker.py:908 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 否 | 否 | 复制完整错误、打开日志；重试/移除 | 否 |  |
| E053 / msg.train.bad_request | 无法读取请求文件：{error} | tools/train_worker.py:912 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 否 | 否 | 复制完整错误、打开日志；重试/移除 | 是 |  |
| E054 / msg.train.dataset_missing | 数据集目录不存在：{path} | tools/train_worker.py:980 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 否 | 复制完整错误、打开日志；重试/移除 | 否 |  |
| E055 / msg.train.oom | 显卡内存不足，请调小批大小（Batch Size）或关闭其他占用显卡内存的程序后重试<br>当前批大小: {batch}<br>{log} | tools/train_worker.py:1027 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 是 | 是 | 复制完整错误、打开日志；重试/移除；TrainingQueue.tsx:55 → 调小批大小 | 否 |  |
| E056 / msg.train.no_weight | 训练结束但没找到 {name}。查看 logs/{exp}/train.log。 | tools/train_worker.py:1030 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） | 否 | 是 | 复制完整错误、打开日志；重试/移除 | 否 |  |

### 训练：界面预检与素材警告

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E057 / s.bc45fc14b1 | 运行环境未就绪，先到「其他」页补全运行环境 | UI/components/TrainPanel.tsx:383 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 是 | 下载模型（TrainPanel.tsx:361） | 否 |  |
| E058 / s.946a92f5a2 | 训练组件不全，安装可能不完整 | UI/components/TrainPanel.tsx:385 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 否 | 下载模型（TrainPanel.tsx:361） | 否 |  |
| E059 / s.e700c7ba47 | 缺 Hubert 模型，先补全引擎资源 | UI/components/TrainPanel.tsx:388 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 是 | 下载模型（TrainPanel.tsx:361） | 否 |  |
| E060 / s.trainRmvpeMissing | 缺音高模型 rmvpe.pt，先补全引擎资源 | UI/components/TrainPanel.tsx:391 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 是 | 下载模型（TrainPanel.tsx:361） | 否 |  |
| E061 / s.8f5fdb1c8a | 训练仅支持 NVIDIA 显卡。当前系统的 DirectML 环境暂不支持相关训练算子。 | UI/components/TrainPanel.tsx:395 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 否 | none | 否 |  |
| E062 / s.b453debe2c | 缺 {v0} 的训练底模。只需下载与采样率对应的那一套（与 RVC 原版 pretrained_v2 一致）。 | UI/components/TrainPanel.tsx:400 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 否 | 下载模型（TrainPanel.tsx:361） | 否 |  |
| E063 / s.trainCheckNoAudio | 选中的数据集里没有音频文件 | UI/components/TrainPanel.tsx:411 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 否 | 重新选择数据集 | 否 |  |
| E064 / s.trainCheckFewFiles | 仅有 {} 个音频文件。素材较少时，训练后的音色相似度可能不足。 | UI/components/TrainPanel.tsx:415 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 否 | none | 否 |  |
| E065 / s.trainCheckDisk | 磁盘剩余 {a0}，训练中间文件预计需要 {a1} 以上 | UI/components/TrainPanel.tsx:424 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 否 | none | 否 |  |
| E066 / s.trainCheckBatch | 批大小 {a0} 高于本机建议值 {a1}，显存不足时训练会中途失败 | UI/components/TrainPanel.tsx:431 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 否 | 调小批大小 | 否 |  |
| E067 / s.trainCheckNameTaken | 已经有一个叫「{}」的实验，继续会写进同一个目录 | UI/components/TrainPanel.tsx:438 | UI/components/TrainPanel.tsx:500（预检列表正文） | 是 | 否 | 修改实验名 | 否 |  |
| E068 / s.trainInspectShort | 素材总时长偏短，音色可能不够像。一般建议 10 分钟以上的干声。 | UI/components/TrainPanel.tsx:544 | UI/components/TrainPanel.tsx:544（状态/预检正文） | 是 | 是 | none | 否 |  |
| E069 / s.trainInspectSilent | 素材约 {}% 是静音，建议剪掉长静音段再训。 | UI/components/TrainPanel.tsx:574 | UI/components/TrainPanel.tsx:574（状态/预检正文） | 是 | 是 | none | 否 |  |
| E070 / s.trainInspectMixedRate | 素材采样率不统一（{}）。预处理会统一重采样，通常无需处理。 | UI/components/TrainPanel.tsx:556 | UI/components/TrainPanel.tsx:556（状态/预检正文） | 是 | 否 | none | 否 |  |
| E071 / s.trainInspectMixedCh | 声道不统一（{}），预处理会自动混为单声道，通常无需处理。 | UI/components/TrainPanel.tsx:581 | UI/components/TrainPanel.tsx:581（状态/预检正文） | 是 | 否 | none | 否 |  |
| E072 / s.trainSrOnly48 | 目前只有 48k 底模就绪。显存不够时可以去下载 40k 或 32k 底模。 | UI/components/TrainPanel.tsx:658 | UI/components/TrainPanel.tsx:658（状态/预检正文） | 是 | 是 | 下载模型 | 否 |  |
| E073 / s.trainStagesIncomplete | 检测到前置预处理步骤尚未完成。继续训练将自动补齐缺失的预处理流程。 | UI/components/TrainPanel.tsx:787 | UI/components/TrainPanel.tsx:787（状态/预检正文） | 是 | 否 | 继续训练 | 否 |  |
| E074 / s.trainPreprocessFailed | 上次预处理有 {a0} 个文件未能读取，成功 {a1} 个。 | UI/components/TrainPanel.tsx:792 | UI/components/TrainPanel.tsx:792（状态/预检正文） | 是 | 否 | 展开失败文件清单；清空中间产物 | 否 |  |
| E075 / s.trainInterrupted | 上次训练（{v0}）在第 {v1} / {v2} 轮中断。切片和特征仍然保留，直接开始训练即可从中断处继续，无需重新处理素材。 | UI/components/TrainPanel.tsx:845 | UI/components/TrainPanel.tsx:845（状态/预检正文） | 是 | 是 | 开始训练 | 否 |  |
| E076 / s.3d19649847 | （缺底模） | UI/components/TrainPanel.tsx:649 | UI/components/TrainPanel.tsx:649（状态/预检正文） | 是 | 否 | none | 否 |  |
| E077 / s.trainInspectLong | 单条素材偏长（中位数 {}）。若为整首歌曲，建议先用「人声分离」取出干声。 | UI/components/TrainPanel.tsx:549 | UI/components/TrainPanel.tsx:549（素材检查建议） | 是 | 是 | 重新检查素材 | 否 |  |
| E078 / s.trainInspectQuiet | 素材录音偏轻（抽样平均约 {} dB），建议提升录音音量后再训。 | UI/components/TrainPanel.tsx:567 | UI/components/TrainPanel.tsx:567（素材检查建议） | 是 | 是 | 重新检查素材 | 否 |  |
| E079 / raw.train.preprocess_file | 【无 app zh-CN 条目】动态：preprocess.log 每个失败文件最后一条非空行，截取 200 个字符，最多 20 项 | infer/modules/train/preprocess.py:119; R/train.rs:705、715、752 | UI/components/TrainPanel.tsx:821（展开失败文件清单后显示原始原因） | 否 | 否 | 查看/收起失败文件清单 | 是 |  |

### 训练：试听

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E080 / s.auditionFailed | 试听失败：{} | UI/components/TrainPanel.tsx:239 | UI/components/TrainPanel.tsx:865（ErrorNote） | 否 | 否 | 复制完整错误、打开日志；试听 | 是 |  |
| E081 / raw.train.audition | 【无 app zh-CN 条目】动态：STS 调用或音频试听失败字符串 | UI/lib/audition.ts:31; UI/components/TrainPanel.tsx:239、260 | UI/components/TrainPanel.tsx:865（ErrorNote，外包 s.auditionFailed） | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |

### 模型工具：信息、融合、提取、ONNX

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E082 / s.ckptBadAction | 未知操作：{a0} | R/ckpt.rs:61 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 否 |  |
| E083 / msg.ckpt.usage | 用法：ckpt_worker.py &lt;request.json&gt; | tools/ckpt_worker.py:193 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 否 |  |
| E084 / s.dc92f52f68 | 运行环境未就绪，请先补全运行环境 | R/ckpt.rs:64 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E085 / s.5164f3e0db | 安装不完整：缺少训练组件，请重新安装 | R/ckpt.rs:67 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E086 / s.ckptBusy | 已有模型处理任务正在进行，请稍候 | R/ckpt.rs:81 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E087 / s.5ee0565f28 | 写请求文件失败：{e} | R/ckpt.rs:150 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E088 / s.47e57cab60 | 找不到 Runtime\python.exe | R/ckpt.rs:152 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E089 / s.217047672d | 训练进程启动失败：{e} | R/ckpt.rs:177 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E090 / s.c73d43b29b | 无法读取训练进程的输出 | R/ckpt.rs:179 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 否 |  |
| E091 / s.60a21a8105 | 训练失败 | R/ckpt.rs:208 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 否 |  |
| E092 / s.d21a4981b7 | 等待训练进程时出错：{e} | R/ckpt.rs:219 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E093 / s.ckptFail | 处理失败（退出码 {a0}） | R/ckpt.rs:224 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E094 / msg.ckpt.name_empty | 保存名不能为空 | tools/ckpt_worker.py:50 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E095 / msg.ckpt.name_bad_chars | 保存名不能含 \ / : * ? " &lt; &gt; &#124; | tools/ckpt_worker.py:52 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E096 / msg.ckpt.name_invalid | 保存名不合法 | tools/ckpt_worker.py:54 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E097 / msg.ckpt.missing_model | 模型不存在：{path} | tools/ckpt_worker.py:93; tools/ckpt_worker.py:101; tools/ckpt_worker.py:168 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E098 / msg.ckpt.missing_model_a | A 模型不存在：{path} | tools/ckpt_worker.py:121 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E099 / msg.ckpt.missing_model_b | B 模型不存在：{path} | tools/ckpt_worker.py:122 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E100 / msg.ckpt.bad_sample_rate | 不支持的采样率：{sample_rate} | tools/ckpt_worker.py:131; tools/ckpt_worker.py:153 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E101 / msg.ckpt.missing_big_model | 大模型不存在：{path} | tools/ckpt_worker.py:149 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E102 / msg.ckpt.mkdir_failed | 无法创建输出目录：{error} | tools/ckpt_worker.py:178 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E103 / msg.ckpt.onnx_missing_deps | 当前运行环境缺少 ONNX 导出所需的组件（onnx 和 onnxsim）：{error} | tools/ckpt_worker.py:182 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 是 |  |
| E104 / msg.ckpt.onnx_failed | ONNX 导出失败：{error} | tools/ckpt_worker.py:187 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E105 / msg.ckpt.bad_request | 无法读取请求文件：{error} | tools/ckpt_worker.py:197 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E106 / msg.ckpt.unknown_action | 未知操作：{action} | tools/ckpt_worker.py:211 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 否 |  |
| E107 / raw.ckpt.info | 【无 app zh-CN 条目】动态：show_info 返回的完整 traceback（phase=done，info 字段） | infer/lib/train/process_ckpt.py:77; tools/ckpt_worker.py:94 | UI/components/CkptAdvanced.tsx:394（ErrorNote error=false，直接显示全文） | 否 | 否 | none | 是 |  |
| E108 / raw.ckpt.operations | 【无 app zh-CN 条目】动态：修改信息/提取/融合返回的 traceback | infer/lib/train/process_ckpt.py:207、219、277; tools/ckpt_worker.py:111、140、161 | UI/components/CkptAdvanced.tsx:394（ErrorNote，异常末行主文） | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |
| E109 / literal.ckpt.architecture | 【无 app zh-CN 条目】Fail to merge the models. The model architectures are not the same. | infer/lib/train/process_ckpt.py:247; tools/ckpt_worker.py:161 | UI/components/CkptAdvanced.tsx:394（ErrorNote） | 是 | 否 | 复制完整错误；打开日志目录 | 否 |  |

### 语音转换：任务、录音与来源清单

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E110 / s.stsDeleteUnsafe | 仅可删除输入文件夹中的音频文件 | R/sts.rs:772; R/sts_sources.rs:455 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E111 / s.stsRenameUnsafe | 仅可重命名输入文件夹中的音频文件 | R/sts.rs:791; R/sts.rs:802; R/sts.rs:812; R/sts.rs:816; R/sts.rs:819; R/sts_sources.rs:481; R/sts_sources.rs:491; R/sts_sources.rs:501; R/sts_sources.rs:504 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E112 / s.stsRenameExists | 目标文件名已存在 | R/sts.rs:826; R/sts_sources.rs:511 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E113 / s.stsRecordAlready | 录音已在进行中 | R/sts.rs:871 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E114 / s.stsHotWorkerGone | 转换过程中引擎进程已退出。请重试；如反复出现，请在「其他 - 收集诊断信息」中导出日志。 | R/sts.rs:1438 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E115 / s.stsHotStalled | 引擎长时间未响应，转换已中断。请重试。 | R/sts.rs:1447 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E116 / msg.sts.no_audio | 没有找到可转换的音频（支持 wav/mp3/flac/ogg/m4a 等） | tools/sts_worker.py:369 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E117 / msg.sts.no_request | 缺请求文件参数 | tools/sts_worker.py:506 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E118 / msg.sts.model_is_archive | 所选文件为训练检查点（G_ / D_ 开头），无法直接用于转换。<br>请先在训练页面的「进阶设置 → 模型提取」中导出音色模型。 | tools/sts_worker.py:460 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 是 | 复制完整错误；打开日志目录；errorActions.ts:82 打开训练窗口（模型提取入口） | 否 | 带 sts.model_is_archive 时 ErrorNote 额外提供打开训练窗按钮。 |
| E119 / s.stsRecordConvertBusy | 正在录音，请停止录音后再转换 | R/sts.rs:1614 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E120 / s.stsRecordNeedWorker | 缺少录音组件，请重新补全运行环境。 | R/sts.rs:943 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E121 / s.5ee0565f28 | 写请求文件失败：{e} | R/sts.rs:978; R/sts.rs:1821 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E122 / s.47e57cab60 | 找不到 Runtime\python.exe | R/sts.rs:982; R/sts.rs:1859 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E123 / s.75b84a31d6 | 运行环境未就绪，请先补全运行环境 | R/sts.rs:1738 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E124 / s.stsRecordNeedRuntime | 录音需要运行环境，请先完成首次补全。 | R/sts.rs:939 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E125 / s.4f592d4fc2 | 转换进程启动失败：{e} | R/sts.rs:1013; R/sts.rs:1892 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E126 / s.68759edc4b | 无法读取转换进程的输出 | R/sts.rs:1019; R/sts.rs:1901 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E127 / s.e9ddef6eab | 无法创建输出目录：{e} | R/sts.rs:1760 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E128 / s.6a025ac81b | 当前已有转换任务正在运行，请等待完成后再试。 | R/sts.rs:349; R/sts.rs:1609 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E129 / s.stsInputDirMissing | 未找到该文件 | R/sts.rs:769; R/sts.rs:788; R/sts.rs:846; R/sts_sources.rs:293; R/sts_sources.rs:450; R/sts_sources.rs:475 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E130 / s.stsDeleteFail | 删除失败：{a0} | R/sts.rs:775; R/sts_sources.rs:457 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E131 / s.stsRenameFail | 重命名失败：{a0} | R/sts.rs:829; R/sts_sources.rs:513 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E132 / s.stsRecordBusy | 正在转换，无法录音 | R/sts.rs:867 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E133 / s.stsRecordNoFolder | 无法创建输入文件夹：{a0} | R/sts.rs:947 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E134 / s.stsModelMissing | 未找到音色模型：{a0} | R/sts.rs:1135 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E135 / s.e84378f99a | 尚未选择音色。请先在「首页」或「模型」页选择。 | R/sts.rs:1157 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E136 / s.stsHotFailed | 转换失败。详情请查看 User_Data/logs/sts/ 中本次的日志。 | R/sts.rs:1511 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E137 / s.5eb32f1350 | 引擎资源不完整（缺 {a0}）。请先在主界面完成「引擎资源」下载（hubert / rmvpe / ffmpeg）。 | R/sts.rs:1742 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E138 / s.bc197d22e5 | 找不到转换脚本：{a0} | R/sts.rs:1746 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E139 / s.e9c01e81cb | 请先选好输入文件或文件夹 | R/sts.rs:1753; R/sts_sources.rs:276; R/sts_sources.rs:286 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E140 / s.cdad0c927d | 等待转换进程时出错：{e} | R/sts.rs:2104 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E141 / s.0d8ec50de8 | 转换进程异常退出（{a0}）。详情见 User_Data/logs/sts/ | R/sts.rs:2115 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 是 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E142 / s.stsStateUnreadable | 无法读取来源清单：{a0} | R/sts_sources.rs:114; R/sts_sources.rs:116; R/sts_sources.rs:121 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E143 / s.stsStateCorrupt | 来源清单文件已损坏，为保护数据已阻止修改 | R/sts_sources.rs:122 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E144 / msg.sts.f0_curve_missing | 找不到 F0 曲线文件：{path} | tools/sts_worker.py:354 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E145 / msg.sts.empty_fields | 音色模型、输入路径与输出路径不能为空 | tools/sts_worker.py:360 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E146 / msg.sts.model_missing | 找不到音色模型：{model} | tools/sts_worker.py:363 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 是 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 否 |  |
| E147 / msg.sts.all_failed | {total} 个文件全部转换失败。第一个原因：{first} | tools/sts_worker.py:464 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E148 / msg.sts.bad_request | 无法读取请求文件：{error} | tools/sts_worker.py:489 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 | 否 | 否 | 复制完整错误、打开日志；转换失败项可仅重试失败条目 | 是 |  |
| E149 / raw.sts.worker | 【无 app zh-CN 条目】动态：模型加载失败／转换异常；friendly_error 未识别时原文或异常末行 + traceback | tools/sts_worker.py:418、549; tools/sts_core.py:64、698、1025; gui_v1.py:4010、4024、4041、4136 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录；失败条目重试 | 是 |  |
| E150 / literal.sts.oom | 【无 app zh-CN 条目】显存不够（CUDA OOM）。常见原因：实时变声还在跑、音频太长、或显卡显存较小（如 3GB）。<br>请先在主界面停止变声，关闭其他占 GPU 的程序后重试；仍失败可把音高算法改成 harvest 或 pm（更省显存），或把长音频切短再转。 | tools/sts_core.py:74 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 是 | 复制完整错误；打开日志目录 | 否 |  |
| E151 / literal.sts.dml | 【无 app zh-CN 条目】显卡后端（DirectML）不支持这一步用到的算子，没法在显卡上完成转换。<br>可以在系统环境变量里设 TM_USE_DML=0 改用 CPU 后端后重启软件（会慢一些）。<br>原始报错：{last_error_line(text)} | tools/sts_core.py:83 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 是 | 复制完整错误；打开日志目录 | 是 | ErrorNote 折叠后两行；失败清单不折叠，故该入口原始末行可见。 |
| E152 / literal.sts.hot_empty | 【无 app zh-CN 条目】输入 / 输出目录不能为空 | gui_v1.py:3973、3976 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E153 / literal.sts.hot_no_audio | 【无 app zh-CN 条目】没有找到可转换的音频（支持 wav/mp3/flac/ogg/m4a 等） | gui_v1.py:3985 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E154 / literal.sts.no_live_model | 【无 app zh-CN 条目】实时引擎里没有可用的模型 | gui_v1.py:4041 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E155 / literal.sts.source_gone | 【无 app zh-CN 条目】源文件不存在（可能在任务开始前被移动或删除） | tools/sts_core.py:948 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E156 / literal.sts.source_missing | 【无 app zh-CN 条目】来源不存在 | R/sts_sources.rs:353 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E157 / raw.sts.source_io | 【无 app zh-CN 条目】动态：来源清单序列化/写入、请求目录创建错误 | R/sts_sources.rs:130、131; R/sts.rs:314、836、843 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |
| E158 / s.stsRecordEmpty | 未录到声音 | R/sts.rs:1096 | UI/components/TtsPanel.tsx:2233（ErrorNote） | 否 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E159 / literal.sts.unknown | 【无 app zh-CN 条目】未知错误 | tools/sts_core.py:698; tools/sts_worker.py:458; gui_v1.py:4180 | UI/components/TtsPanel.tsx:2233、2253（ErrorNote / 失败清单） | 否 | 否 | 复制完整错误；打开日志目录 | 否 |  |

### 语音转换：界面拦截

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E160 / s.bc45fc14b1 | 运行环境未就绪，先到「其他」页补全运行环境 | UI/components/TtsPanel.tsx:1001; UI/components/TtsPanel.tsx:1006 | UI/components/TtsPanel.tsx:1509（拦截正文；录音按钮同页） | 是 | 是 | 下载模型/切换目标音色（按缺件入口） | 否 |  |
| E161 / s.stsRecordNeedWorker | 缺少录音组件，请重新补全运行环境。 | UI/components/TtsPanel.tsx:1003 | UI/components/TtsPanel.tsx:1509（拦截正文；录音按钮同页） | 是 | 是 | 下载模型/切换目标音色（按缺件入口） | 否 |  |
| E162 / s.156ff9271b | 引擎资源未补全（缺 {v0}）。请先在主界面完成引擎资源下载。 | UI/components/TtsPanel.tsx:1008 | UI/components/TtsPanel.tsx:1509（拦截正文；录音按钮同页） | 是 | 是 | 下载模型/切换目标音色（按缺件入口） | 否 |  |
| E163 / s.84b7d7b6b0 | 缺少转换脚本，安装可能不完整 | UI/components/TtsPanel.tsx:1012 | UI/components/TtsPanel.tsx:1509（拦截正文；录音按钮同页） | 是 | 否 | 下载模型/切换目标音色（按缺件入口） | 否 |  |
| E164 / s.03877888b6 | 未选择目标音色。请在首页或「模型」页选择音色。 | UI/components/TtsPanel.tsx:1014; UI/components/TtsPanel.tsx:1526 | UI/components/TtsPanel.tsx:1509（拦截正文；录音按钮同页） | 是 | 是 | 下载模型/切换目标音色（按缺件入口） | 否 |  |

### 语音转换：列表与播放

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E165 / s.stsPlayFail | 无法播放该音频 | UI/components/TtsPanel.tsx:1085; UI/components/TtsPanel.tsx:1099 | UI/components/TtsPanel.tsx:1085; UI/components/TtsPanel.tsx:1099（状态/列表/错误提示；播放错误 → :2233 ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 否 |  |
| E166 / s.stsNoItems | 清单为空。请添加文件或目录。 | UI/components/TtsPanel.tsx:1355; UI/components/TtsPanel.tsx:1841 | UI/components/TtsPanel.tsx:1355; UI/components/TtsPanel.tsx:1841（状态/列表/错误提示；播放错误 → :2233 ErrorNote） | 否 | 是 | none | 否 |  |
| E167 / s.stsUnreadableTag | 目录不可读 | UI/components/TtsPanel.tsx:1652 | UI/components/TtsPanel.tsx:1652（状态/列表/错误提示；播放错误 → :2233 ErrorNote） | 是 | 否 | none | 否 |  |
| E168 / s.stsMissingTag | 来源不存在 | UI/components/TtsPanel.tsx:1653 | UI/components/TtsPanel.tsx:1653（状态/列表/错误提示；播放错误 → :2233 ErrorNote） | 是 | 否 | none | 否 |  |
| E169 / s.stsForeignBusy | 另一窗口正在转换，此处为只读状态 | UI/components/TtsPanel.tsx:2227 | UI/components/TtsPanel.tsx:2227（状态/列表/错误提示；播放错误 → :2233 ErrorNote） | 是 | 否 | none | 否 |  |
| E170 / s.stsSkippedTitle | 以下 {v0} 个文件转换失败： | UI/components/TtsPanel.tsx:2245 | UI/components/TtsPanel.tsx:2245（状态/列表/错误提示；播放错误 → :2233 ErrorNote） | 否 | 否 | 仅重试失败条目 | 否 |  |
| E171 / s.stsSourcesNoAudio | 来源中未识别到音频。 | UI/components/TtsPanel.tsx:1840 | UI/components/TtsPanel.tsx:1840（状态/列表/错误提示；播放错误 → :2233 ErrorNote） | 否 | 否 | none | 否 |  |
| E172 / s.itemReason | {v0}：{v1} | UI/components/TtsPanel.tsx:2253 | UI/components/TtsPanel.tsx:2253（条目正文） | 否 | 否 | 仅重试失败条目 | 是 | v1 来自 worker reason/message；不使用 ErrorNote 折叠。 |

### 文本转语音（SAPI 与后续 RVC）

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E173 / s.1bedd33b11 | 单次最多 {MAX_CHARS} 字，请分多次转换 | R/tts.rs:394 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 是 | 复制完整错误、打开日志 | 否 |  |
| E174 / s.f7271a7905 | 语音转换进程已结束，但未生成输出文件，请查看日志排查 | R/tts.rs:512 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 是 | 复制完整错误、打开日志 | 否 |  |
| E175 / s.75b84a31d6 | 运行环境未就绪，请先补全运行环境 | R/tts.rs:445 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E176 / s.e9ddef6eab | 无法创建输出目录：{e} | R/tts.rs:411; R/tts.rs:458 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E177 / s.6fe5607f45 | PowerShell 启动失败：{e} | R/tts.rs:190 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E178 / s.787332269e | PowerShell 执行失败 | R/tts.rs:192 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 否 |  |
| E179 / s.74d5d45130 | 系统中找不到此语音：{voice} | R/tts.rs:208 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E180 / s.9273991f94 | 无法创建缓存目录：{e} | R/tts.rs:211 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E181 / s.6619dda8e2 | 无法写入文本文件：{e} | R/tts.rs:217; R/tts.rs:220 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E182 / s.0b2b13c141 | 系统语音没有生成声音文件。请到「设置 → 时间和语言 → 语音」里确认装了语音包。 | R/tts.rs:250 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E183 / s.47baa6fbb7 | 当前已有合成任务正在运行，请等待完成后再试。 | R/tts.rs:314 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E184 / s.4e723e58f7 | 请先输入需要朗读的文本 | R/tts.rs:391 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 是 | 复制完整错误、打开日志 | 否 |  |
| E185 / s.9f8084f7cb | 无法写入输出文件：{e} | R/tts.rs:425; R/tts.rs:516 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E186 / s.ab63502dd7 | 尚未选择音色。请先在「首页」选择，或关闭「使用变声」。 | R/tts.rs:442 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E187 / s.42d0633ac9 | 系统里没有可用的语音。到「Windows 设置 → 时间和语言 → 语音」里添加一个语音包。 | UI/components/TtsPanel.tsx:2379 | UI/components/TtsPanel.tsx:2417（拦截正文） | 是 | 是 | none | 否 |  |
| E188 / s.bb1d8d1da8 | 未选择目标音色。请到首页选择一个音色，或关闭下方的「使用变声」。 | UI/components/TtsPanel.tsx:2381 | UI/components/TtsPanel.tsx:2417（拦截正文） | 是 | 是 | none | 否 |  |
| E189 / s.bc45fc14b1 | 运行环境未就绪，先到「其他」页补全运行环境 | UI/components/TtsPanel.tsx:2383 | UI/components/TtsPanel.tsx:2417（拦截正文） | 是 | 是 | none | 否 |  |
| E190 / s.68cf604e87 | 缺少推理脚本，安装可能不完整 | UI/components/TtsPanel.tsx:2385 | UI/components/TtsPanel.tsx:2417（拦截正文） | 是 | 否 | none | 否 |  |
| E191 / raw.tts.sts | 【无 app zh-CN 条目】动态：STS 后处理失败（与 raw.sts.worker 同一路径）及 Tauri 异步调用错误 | R/tts.rs:475; UI/components/TtsPanel.tsx:2341、2352、2359、2404 | UI/components/TtsPanel.tsx:2541（ErrorNote） | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |

### 人声分离

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E192 / s.38d4c44c83 | 当前已有分离任务正在运行，请等待完成后再试。 | R/separate.rs:161 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E193 / msg.sep.empty_fields | 模型、输入路径与输出路径不能为空 | tools/separate_worker.py:98 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E194 / s.6ff3d83b8f | 人声分离组件缺失（pymss_core），请重新安装或更新软件 | R/separate.rs:253 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E195 / s.5ee0565f28 | 写请求文件失败：{e} | R/separate.rs:290 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E196 / s.47e57cab60 | 找不到 Runtime\python.exe | R/separate.rs:294 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E197 / s.75b84a31d6 | 运行环境未就绪，请先补全运行环境 | R/separate.rs:246 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E198 / s.271fa82d5c | 找不到分离脚本：{a0} | R/separate.rs:250 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E199 / s.494f3ed5a0 | 请先选好输入文件和输出目录 | R/separate.rs:256 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 否 | 是 | 复制完整错误、打开日志 | 否 |  |
| E200 / s.e38da2e4e6 | 缺分离模型，请先下载 | R/separate.rs:260 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 是 | 是 | 复制完整错误、打开日志 | 否 |  |
| E201 / s.e9ddef6eab | 无法创建输出目录：{e} | R/separate.rs:262 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E202 / s.c727da1f5b | 分离进程启动失败：{e} | R/separate.rs:320 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E203 / s.1a66c860cd | 无法读取分离进程的输出 | R/separate.rs:322 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 否 | 否 | 复制完整错误、打开日志 | 否 |  |
| E204 / s.a4abecd0fe | 等待分离进程时出错：{e} | R/separate.rs:400 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E205 / s.6b7047af91 | 分离进程异常退出（{a0}）。详情见 User_Data/logs/separate.log | R/separate.rs:405 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 否 | 是 | 复制完整错误、打开日志 | 是 |  |
| E206 / msg.sep.no_request | 缺少请求文件参数 | tools/separate_worker.py:76 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 是 | 否 | 复制完整错误、打开日志 | 否 |  |
| E207 / msg.sep.bad_request | 无法读取请求文件：{error} | tools/separate_worker.py:81 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 否 | 否 | 复制完整错误、打开日志 | 是 |  |
| E208 / msg.sep.failed | 分离失败，详见日志 | tools/separate_worker.py:152 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 | 否 | 是 | 复制完整错误、打开日志 | 是 | tools/separate_worker.py:151 的 type(e): e 放入 detail；R/separate.rs:388 将它拼进同一行。 |
| E209 / s.bc45fc14b1 | 运行环境未就绪，先到「其他」页补全运行环境 | UI/components/SeparatePanel.tsx:150 | UI/components/SeparatePanel.tsx:175（拦截正文） | 是 | 是 | 下载模型 | 否 |  |
| E210 / s.92ba5de60f | 缺少分离脚本，安装可能不完整 | UI/components/SeparatePanel.tsx:152 | UI/components/SeparatePanel.tsx:175（拦截正文） | 是 | 否 | 下载模型 | 否 |  |
| E211 / s.6ff3d83b8f | 人声分离组件缺失（pymss_core），请重新安装或更新软件 | UI/components/SeparatePanel.tsx:154 | UI/components/SeparatePanel.tsx:175（拦截正文） | 是 | 是 | 下载模型 | 否 |  |
| E212 / s.f8893054c2 | 尚未安装分离模型。建议优先下载「人声提取」，清理训练素材使用该模型即可。 | UI/components/SeparatePanel.tsx:156 | UI/components/SeparatePanel.tsx:175（拦截正文） | 是 | 是 | 下载模型 | 否 |  |
| E213 / python.sep.catalog | 【无 app zh-CN 条目】分离模型清单不存在：%s | tools/pymss/model_registry.py:132 | UI/components/SeparatePanel.tsx:250（在 msg.sep.failed 后的 detail） | 是 | 否 | 复制完整错误；打开日志目录 | 是 |  |

### 实时变声与引擎生命周期

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E214 / s.wkReadyTimeout | 等待引擎就绪超时，请再试一次，或查看 User_Data/logs/realtime_worker.log | R/worker.rs:1107; R/worker.rs:1238; R/worker.rs:1249; R/worker.rs:1394 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 否 | 是 | Dock 自检（错误态）；App 故障提示动作 | 否 |  |
| E215 / s.fd40e2e936 | 找不到实时变声引擎文件：{a0} | R/worker.rs:873 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 是 | 否 | Dock 自检（错误态）；App 故障提示动作 | 否 |  |
| E216 / s.e8edbd3cce | 找不到 Runtime\pythonw.exe（根目录 {a0}）。请先补全运行环境。 | R/worker.rs:876 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 是 | 是 | Dock 自检（错误态）；App 故障提示动作 | 否 |  |
| E217 / s.7611f15dff | 无法启动引擎进程：{a0} | R/worker.rs:961; R/worker.rs:977 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 否 | 否 | Dock 自检（错误态）；App 故障提示动作 | 是 |  |
| E218 / s.wkKilledBySystem | 引擎进程被系统终止，退出码 {}。这类退出通常由第三方驱动在程序内部出错引起。 | R/worker.rs:1064; R/worker.rs:1875 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 是 | 否 | Dock 自检（错误态）；App 故障提示动作 | 是 |  |
| E219 / s.wkExitedWithCode | 引擎进程已退出，退出码 {}。 | R/worker.rs:1066 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 否 | 否 | Dock 自检（错误态）；App 故障提示动作 | 是 |  |
| E220 / s.wkStartTimeout | 启动超时 | R/worker.rs:1114 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 否 | 否 | Dock 自检（错误态）；App 故障提示动作 | 否 |  |
| E221 / s.496951c554 | 变声引擎进程意外退出（常见：显存不足、声卡被占用）。已清理残留，请再试。 | R/worker.rs:1619 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 是 | 是 | Dock 自检（错误态）；App 故障提示动作 | 否 |  |
| E222 / s.7da520ca1f | 启动超时且引擎已退出，请查看 User_Data/logs/realtime_worker.log | R/worker.rs:1630 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 否 | 是 | Dock 自检（错误态）；App 故障提示动作 | 否 |  |
| E223 / msg.vc.start_timeout | 启动超时：引擎未进入变声。请重试，或查看 User_Data/logs/realtime_worker.log | R/worker.rs:1647; R/worker.rs:1651 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 | 否 | 是 | Dock 自检（错误态）；App 故障提示动作 | 否 |  |
| E224 / s.a36cb645c2 | 运行环境未就绪（缺少 torch） | R/lib.rs:1222 | UI/components/Dock.tsx:217；UI/pages/SettingsPage.tsx:277（设置操作错误） | 是 | 否 | 自检 | 否 |  |
| E225 / s.45309ba4c5 | 运行环境未就绪，无法开启变声 | R/lib.rs:1238 | UI/components/Dock.tsx:217；UI/pages/SettingsPage.tsx:277（设置操作错误） | 是 | 否 | 自检 | 否 |  |
| E226 / s.75b84a31d6 | 运行环境未就绪，请先补全运行环境 | R/lib.rs:1199 | UI/components/Dock.tsx:217；UI/pages/SettingsPage.tsx:277（设置操作错误） | 是 | 是 | 自检 | 否 |  |
| E227 / s.9f39847f54 | 运行环境未就绪 | R/lib.rs:2253 | UI/components/Dock.tsx:217；UI/pages/SettingsPage.tsx:277（设置操作错误） | 是 | 否 | 自检 | 否 |  |
| E228 / s.40018c2fe1 | 没有可在运行中更新的参数 | R/lib.rs:2206 | UI/components/Dock.tsx:217；UI/pages/SettingsPage.tsx:277（设置操作错误） | 否 | 否 | 自检 | 否 |  |
| E229 / audio.voiceStopBeforeEngine | 音频正在语音输出中。请先停止音频，再开启变声。 | R/audio_voice.rs:466 | UI/components/Dock.tsx:217（状态错误） | 否 | 是 | none | 否 |  |
| E230 / s.exitAccessViolation | 访问冲突 | R/crash.rs:63 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） | 否 | 否 | none | 是 |  |
| E231 / s.exitDivideByZero | 整数除零 | R/crash.rs:64 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） | 否 | 否 | none | 是 |  |
| E232 / s.exitIllegalInstruction | 非法指令 | R/crash.rs:65 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） | 是 | 否 | none | 是 |  |
| E233 / s.exitStackBufferOverrun | 栈缓冲区溢出 | R/crash.rs:66 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） | 否 | 否 | none | 是 |  |
| E234 / s.exitStackOverflow | 栈溢出 | R/crash.rs:67 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） | 否 | 否 | none | 是 |  |
| E235 / s.exitMissingDll | 缺少依赖库 | R/crash.rs:68 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） | 是 | 否 | none | 是 |  |
| E236 / s.exitInterrupted | 进程被中断 | R/crash.rs:69 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） | 是 | 否 | none | 是 |  |
| E237 / raw.engine.invoke | 【无 app zh-CN 条目】动态：IPC/启动/停止/热参数更新失败；String(e) / Error.message | UI/hooks/useEngine.ts:176、199、423、485、512; UI/components/Overlay.tsx:135; R/lib.rs:2049、2093、2130 | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） | 否 | 否 | 自检；按 trouble 分类显示修复入口 | 是 |  |
| E238 / s.wkDiedListDevices | 读取设备列表时引擎进程退出，请再试一次 | R/lib.rs:2282; R/worker.rs:1390 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182；应用音色失败也至 ModelsPage.tsx:527、HomePage.tsx:340 | 否 | 是 | 自检；重试相应操作 | 否 |  |
| E239 / s.7764d6bdd2 | 后台服务未运行 | R/worker.rs:1291; R/worker.rs:1748 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182；应用音色失败也至 ModelsPage.tsx:527、HomePage.tsx:340 | 否 | 否 | 自检；重试相应操作 | 否 |  |
| E240 / s.0ec38407bc | 引擎未完全停止，声卡仍被占用 | UI/pages/HelpPage.tsx:194; R/worker.rs:1688; R/worker.rs:1697 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182；应用音色失败也至 ModelsPage.tsx:527、HomePage.tsx:340 | 是 | 否 | 自检；重试相应操作 | 否 |  |
| E241 / s.b3b2c06973 | 尚未选择音色 | R/worker.rs:1770 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182；应用音色失败也至 ModelsPage.tsx:527、HomePage.tsx:340 | 是 | 否 | 自检；重试相应操作 | 否 |  |
| E242 / s.modelApplyUnconfirmed | 引擎尚未确认音色已应用。若仍无声，请重试或重启引擎。 | R/worker.rs:1247; R/worker.rs:1248; R/worker.rs:1816 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182；应用音色失败也至 ModelsPage.tsx:527、HomePage.tsx:340 | 否 | 是 | 自检；重试相应操作 | 否 |  |
| E243 / s.engineCmdBusy | 引擎正忙，上一条指令尚未处理完成。请稍候再试。 | R/worker.rs:1236; R/worker.rs:1237 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182 | 否 | 是 | 重试 | 否 |  |
| E244 / s.wkDiedDuringLoad | 引擎进程在加载过程中退出，请查看 User_Data/logs/worker/ 中当天的日志。 | R/worker.rs:1069 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（状态文本） | 否 | 是 | 自检；重试开启 | 否 |  |
| E245 / s.wkPidNotAlive | 引擎进程已不在运行 | R/worker.rs:1101 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（状态文本） | 否 | 否 | 自检；重试开启 | 否 |  |

### 实时变声：worker 状态

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E246 / msg.engine.missing_gui | 安装不完整：缺少引擎主程序 | tools/realtime_worker.py:215 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 是 | 否 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E247 / msg.engine.crash_load | 引擎加载时崩溃，详见日志 | tools/dsp_worker.py:1032; tools/realtime_worker.py:266 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 是 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E248 / msg.engine.loop_error | 引擎内部错误，详见日志 | tools/dsp_worker.py:988; gui_v1.py:4398 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 是 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E249 / msg.engine.files_corrupt | 引擎程序文件损坏（{files}）。重新运行安装包覆盖安装即可修复。 | tools/realtime_worker.py:264 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 是 | 是 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E250 / msg.engine.nvidia_cuda_missing | 检测到 NVIDIA 显卡（{gpu}），但 CUDA 不可用。请安装官方显卡驱动并重启本软件。 | gui_v1.py:3804、4248 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 是 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E251 / msg.vc.need_model | 请选择音色，或先选用一个 DSP 预设 | tools/dsp_worker.py:723 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 是 | Dock 自检；App.tsx:1550 分类动作 | 否 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E252 / msg.vc.pth_missing | pth 文件不存在：{path} | gui_v1.py:1162 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 是 | 否 | Dock 自检；App.tsx:1550 分类动作 | 否 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E253 / msg.vc.bad_settings | 设置无效，无法开始变声 | tools/dsp_worker.py:727; gui_v1.py:3647 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 否 | Dock 自检；App.tsx:1550 分类动作 | 否 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E254 / msg.vc.start_failed | 启动失败 | tools/dsp_worker.py:918; gui_v1.py:3811 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 否 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E255 / msg.vc.dml_alloc | 当前显卡（{gpu}）无法在 DirectML 上分配模型缓存。若有 NVIDIA 显卡，请先安装官方驱动。 | gui_v1.py:3808 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 是 | 是 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E256 / msg.vc.stop_failed | 停止失败 | tools/dsp_worker.py:940; gui_v1.py:3830 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 否 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E257 / msg.vc.swap_failed | 切换失败，仍在使用上一音色 | gui_v1.py:3318; gui_v1.py:3377; gui_v1.py:3475; gui_v1.py:3497; gui_v1.py:3520; gui_v1.py:4389 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 否 | Dock 自检；App.tsx:1550 分类动作 | 否 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E258 / msg.vc.unknown_cmd | 无法识别的指令：{action} | tools/dsp_worker.py:962; tools/dsp_worker.py:966; gui_v1.py:4355 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 否 | Dock 自检；App.tsx:1550 分类动作 | 否 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E259 / msg.dev.list_failed | 读取设备失败 | tools/dsp_worker.py:856; gui_v1.py:2844 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 否 | 否 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E260 / msg.dev.invalid | 设备无效：{detail} | gui_v1.py:1169 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 | 是 | 否 | Dock 自检；App.tsx:1550 分类动作 | 是 | i18n.rs:503 仅替换 message；useEngine.ts:164–167 优先原始 error。此处原文列为 message 的语言包文本。 |
| E261 / raw.vc.status_error | 【无 app zh-CN 条目】动态：status.error 原始异常；list_devices/start/stop/loop 的类型名与异常正文 | gui_v1.py:1676、2842、3814、3828、4397; tools/realtime_worker.py:269、279; tools/dsp_worker.py:854、917、938、987 | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） | 否 | 否 | 自检；按 trouble 分类显示修复入口 | 是 | i18n.rs 仅替换 message；useEngine.ts:164 优先读 error。 |
| E262 / literal.vc.swap_missing | 【无 app zh-CN 条目】音色文件不在了，仍在用上一个音色 | gui_v1.py:3079 | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） | 是 | 否 | 重新选音色 | 否 |  |
| E263 / literal.vc.swap_failed | 【无 app zh-CN 条目】换模型失败，仍在用上一个音色 | gui_v1.py:3304 | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） | 否 | 否 | 重新选音色 | 否 |  |
| E264 / literal.dsp.crash | 【无 app zh-CN 条目】dsp worker crashed | tools/dsp_worker.py:1030 | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） | 否 | 否 | 自检 | 否 |  |
| E265 / python.device_input | 【无 app zh-CN 条目】输入设备不在列表中: {input_device!r} | gui_v1.py:2429 | UI/components/Dock.tsx:217；gui_v1.py:1046（popup） | 是 | 否 | 重新选择设备 | 是 |  |
| E266 / python.device_output | 【无 app zh-CN 条目】输出设备不在列表中: {output_device!r} | gui_v1.py:2431 | UI/components/Dock.tsx:217；gui_v1.py:1046（popup） | 是 | 否 | 重新选择设备 | 是 |  |

### 实时变声：前端拦截/兜底

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E267 / s.6aa0d5bedd | 运行环境未就绪，请先补全运行环境 | UI/hooks/useEngine.ts:305 | UI/components/Dock.tsx:205、217（状态行） | 是 | 是 | 自检；按故障分类打开音色/设备/性能/补全入口 | 否 |  |
| E268 / s.vcNeedEngineCoreShort | 请先补全引擎资源，再开启变声 | UI/hooks/useEngine.ts:363 | UI/components/Dock.tsx:205、217（状态行） | 否 | 是 | 自检；按故障分类打开音色/设备/性能/补全入口 | 否 |  |
| E269 / msg.vc.need_model | 请选择音色，或先选用一个 DSP 预设 | UI/hooks/useEngine.ts:350; UI/hooks/useEngine.ts:418 | UI/components/Dock.tsx:205、217（状态行） | 否 | 是 | 自检；按故障分类打开音色/设备/性能/补全入口 | 否 |  |
| E270 / audio.microphoneBridgeFailed | 音频混音连接已中断。请停止并重新开启变声。 | UI/hooks/useEngine.ts:165 | UI/components/Dock.tsx:205、217（状态行） | 是 | 是 | 自检；按故障分类打开音色/设备/性能/补全入口 | 否 |  |
| E271 / engine.browserNoVc | 请在软件窗口中启动变声 | UI/lib/engine.ts:224 | UI/components/Dock.tsx:205、217（状态行） | 否 | 是 | 自检；按故障分类打开音色/设备/性能/补全入口 | 否 |  |
| E272 / dock.engineError | 引擎错误 | UI/lib/engine.ts:383 | UI/components/Dock.tsx:205、217（状态行） | 否 | 否 | 自检；按故障分类打开音色/设备/性能/补全入口 | 否 |  |

### 实时变声：故障引导

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E273 / s.trouble.voice.body | 尚未选择音色，或所选音色的模型文件已不存在。请选择一个音色，或使用内置的 DSP 预设。 | UI/lib/trouble.ts:16；UI/App.tsx:933（前端按原始 error 分类） | UI/App.tsx:1553（Nudge 正文） | 是 | 是 | UI/App.tsx:1550（音色 / 补全 / 设备 / 性能 / 自检） | 否 |  |
| E274 / s.trouble.runtime.body | 运行环境尚未安装完整。补全后即可开启变声；只使用 DSP 预设时不需要运行环境。 | UI/lib/trouble.ts:16；UI/App.tsx:933（前端按原始 error 分类） | UI/App.tsx:1553（Nudge 正文） | 是 | 是 | UI/App.tsx:1550（音色 / 补全 / 设备 / 性能 / 自检） | 否 |  |
| E275 / s.trouble.devices.body | 音频设备无法打开：设备可能已断开，或被其他软件独占。请重新选择输入与输出设备。 | UI/lib/trouble.ts:16；UI/App.tsx:933（前端按原始 error 分类） | UI/App.tsx:1553（Nudge 正文） | 是 | 是 | UI/App.tsx:1550（音色 / 补全 / 设备 / 性能 / 自检） | 否 |  |
| E276 / s.trouble.vram.body | 显存不足。请在性能设置中降低质量，或关闭其他占用显卡的软件后重试。 | UI/lib/trouble.ts:16；UI/App.tsx:933（前端按原始 error 分类） | UI/App.tsx:1553（Nudge 正文） | 是 | 是 | UI/App.tsx:1550（音色 / 补全 / 设备 / 性能 / 自检） | 否 |  |
| E277 / s.trouble.unknown.body | 启动过程中出现了错误。运行自检会逐项检查运行环境、设备与虚拟声卡，并给出处理办法。 | UI/lib/trouble.ts:16；UI/App.tsx:933（前端按原始 error 分类） | UI/App.tsx:1553（Nudge 正文） | 否 | 是 | UI/App.tsx:1550（音色 / 补全 / 设备 / 性能 / 自检） | 否 |  |
| E278 / s.trouble.title | 变声未能启动 | UI/App.tsx:1545 | UI/App.tsx:1545（Nudge 标题） | 否 | 否 | 关闭；自检；按分类修复 | 否 |  |

### DSP 预设

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E279 / s.dspPresetBadId | 预设名只能用小写字母、数字和下划线，最长 48 个字符。 | R/dsp.rs:145; R/dsp.rs:198; R/dsp.rs:221 | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 | 否 | 否 | none | 否 |  |
| E280 / s.dspPresetBadParams | 预设参数格式不对。 | R/dsp.rs:148; R/dsp.rs:201 | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 | 否 | 否 | none | 否 |  |
| E281 / s.dspSaveNeedName | 请先输入预设名称。 | UI/components/DspPresetEditor.tsx:165 | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 | 否 | 是 | none | 否 |  |
| E282 / s.dspPresetSaveFail | 预设保存失败：{0} | R/dsp.rs:204; R/dsp.rs:213 | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 | 否 | 否 | none | 是 |  |
| E283 / s.dspPresetNotUser | 内置预设无法删除。如需修改，可另存同名的自定义预设进行覆盖。 | R/dsp.rs:225 | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 | 是 | 是 | none | 否 |  |
| E284 / s.dspPresetDeleteFail | 预设删除失败：{0} | R/dsp.rs:227 | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 | 否 | 否 | none | 是 |  |
| E285 / raw.dsp.load_apply | 【无 app zh-CN 条目】动态：获取预设/应用预设的 IPC 或文件错误 | UI/components/DspPresetGrid.tsx:90; UI/pages/ModelsPage.tsx:144 | UI/components/DspPresetGrid.tsx:124；UI/pages/ModelsPage.tsx:527 | 否 | 否 | 重新加载/选用预设 | 是 |  |

### 音色管理、档案与轮次切换

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E286 / s.899c21edd3 | 路径不在音色库内 | R/voices.rs:1157 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E287 / s.acaebc442f | 导入 .index 需要先选中一个可管理音色 | R/voices.rs:1885 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 否 | 否 | none | 否 |  |
| E288 / s.5584cc4752 | 不能删除默认档案 | R/voices.rs:1709 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 否 | 否 | none | 否 |  |
| E289 / s.fffda47f1e | 当前是默认参数，没有可导出的档案。请先「另存当前为档案」。 | R/voices.rs:1794 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 否 | 是 | none | 否 |  |
| E290 / s.b43921940c | 不能操作音色库根目录 | R/voices.rs:1165 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 否 | 否 | none | 否 |  |
| E291 / s.e178207ec7 | 档案名不合法：{profile_id:?} | R/voices.rs:1309 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E292 / modelVersions.invalidTarget | 音色不存在或不在音色库中。 | R/model_versions.rs:76; R/model_versions.rs:92 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E293 / modelVersions.installFailed | 切换模型失败。 | R/model_versions.rs:285; R/model_versions.rs:350 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 否 | 否 | none | 是 | model_versions.rs:285 追加原始错误；350 为不带详情的校验失败。 |
| E294 / modelVersions.invalidVersion | 该轮次模型不存在。 | R/model_versions.rs:322; R/model_versions.rs:328 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E295 / s.8cfc8f198c | 未找到该音色 | R/voices.rs:885 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E296 / s.01eba6e7b6 | 音色文件缺失或不完整 | R/voices.rs:887 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E297 / s.3c07b16355 | 音色目录不存在 | R/voices.rs:1135 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E298 / s.3ba595eced | models 目录不存在 | R/voices.rs:1138 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E299 / s.dab1a19c29 | 档案格式无效 | R/voices.rs:1469; R/voices.rs:1738 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E300 / s.a5a2f91ea1 | 无效档案: {e} | R/voices.rs:1736 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 是 |  |
| E301 / s.8af26d69aa | 活动档案文件不存在 | R/voices.rs:1798 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E302 / s.ffcf0a1eb0 | 文件不存在 | R/voices.rs:1857 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E303 / s.1090b966ea | 复制 .pth 失败: {e} | R/voices.rs:1936 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 否 | 否 | none | 是 |  |
| E304 / s.voiceDeleteFailed | 删除失败。该音色可能正在使用中，请先停止实时变声或等待转换任务完成后重试。<br>{e} | R/voices.rs:2129 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 是 | none | 是 |  |
| E305 / s.ca898456b2 | 名称不能为空 | R/voices.rs:2206 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E306 / neptune.exportMissing | 模型文件不存在，无法导出。 | R/voices.rs:2219; R/voices.rs:2263 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E307 / models.coverBadImage | 图片数据无效，保存失败 | R/voices.rs:2416; R/voices.rs:2429; R/voices.rs:2440; R/voices.rs:2444; R/voices.rs:2448; R/voices.rs:2480; R/voices.rs:2485; R/voices.rs:2487; R/voices.rs:2489; R/voices.rs:2494 | UI/components/CropCoverDialog.tsx:20 → app/node_modules/trm-ui/lib/index.js:6425（ImageCropDialog alert） | 是 | 否 | none | 否 |  |
| E308 / s.6f0a06a10f | 源 .pth 不存在 | R/voices.rs:2550 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 | 是 | 否 | none | 否 |  |
| E309 / modelVersions.engineBusy | 请先停止变声或训练，再切换轮次。 | R/train.rs:1003 | UI/pages/ModelsPage.tsx:527（toast） | 否 | 是 | none | 否 |  |
| E310 / home.switchFail | 切换失败：{error} | UI/pages/HomePage.tsx:268 | UI/pages/HomePage.tsx:268（toast / 卡片警告 / 轮次说明；home.switchFail 在 HomePage.tsx:340） | 否 | 否 | none | 是 |  |
| E311 / s.314a72cba4 | 这个音色的模型文件缺失或不完整，请重新下载或修复。 | UI/pages/HomePage.tsx:251; UI/pages/ModelsPage.tsx:416 | UI/pages/HomePage.tsx:251; UI/pages/ModelsPage.tsx:416（toast / 卡片警告 / 轮次说明；home.switchFail 在 HomePage.tsx:340） | 是 | 是 | none | 否 |  |
| E312 / s.8f61254fa2 | 这个音色的模型文件缺失或不完整，请重新下载或修复，先修好或删除后再绑定。 | UI/pages/ModelsPage.tsx:469 | UI/pages/ModelsPage.tsx:469（toast / 卡片警告 / 轮次说明；home.switchFail 在 HomePage.tsx:340） | 是 | 是 | none | 否 |  |
| E313 / s.2fe9b75856 | 缺失 | UI/pages/ModelsPage.tsx:659 | UI/pages/ModelsPage.tsx:659（toast / 卡片警告 / 轮次说明；home.switchFail 在 HomePage.tsx:340） | 是 | 否 | none | 否 |  |
| E314 / s.modelVersionsSourceRemoved | 当前使用第 {v0} 轮，源文件已删除。 | UI/pages/ModelsPage.tsx:822 | UI/pages/ModelsPage.tsx:822（toast / 卡片警告 / 轮次说明；home.switchFail 在 HomePage.tsx:340） | 是 | 否 | none | 否 |  |
| E315 / s.modelVersionsSourceRemovedUnknown | 当前版本的源文件已删除。 | UI/pages/ModelsPage.tsx:823 | UI/pages/ModelsPage.tsx:823（toast / 卡片警告 / 轮次说明；home.switchFail 在 HomePage.tsx:340） | 是 | 否 | none | 否 |  |
| E316 / s.3620fe63a3 | 这个音色不支持绑定。 | UI/pages/ModelsPage.tsx:473 | UI/pages/ModelsPage.tsx:473（绑定按钮 title） | 是 | 否 | none | 否 |  |
| E317 / s.c4a98bd0e6 | 读取音色目录失败：{v0} | UI/pages/HomePage.tsx:297 | UI/pages/HomePage.tsx:297（加载错误正文） | 否 | 否 | 重新加载 | 是 |  |
| E318 / raw.voice.io | 【无 app zh-CN 条目】动态：档案 JSON/文件操作错误；copy index: {e}；读取、导出、复制、重命名、备份文件失败 | R/voices.rs:214、216、225、226、229、380、396、1667、1735、1775、1822、1933、2153、2159、2248、2268、2272、2273、2275、2276、2279、2280、2281、2283、2284、2304、2557、2563、2571 | UI/pages/ModelsPage.tsx:527（toast）；UI/pages/HomePage.tsx:297、340（加载正文/切换 toast） | 否 | 否 | 重新执行相应音色/档案操作 | 是 |  |
| E319 / raw.voice.import_result | 【无 app zh-CN 条目】动态：批量导入 errors[].error，界面合并显示 | R/voices.rs:1857、1875、1879、1909、1911; UI/pages/ModelsPage.tsx:494 | UI/pages/ModelsPage.tsx:527（toast）；UI/pages/HomePage.tsx:297、340（加载正文/切换 toast） | 否 | 否 | 重新导入 | 是 |  |

### 设置与配置文件

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E320 / s.47a27ebb17 | 保存设置失败：{e} | R/config.rs:391; R/config.rs:510; R/config.rs:676; R/config.rs:692; R/config.rs:749; R/config.rs:829; R/config.rs:839 | UI/pages/SettingsPage.tsx:277（文本）；触发保存的音色/设备/工具面板也接收 invoke 拒绝 | 否 | 否 | none | 是 |  |
| E321 / s.4ad9fdccd9 | 写入 inuse 配置失败：{e} | R/config.rs:500 | UI/pages/SettingsPage.tsx:277（文本）；触发保存的音色/设备/工具面板也接收 invoke 拒绝 | 否 | 否 | none | 是 |  |
| E322 / s.1455f353e7 | 文件保存失败：{e} | R/config.rs:866; R/config.rs:904; R/config.rs:944 | UI/pages/SettingsPage.tsx:277（文本）；触发保存的音色/设备/工具面板也接收 invoke 拒绝 | 否 | 否 | none | 是 |  |
| E323 / s.1cab0503c2 | （当前不可用） | UI/components/Select.tsx:8 | UI/components/Select.tsx:8（PopupSelect 已失效选项后缀） | 是 | 否 | 重新选择有效选项 | 否 |  |

### 设置与设备配置

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E324 / s.e0125710be | 保存失败：{v0} | UI/pages/MorePage.tsx:113 | UI/pages/MorePage.tsx:350（ListItem desc） | 否 | 否 | none | 是 |  |
| E325 / s.computeBackendWarn | 已安装 NVIDIA 显卡的运行环境，但当前未使用 CUDA。请将「主显卡」改回「自动（不指定）」，或更新 NVIDIA 驱动后重试。 | UI/pages/MorePage.tsx:365 | UI/pages/MorePage.tsx:365（ListItem desc） | 是 | 是 | none | 否 |  |
| E326 / s.1831f7eb53 | 尚未读取到设备，请点击右侧「重新加载设备列表」重试 | UI/components/SetupGuide.tsx:298; UI/pages/SettingsPage.tsx:234 | UI/components/SetupGuide.tsx:298（设备提示）；UI/pages/SettingsPage.tsx:427（自动配置结果） | 否 | 是 | 重新加载设备列表 | 否 |  |
| E327 / s.devAutoOutWasCapture | 输出不能选虚拟声卡的录音端，已改到注入端。 | UI/lib/deviceSetup.ts:281 | UI/pages/SettingsPage.tsx:427（自动配置结果） | 否 | 否 | 重新自动配置 | 否 |  |
| E328 / s.devAutoOutWasSpeaker | 输出改到了虚拟声卡注入端，这样游戏/Discord 才能收到变声。 | UI/lib/deviceSetup.ts:281 | UI/pages/SettingsPage.tsx:427（自动配置结果） | 否 | 否 | 重新自动配置 | 否 |  |
| E329 / raw.settings.auto | 【无 app zh-CN 条目】动态：设备列表刷新或自动配置 invoke 错误 | UI/pages/SettingsPage.tsx:250 | UI/pages/SettingsPage.tsx:427（自动配置提示） | 否 | 否 | 重新自动配置 | 是 |  |

### 音频设备恢复

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E330 / neptune.deviceRecovery | 音频设备无法启动。可忽略检查失败的设备，然后重新配置。 | R/audio_recovery.rs:103 | UI/components/AudioRecovery.tsx:41（Nudge）、66（alert）；探测崩溃也至 Dock.tsx:217 | 否 | 否 | 忽略故障设备并重试；兼容模式；恢复设备 | 否 |  |
| E331 / s.audioProbeCrash | 读取音频设备列表时进程被系统终止，退出码 {}。 | R/audio_probe.rs:74 | UI/components/AudioRecovery.tsx:41（Nudge）、66（alert）；探测崩溃也至 Dock.tsx:217 | 是 | 否 | 忽略故障设备并重试；兼容模式；恢复设备 | 是 |  |
| E332 / neptune.compatibilityFailed | 音频兼容组件尚未就绪，请检查网络后重试。 | R/audio_recovery.rs:54; R/audio_recovery.rs:112 | UI/components/AudioRecovery.tsx:41（Nudge）、66（alert）；探测崩溃也至 Dock.tsx:217 | 是 | 是 | 忽略故障设备并重试；兼容模式；恢复设备 | 否 |  |
| E333 / neptune.deviceCheckFailed | 音频设备检查未能完成。请尝试兼容模式，或在设备与音频设置中重新选择设备。 | R/audio_recovery.rs:74 | UI/components/AudioRecovery.tsx:66（alert） | 否 | 是 | 忽略故障设备并重试；兼容模式 | 否 |  |
| E334 / raw.recovery.native | 【无 app zh-CN 条目】动态：兼容组件下载/ZIP/文件读写、探测进程、JSON、异步错误 | R/audio_recovery.rs:17、22、23、26、34、36、41、45、47、48、56、72、76、77、174 | UI/components/AudioRecovery.tsx:41（Nudge error）及 :66（alert） | 否 | 否 | 忽略故障设备并重试；兼容模式 | 是 |  |
| E335 / s.audioProbeAsio | 本机已注册的 ASIO 驱动：{}。请更新或卸载相关驱动后重试。 | R/audio_probe.rs:77 | UI/components/Dock.tsx:217（拼接于 audioProbeCrash）；AudioRecovery.tsx:41 的恢复操作错误 | 否 | 是 | 自检；重新选择/恢复设备 | 否 |  |

### 麦克风测试

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E336 / s.micErrOpen | 无法打开麦克风。请检查设备是否连接正常，以及系统「麦克风隐私设置」是否允许本软件使用麦克风。 | R/mic.rs:74; R/mic.rs:76; R/mic.rs:236 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 否 | 是 | 重新测试；停止测试 | 否 |  |
| E337 / s.stsRecordNeedWorker | 缺少录音组件，请重新补全运行环境。 | R/mic.rs:106 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 是 | 是 | 重新测试；停止测试 | 否 |  |
| E338 / s.5ee0565f28 | 写请求文件失败：{e} | R/mic.rs:123; R/mic.rs:135 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 否 | 否 | 重新测试；停止测试 | 是 |  |
| E339 / s.47e57cab60 | 找不到 Runtime\python.exe | R/mic.rs:108 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 是 | 否 | 重新测试；停止测试 | 否 |  |
| E340 / s.micErrBusy | 无法打开麦克风：设备正被占用。请先在主界面停止变声（尤其开启了 WASAPI 独占时），或关闭其他正在使用麦克风的软件。 | R/mic.rs:68 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 是 | 是 | 重新测试；停止测试 | 否 |  |
| E341 / s.micErrNotFound | 找不到设置中选择的输入设备。设备可能已断开，请点击「重新扫描」后重新选择。 | R/mic.rs:69 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 是 | 是 | 重新测试；停止测试 | 否 |  |
| E342 / s.micErrNoLib | 运行环境里的音频组件不可用，请先完成一次「补全运行环境」。 | R/mic.rs:70 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 否 | 是 | 重新测试；停止测试 | 否 |  |
| E343 / s.micTestSilent | 未检测到音频输入。请检查麦克风连接、系统静音设置，或切换其他输入设备。 | R/mic.rs:73; R/mic.rs:243 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 是 | 是 | 重新测试；停止测试 | 否 |  |
| E344 / s.micTestBusy | 麦克风测试正在进行中，请稍候。 | R/mic.rs:85 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 是 | 是 | 重新测试；停止测试 | 否 |  |
| E345 / s.stsRecordNeedRuntime | 录音需要运行环境，请先完成首次补全。 | R/mic.rs:102 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 否 | 是 | 重新测试；停止测试 | 否 |  |
| E346 / s.4f592d4fc2 | 转换进程启动失败：{e} | R/mic.rs:164 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 否 | 否 | 重新测试；停止测试 | 是 |  |
| E347 / s.68759edc4b | 无法读取转换进程的输出 | R/mic.rs:170 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 否 | 否 | 重新测试；停止测试 | 否 |  |
| E348 / raw.mic.unknown | 【无 app zh-CN 条目】动态：未命中 busy/notfound/nolib/silent/enum/open 的 worker message 原文 | R/mic.rs:75; tools/record_worker.py:351、363 | UI/components/MicTest.tsx:153；UI/components/LinkCheckDialog.tsx:391（结果正文） | 否 | 否 | 重新测试 | 是 |  |

### 音频裁剪与波形

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E349 / neptune.selectionInvalid | 不能删除整段音频，请缩小选择范围。 | UI/components/AudioTrim.tsx:181 | UI/components/AudioTrim.tsx:181（错误/校验正文）；:152（波形失败） | 否 | 是 | 重新选择范围 / 应用裁剪 / 试听按钮仍在当前面板 | 否 |  |
| E350 / neptune.waveformFailed | 波形读取失败，仍可使用下方时间输入。 | UI/components/AudioTrim.tsx:152 | UI/components/AudioTrim.tsx:181（错误/校验正文）；:152（波形失败） | 否 | 是 | 重新选择范围 / 应用裁剪 / 试听按钮仍在当前面板 | 否 |  |
| E351 / neptune.previewFailed | 无法试听此文件。 | UI/components/AudioTrim.tsx:125; UI/components/AudioTrim.tsx:175 | UI/components/AudioTrim.tsx:181（错误/校验正文）；:152（波形失败） | 否 | 否 | 重新选择范围 / 应用裁剪 / 试听按钮仍在当前面板 | 否 |  |
| E352 / neptune.trimFailed | 音频裁剪失败。 | R/audio_edit.rs:195; R/audio_edit.rs:274 | UI/components/AudioTrim.tsx:181（错误/校验正文）；:152（波形失败） | 否 | 否 | 重新选择范围 / 应用裁剪 / 试听按钮仍在当前面板 | 是 | R/audio_edit.rs:193、272 在固定文本后附加 ffmpeg stderr；AudioTrim 不折叠。 |
| E353 / neptune.trimInvalid | 请选择有效的音频文件和起止时间。 | UI/components/AudioTrim.tsx:181; R/audio_edit.rs:142; R/audio_edit.rs:204 | UI/components/AudioTrim.tsx:181（错误正文） | 否 | 是 | 重新选择裁剪时间 | 否 |  |
| E354 / raw.trim.native | 【无 app zh-CN 条目】动态：目录创建、ffmpeg 启动或异步任务失败 | R/audio_edit.rs:146、186、208、265、297、317 | UI/components/AudioTrim.tsx:181（正文） | 否 | 否 | 重新选择/导出 | 是 |  |

### 运行环境补全与迁移

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E355 / s.e12d8322af | 未能识别显卡类型：{}，请手动选择 | R/provision.rs:99 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 否 | 是 | 补全重试 / 迁移重试 | 否 |  |
| E356 / s.rtExtractFailed | 下载与校验均已通过，失败发生在解压步骤，重新下载无法解决该问题。 | R/provision.rs:693 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 否 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E357 / s.rtExtractHelp | 建议排查以下项目：<br>• 将软件安装目录添加至杀毒软件白名单后重新执行补全<br>• 确认目标磁盘剩余空间不少于 20 GB<br>• 将软件安装至非系统盘，且安装路径中请勿包含中文或空格<br>• 若仍无法解决，请前往「其他」页扫码加入 QQ 群反馈 | R/provision.rs:697; R/provision.rs:1008; R/provision.rs:1027 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 是 | 补全重试 / 迁移重试 | 否 |  |
| E358 / s.dlReconnect | 连接失败，正在重连（第 {v0} 次）… | R/provision.rs:928 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 否 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E359 / runtimeMigration.required | 请先完成运行环境迁移。 | R/provision.rs:807 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 否 | 是 | 补全重试 / 迁移重试 | 否 |  |
| E360 / runtimeMigration.stopEngine | 请先停止变声引擎，再切换或更新运行环境。 | R/provision.rs:813; R/provision.rs:832; R/runtime_migration.rs:141 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 否 | 是 | 补全重试 / 迁移重试 | 否 |  |
| E361 / runtimeMigration.targetExists | 运行环境目标已存在：{v0} | R/provision.rs:756; R/runtime_migration.rs:149 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E362 / runtimeMigration.selectVariant | 无法确认旧版运行环境类型，请选择： | R/runtime_migration.rs:133 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 否 | 是 | 补全重试 / 迁移重试 | 否 |  |
| E363 / s.90e6bba99d | 移动运行环境失败：{e} | R/provision.rs:763; R/provision.rs:770; R/runtime_migration.rs:173 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 否 | 否 | 补全重试 / 迁移重试 | 是 |  |
| E364 / s.eca157a71e | 已有补全任务在进行 | R/provision.rs:38 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 否 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E365 / s.47c37d6efa | 未检测到显卡，请手动选择运行环境版本 | R/provision.rs:60 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 是 | 补全重试 / 迁移重试 | 否 |  |
| E366 / runtimeMigration.runtimeNotReady | 这套运行环境尚未就绪。 | R/provision.rs:511 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E367 / s.ee7e83d91d | 运行环境已就绪，但缺少实时变声组件 | R/provision.rs:663 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E368 / runtimeMigration.runtimeBusy | 仍有 {v0} 个进程在使用这套运行环境（原版 WebUI、实时面板或转换任务）。请先关闭它们再重试。 | R/provision.rs:839; R/provision.rs:1016 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 是 | 补全重试 / 迁移重试 | 否 |  |
| E369 / s.33d04e20c0 | 组件列表中没有可用的运行环境下载地址。 | R/provision.rs:848 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E370 / s.09dfaea8c0 | 运行环境清单缺少有效的 sha256，已拒绝下载。 | R/provision.rs:861 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E371 / s.74aef4af02 | 解压完成，但未检测到 torch，运行环境可能不完整。 | R/provision.rs:1007; R/provision.rs:1026 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E372 / runtimeMigration.notFound | 找不到旧版运行环境。 | R/runtime_migration.rs:162 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 是 | 否 | 补全重试 / 迁移重试 | 否 |  |
| E373 / s.44c7946c76 | 补全失败 | UI/components/ProvisionGate.tsx:155 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） | 否 | 否 | 补全重试 | 否 |  |
| E374 / engine.browserNoRuntime | 浏览器预览无法探测运行环境 | UI/lib/engine.ts:294 | UI/components/Dock.tsx:217 / UI/components/ProvisionGate.tsx:335（浏览器预览返回的状态/错误） | 否 | 否 | none | 否 |  |
| E375 / engine.browserNoDownload | 浏览器预览无法下载运行环境 | UI/lib/engine.ts:306 | UI/components/Dock.tsx:217 / UI/components/ProvisionGate.tsx:335（浏览器预览返回的状态/错误） | 否 | 否 | none | 否 |  |
| E376 / runtimeMigration.verifyFailed | 迁移后的运行环境未通过检查。 | R/runtime_migration.rs:190 | UI/components/RuntimeMigrationDialog.tsx:178（错误正文） | 否 | 否 | 重试 | 否 |  |
| E377 / runtimeMigration.waitingDescription | 已找到旧版运行环境，但无法确认类型。请选择后才会开始迁移。 | UI/components/RuntimeMigrationDialog.tsx:112 | UI/components/RuntimeMigrationDialog.tsx:110（等待选择说明） | 否 | 是 | 选择环境类型后迁移 | 否 |  |
| E378 / raw.runtime.io | 【无 app zh-CN 条目】动态：运行环境状态/标记文件、目录创建、备份删除等 I/O 异常 | R/provision.rs:467、469、482、484、742、745、761; UI/components/RuntimeMigrationDialog.tsx:65、92、197、223 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（正文） | 否 | 否 | 重试/选择类型；compact 无错误复制按钮 | 是 |  |

### 下载通道与压缩包解压

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E379 / s.dlWhyReset | 连接在传输过程中被断开。常见于不稳定的 Wi-Fi、代理，或防火墙切断长连接。 | R/download.rs:227; R/download.rs:243 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E380 / s.netUnknown | 无法获取在线信息。请稍后重试；问题持续时，请在「其他」页加入 QQ 群反馈。 | R/download.rs:240 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E381 / s.netCheckNetwork | 请检查网络连接或代理设置后重试。 | R/download.rs:243 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E382 / s.netRetryOrManual | 请重试；若仍失败，请前往官网下载安装包。 | R/download.rs:244 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E383 / s.dlGaveUp | 已自动重试 {v0} 次仍未成功。 | R/download.rs:270 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E384 / s.dlFailedHelp | 可以尝试：<br>• 检查网络是否通畅，或更换网络（例如手机热点）<br>• 关闭或更换代理 / VPN 后重试<br>• 服务器繁忙时请稍候片刻<br>• 仍然无法解决，请到「其他」页扫码加入 QQ 群（1077458748）反馈 | R/download.rs:273 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E385 / s.dlTriedHosts | 已尝试 {a0} 个下载源：{a1} | R/download.rs:263 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E386 / s.dlDetail | 技术细节（反馈时请一并贴上）：{e} | R/download.rs:276 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 | compact ErrorNote 收入详情；Extras/Store 的正文未折叠。 |
| E387 / s.70f6a74f68 | 压缩包含空路径 | R/extract.rs:44 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E388 / s.099b711760 | 含盘符路径：{name} | R/extract.rs:47 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E389 / s.7801d82550 | 路径越界：{name} | R/extract.rs:53 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E390 / s.38ad9afc9b | 路径非法：{name} | R/extract.rs:54 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E391 / s.242a3a8640 | 压缩包{e} | R/extract.rs:221 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E392 / s.e0dab22b1a | 下载失败 | R/download.rs:958 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E393 / s.dlWhyHash | 下载已完成，但文件内容与清单校验不一致。可能在传输中被修改或损坏，无法安装。 | R/download.rs:193; R/download.rs:244 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E394 / s.dlWhyDisk | 磁盘空间不足，无法写入。运行环境解压后约需十几 GB，请清理空间后重试。 | R/download.rs:196 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E395 / s.dlWhyPerm | 文件写入被拒绝。可能是杀毒软件拦截，或安装目录没有写入权限。 | R/download.rs:200; R/download.rs:244 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E396 / s.dlWhyDns | 无法解析下载服务器的地址。通常是 DNS 故障，或该域名被拦截。 | R/download.rs:203; R/download.rs:243 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E397 / s.dlWhyTls | 无法建立安全连接。可能有代理、企业网关或杀毒软件介入了该连接。 | R/download.rs:206; R/download.rs:243 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E398 / s.dlWhyRefused | 下载源无法提供此文件。请稍后重试。 | R/download.rs:216 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E399 / s.dlWhyServer | 服务器返回错误。此问题与你的网络无关，请稍后重试。 | R/download.rs:221 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E400 / s.dlWhyUnreachable | 无法连接到下载服务器。请检查网络连接，或确认代理配置是否正确。 | R/download.rs:230 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E401 / s.5ca337dd03 | sha256 格式无效 | R/download.rs:543 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E402 / s.73a397a7fd | sha256 不匹配\n期望 {a0}\n实际 {a1} | R/download.rs:547 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E403 / s.21ce93c732 | 打开文件失败: {e} | R/download.rs:553 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E404 / s.d08e45e275 | 没有下载地址 | R/download.rs:701 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E405 / s.fe9e98a65c | 完成重命名失败: {e} | R/download.rs:883 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E406 / s.9f44b201ee | 打开 tar 失败: {e} | R/extract.rs:83 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E407 / runtimeMigration.targetExists | 运行环境目标已存在：{v0} | R/extract.rs:139 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E408 / s.79a3d2ebab | 读取 tar 失败: {e} | R/extract.rs:151 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E409 / s.f456299616 | tar 条目错误: {e} | R/extract.rs:154 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E410 / s.646bbce5a0 | 解压失败 {a0}: {a1} | R/extract.rs:166 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E411 / s.b4817b7fdf | 解压后未找到 Runtime\python.exe。请检查下载的压缩包是否完整，或重试。 | R/extract.rs:192 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 是 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E412 / s.90e6bba99d | 移动运行环境失败：{e} | R/extract.rs:200 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E413 / s.101fd24d34 | 解压后未找到 Runtime\python.exe。 | R/extract.rs:206 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E414 / s.e32a4f9295 | 打开压缩包失败：{e} | R/extract.rs:214 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E415 / s.c9aafa74d7 | 读取压缩包失败：{e} | R/extract.rs:215 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E416 / s.4a02ebe151 | 压缩包路径不安全：{name} | R/extract.rs:226 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 是 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 否 |  |
| E417 / s.a4462e4266 | 写入 {a0} 失败：{a1} | R/extract.rs:236 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） | 否 | 否 | 对应下载/安装重试；compact ErrorNote 只有详情 | 是 |  |
| E418 / s.dlWhyBusy | 服务器提示请求过于频繁。请等待几分钟后重试。 | R/download.rs:209 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；ExtrasDialog.tsx:379、StoreSection.tsx:616（正文） | 是 | 是 | 下载入口重试 | 否 |  |
| E419 / s.dlWhyTimeout | 已连接到服务器，但长时间未收到数据。通常是网络过慢，或链路中途被阻塞。 | R/download.rs:224; R/download.rs:243 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；ExtrasDialog.tsx:379、StoreSection.tsx:616（正文） | 是 | 否 | 下载入口重试 | 否 |  |
| E420 / raw.download.unknown | 【无 app zh-CN 条目】动态：download_error_text 未识别的错误原文位于首行 | R/download.rs:254 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；ExtrasDialog.tsx:379、StoreSection.tsx:616（正文）；UpdateNudge.tsx:72 | 否 | 否 | 对应下载入口重试 | 是 |  |

### 组件、底模与分离模型下载/删除

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E421 / s.ae3f0d2168 | 清单里没有 {key} 这条资源 | R/extra_assets.rs:513; R/extra_assets.rs:599 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 否 | 否 | 重新下载 / 取消 / 删除 | 否 |  |
| E422 / s.42b898eb36 | 当前已有下载任务正在运行，请稍候。 | R/extra_assets.rs:44 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 是 | 是 | 重新下载 / 取消 / 删除 | 否 |  |
| E423 / s.dlReconnect | 连接失败，正在重连（第 {v0} 次）… | R/extra_assets.rs:621 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 否 | 否 | 重新下载 / 取消 / 删除 | 否 |  |
| E424 / s.extraRemoveTrainBusy | 训练正在进行，请先停止后再卸载训练底模。 | R/extra_assets.rs:515 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 是 | 是 | 重新下载 / 取消 / 删除 | 否 |  |
| E425 / s.extraRemoveSepBusy | 人声分离正在进行，请先停止后再卸载分离模型。 | R/extra_assets.rs:516 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 是 | 是 | 重新下载 / 取消 / 删除 | 否 |  |
| E426 / s.341bc35cbf | 组件列表给出的保存路径不安全：{a0} | R/extra_assets.rs:520; R/extra_assets.rs:601 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 是 | 否 | 重新下载 / 取消 / 删除 | 否 |  |
| E427 / s.extraRemoveFailed | {a0} 无法删除：{a1}。文件可能正被占用，请先停止分离/训练后重试。 | R/extra_assets.rs:551 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 是 | 是 | 重新下载 / 取消 / 删除 | 是 |  |
| E428 / s.ec982d9c98 | 无法创建目录：{e} | R/extra_assets.rs:602; R/extra_assets.rs:613 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 否 | 否 | 重新下载 / 取消 / 删除 | 是 |  |
| E429 / s.0df1f31a67 | {a0} 下载失败：{a1} | R/extra_assets.rs:638 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 否 | 否 | 重新下载 / 取消 / 删除 | 是 |  |
| E430 / s.538ff61331 | {a0} 保存失败：{a1} | R/extra_assets.rs:642 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 | 否 | 否 | 重新下载 / 取消 / 删除 | 是 |  |
| E431 / s.d15a7a3da1 | 浏览器预览中无法获取组件列表 | UI/lib/voices.ts:392 | UI/components/ExtrasDialog.tsx:379（正文）；CommunityDownloadOrb.tsx:89 | 否 | 否 | 重新下载 | 否 |  |
| E432 / s.e0dab22b1a | 下载失败 | UI/lib/extraJobs.ts:71 | UI/components/ExtrasDialog.tsx:379（正文）；CommunityDownloadOrb.tsx:89 | 否 | 否 | 重新下载 | 否 |  |
| E433 / s.122abe360d | 无法连接服务器，请检查网络后重试。 | UI/components/ExtrasDialog.tsx:222 | UI/components/ExtrasDialog.tsx:331（emptyHint 正文） | 否 | 是 | 刷新 | 否 |  |
| E434 / s.extraRemoveBusy | 该组件正在下载中，请等待完成或取消后再删除。 | R/extra_assets.rs:495 | UI/components/ExtrasDialog.tsx:379（正文） | 否 | 是 | 取消下载/完成后删除 | 否 |  |

### 引擎资源、音频组件与虚拟声卡

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E435 / s.vbcablePackBroken | 安装包解压后不完整，请重新下载 | R/engine_assets.rs:424 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 是 | 是 | 组件下载重试；驱动安装/卸载 | 否 |  |
| E436 / s.vbcableNoSetup | 没找到 VB-Cable 安装程序，请先下载安装包 | R/engine_assets.rs:467 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 否 | 是 | 组件下载重试；驱动安装/卸载 | 否 |  |
| E437 / s.vbcableCancelled | 已取消：安装驱动需要管理员权限 | R/engine_assets.rs:495 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 是 | 否 | 组件下载重试；驱动安装/卸载 | 否 |  |
| E438 / s.vbcableUninstallCancelled | 已取消：卸载驱动需要管理员权限 | R/engine_assets.rs:493 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 是 | 否 | 组件下载重试；驱动安装/卸载 | 否 |  |
| E439 / s.vbcableWindowsOnly | 只有 Windows 能安装虚拟声卡 | R/engine_assets.rs:541; R/engine_assets.rs:546 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 否 | 否 | 组件下载重试；驱动安装/卸载 | 否 |  |
| E440 / s.04c4e3b2b3 | 下载失败：{e} | R/engine_assets.rs:278; R/engine_assets.rs:331 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 否 | 否 | 组件下载重试；驱动安装/卸载 | 是 |  |
| E441 / s.f36aff2870 | 引擎资源仍缺少：{a0} | R/engine_assets.rs:139; R/engine_assets.rs:398 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 是 | 否 | 组件下载重试；驱动安装/卸载 | 否 |  |
| E442 / s.0707e8af4e | 解压失败：{e} | R/engine_assets.rs:280; R/engine_assets.rs:334 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 否 | 否 | 组件下载重试；驱动安装/卸载 | 是 |  |
| E443 / s.vbcableUninstallFailedCode | 卸载失败（错误码 {e}） | R/engine_assets.rs:488 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 否 | 否 | 组件下载重试；驱动安装/卸载 | 是 |  |
| E444 / s.vbcableFailedCode | 安装失败（错误码 {e}） | R/engine_assets.rs:490 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 否 | 否 | 组件下载重试；驱动安装/卸载 | 是 |  |
| E445 / s.23220ab448 | 启动安装程序失败：{e} | R/engine_assets.rs:517 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） | 否 | 否 | 组件下载重试；驱动安装/卸载 | 是 |  |
| E446 / s.1b94ca3bf5 | 无法查询安装包状态，点右侧仍可尝试下载并安装 | UI/pages/HelpPage.tsx:467 | UI/pages/HelpPage.tsx:440、443、467（说明/安装状态） | 否 | 是 | 下载安装；查看设备设置说明 | 否 |  |
| E447 / s.60f0f911ec | 尚未读取到设备列表，暂时无法判断是否已安装虚拟声卡。请在引擎启动后，或到「设置 → 设备与音频」点击一次「重新加载设备列表」后再次查看。 | UI/pages/HelpPage.tsx:440 | UI/pages/HelpPage.tsx:440、443、467（说明/安装状态） | 否 | 是 | 下载安装；查看设备设置说明 | 否 |  |
| E448 / s.helpNoRoute | 在 {n} 个设备中没有找到可用的转发通道，需要安装虚拟声卡。点击下方「安装虚拟声卡」即可。 | UI/pages/HelpPage.tsx:443 | UI/pages/HelpPage.tsx:440、443、467（说明/安装状态） | 是 | 否 | 下载安装；查看设备设置说明 | 否 |  |

### VC++ 运行库安装

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E449 / s.vcrPackMissing | 当前版本未附带运行库安装包 | R/vcredist.rs:125 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） | 否 | 否 | 安装重试 | 否 |  |
| E450 / s.vcrPackBroken | 运行库安装包不完整，请重试 | R/vcredist.rs:141 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） | 是 | 是 | 安装重试 | 否 |  |
| E451 / s.vcrNoSetup | 安装包里找不到安装程序 | R/vcredist.rs:154 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） | 是 | 否 | 安装重试 | 否 |  |
| E452 / s.vcrWindowsOnly | 该操作仅支持 Windows | R/vcredist.rs:178 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） | 否 | 否 | 安装重试 | 否 |  |
| E453 / s.vcrCancelled | 安装已取消，可稍后在设置页重试（代码 {e}） | R/vcredist.rs:64 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） | 否 | 是 | 安装重试 | 是 |  |
| E454 / s.vcrBusy | 系统正在安装其他程序，请稍后重试（代码 {e}） | R/vcredist.rs:65 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） | 是 | 是 | 安装重试 | 是 |  |
| E455 / s.vcrFailed | 运行库安装失败（代码 {e}） | R/vcredist.rs:66; R/vcredist.rs:168 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） | 否 | 否 | 安装重试 | 是 |  |

### 社区目录、下载与音色包安装

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E456 / s.007e8f085e | 音色包{e} | R/store.rs:901 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 否 | 否 | 刷新 / 下载 / 暂存安装重试 | 是 |  |
| E457 / s.0c6c58c683 | 该音色尚未下载完成 | R/store.rs:1816 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 否 | 否 | 刷新 / 下载 / 暂存安装重试 | 否 |  |
| E458 / community.refreshBeforeDownload | 请刷新社区后再下载此版本。 | R/community_catalog.rs:248 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 否 | 是 | 刷新 / 下载 / 暂存安装重试 | 否 |  |
| E459 / s.dlReconnect | 连接失败，正在重连（第 {v0} 次）… | R/store.rs:24 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 否 | 否 | 刷新 / 下载 / 暂存安装重试 | 否 |  |
| E460 / community.catalogUnavailable | 无法刷新社区目录。 | R/community_catalog.rs:478; R/store.rs:491 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 否 | 否 | 刷新 / 下载 / 暂存安装重试 | 否 |  |
| E461 / s.760364197e | 找不到音色包：{a0} | R/store.rs:1183 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 是 | 否 | 刷新 / 下载 / 暂存安装重试 | 否 |  |
| E462 / s.41e7454584 | 音色包内没有 .pth 文件 | R/store.rs:1202 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 是 | 否 | 刷新 / 下载 / 暂存安装重试 | 否 |  |
| E463 / s.713173a2d7 | 音色包内 .pth 过小，可能损坏 | R/store.rs:1205 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 是 | 否 | 刷新 / 下载 / 暂存安装重试 | 否 |  |
| E464 / s.8c8dade1e1 | 复制 pth 失败：{e} | R/store.rs:1304 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 否 | 否 | 刷新 / 下载 / 暂存安装重试 | 是 |  |
| E465 / s.40dc667415 | 音色 {id} 缺少有效的 sha256，已拒绝安装 | R/store.rs:1485 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 是 | 否 | 刷新 / 下载 / 暂存安装重试 | 否 |  |
| E466 / s.80b25fdbcd | 删除失败：{e} | R/store.rs:1825 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 否 | 否 | 刷新 / 下载 / 暂存安装重试 | 是 |  |
| E467 / s.361cb27e7b | 暂存目录里没有可安装的文件 | R/store.rs:1852; R/store.rs:1858 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 是 | 否 | 刷新 / 下载 / 暂存安装重试 | 否 |  |
| E468 / s.afcf23635f | 复制模型失败：{e} | R/store.rs:1913 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 | 否 | 否 | 刷新 / 下载 / 暂存安装重试 | 是 |  |
| E469 / s.bea562b0a7 | 浏览器预览无法联网拉取社区内容 | UI/lib/plaza.ts:61 | UI/pages/PlazaPage.tsx:310；UI/components/StoreSection.tsx:518（Warn） | 否 | 否 | 刷新 | 否 |  |
| E470 / raw.store.io | 【无 app zh-CN 条目】动态：下载/安装/删除失败的 String(e)；下载队列前缀为 {label &#124;&#124; id}： | UI/lib/storeJobs.ts:141; UI/components/StoreSection.tsx:208、447、463; UI/hooks/usePlaza.ts:35 | UI/components/StoreSection.tsx:518、616（正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71；CommunityDownloadOrb.tsx:89（悬浮提示） | 否 | 否 | 重新下载/刷新；下载球跳转错误页面 | 是 |  |
| E471 / s.a005e42321 | 社区内容：{e} | R/plaza.rs:459 | UI/pages/PlazaPage.tsx:310（Warn）；StoreSection.tsx:518、616（正文） | 否 | 否 | 刷新/重试 | 是 |  |
| E472 / s.d2620f4b90 | 更新日志：{e} | R/plaza.rs:466 | UI/pages/PlazaPage.tsx:310（Warn）；StoreSection.tsx:518、616（正文） | 否 | 否 | 刷新/重试 | 是 |  |
| E473 / s.5ca65185f2 | 音色未配置下载地址 | R/store.rs:1583 | UI/pages/PlazaPage.tsx:310（Warn）；StoreSection.tsx:518、616（正文） | 是 | 否 | 刷新/重试 | 否 |  |
| E474 / s.281cb87781 | 下载的模型文件过小，可能不是有效 .pth | R/store.rs:1631 | UI/pages/PlazaPage.tsx:310（Warn）；StoreSection.tsx:518、616（正文） | 是 | 否 | 刷新/重试 | 否 |  |

### 更新

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E475 / s.f0098a67e2 | 更新包里没有 index.html，已放弃应用 | R/update.rs:257 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） | 否 | 否 | 重试安装 / 手动检查更新 | 否 |  |
| E476 / s.099b3eb863 | 更新地址为空 | R/update.rs:231 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） | 否 | 否 | 重试安装 / 手动检查更新 | 否 |  |
| E477 / s.a6af760282 | 更新包缺少有效的 sha256，已拒绝应用 | R/update.rs:238 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） | 是 | 否 | 重试安装 / 手动检查更新 | 否 |  |
| E478 / s.6462f5c407 | 找不到可替换的界面文件夹，本次安装无法在线更新界面 | R/update.rs:241 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） | 是 | 否 | 重试安装 / 手动检查更新 | 否 |  |
| E479 / s.acc7dfe816 | 下载更新失败：{e} | R/update.rs:247 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） | 否 | 否 | 重试安装 / 手动检查更新 | 是 |  |
| E480 / s.0350fdf3a0 | 解压更新失败：{e} | R/update.rs:251 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） | 否 | 否 | 重试安装 / 手动检查更新 | 是 |  |
| E481 / s.a9fa441818 | 备份旧界面失败：{e} | R/update.rs:264 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） | 否 | 否 | 重试安装 / 手动检查更新 | 是 |  |
| E482 / s.7935e3dd3e | 替换界面失败：{e} | R/update.rs:270 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） | 否 | 否 | 重试安装 / 手动检查更新 | 是 |  |
| E483 / s.ac3a85a9c1 | 检查更新失败：{v0} | UI/lib/updateFlow.ts:121 | UI/pages/SettingsPage.tsx:1177（检查结果）；UI/components/UpdateNudge.tsx:72（安装错误） | 否 | 否 | 重新检查 / 重试更新 | 是 |  |
| E484 / s.bac68ea7db | 更新失败：{v0} | UI/lib/updateFlow.ts:147 | UI/pages/SettingsPage.tsx:1177（检查结果）；UI/components/UpdateNudge.tsx:72（安装错误） | 否 | 否 | 重新检查 / 重试更新 | 是 |  |
| E485 / s.3d1fde4601 | 暂未获取到程序更新包，可先前往发布页手动下载 | UI/lib/updateFlow.ts:87 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（状态） | 否 | 否 | 重试 | 否 |  |
| E486 / s.6a3b354477 | 尚未配置更新签名密钥，请到发布页手动下载新版本 | R/update.rs:476 | UI/components/UpdateNudge.tsx:72（Nudge）；SettingsPage.tsx:1177（状态） | 是 | 是 | 更新弹窗重试 | 否 |  |

### 音频库、试听与语音输出

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E487 / audio.numberTaken | 该编号已被其他音频使用。 | R/audio_library.rs:954；UI/pages/AudioPage.tsx:286（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 否 | none | 否 |  |
| E488 / audio.clipInvalid | 请填写片段名称和有效的起止时间。 | R/audio_library.rs:1013; R/audio_library.rs:1025; R/audio_library.rs:1057; R/audio_library.rs:1075；UI/pages/AudioPage.tsx:287; UI/pages/AudioPage.tsx:384; UI/pages/AudioPage.tsx:404; UI/pages/AudioPage.tsx:417; UI/pages/AudioPage.tsx:435（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 否 | 是 | none | 否 |  |
| E489 / audio.previewDeviceInvalid | 此设备可能用于语音输出，不能用于本地试听。请选择耳机或扬声器。 | R/audio_preview.rs:26；UI/pages/AudioPage.tsx:288（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 是 | none | 否 |  |
| E490 / audio.voiceEngineActive | 变声正在运行。请先停止变声，再播放音频。 | R/audio_voice.rs:392; R/audio_voice.rs:398; R/audio_voice.rs:645; R/audio_voice.rs:662; R/audio_voice.rs:772；UI/pages/AudioPage.tsx:289（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 是 | none | 否 |  |
| E491 / audio.voiceDeviceInvalid | 本地监听设备和输出设备是同一个。请把本地监听设备换成耳机或扬声器。 | R/audio_voice.rs:653；UI/pages/AudioPage.tsx:290（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 是 | none | 否 |  |
| E492 / audio.chooseVoiceDevice | 请先在「设备与音频」里选择输出设备。 | R/audio_voice.rs:607；UI/pages/AudioPage.tsx:291; UI/pages/AudioPage.tsx:450（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 否 | 是 | none | 否 |  |
| E493 / audio.voiceDeviceLocked | 当前语音输出设备正在使用。请先停止音频或变声，再更换设备。 | R/audio_voice.rs:409; R/audio_voice.rs:669; R/audio_voice.rs:684; R/audio_voice.rs:766；UI/pages/AudioPage.tsx:292（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 否 | 是 | none | 否 |  |
| E494 / audio.microphoneBridgeFailed | 音频混音连接已中断。请停止并重新开启变声。 | R/audio_voice.rs:676; R/audio_voice.rs:769；UI/pages/AudioPage.tsx:293（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 是 | none | 否 |  |
| E495 / audio.playbackCapacity | 同时播放的音频已达上限。请先停止一段音频。 | R/audio_bus.rs:55；UI/pages/AudioPage.tsx:294（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 是 | none | 否 |  |
| E496 / audio.playbackCancelled | 已取消这次播放。 | R/audio_bus.rs:59; R/audio_session.rs:157; R/audio_session.rs:176; R/audio_voice.rs:687; R/audio_voice.rs:689; R/audio_voice.rs:750; R/audio_voice.rs:756；UI/pages/AudioPage.tsx:295; UI/pages/AudioPage.tsx:310; UI/pages/AudioPage.tsx:675（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 否 | 否 | none | 否 |  |
| E497 / audio.relinkConflict | 该来源与其他素材或来源共用文件，无法直接重新定位。请先整理重叠来源。 | R/audio_library.rs:642; R/audio_library.rs:682; R/audio_library.rs:707; R/audio_library.rs:784; R/audio_library.rs:805; R/audio_library.rs:649; R/audio_library.rs:702；UI/pages/AudioPage.tsx:296（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 是 | none | 否 |  |
| E498 / audio.relinkOutsideSource | 所选文件不在原来源文件夹内。请重新定位来源文件夹。 | R/audio_library.rs:827；UI/pages/AudioPage.tsx:297（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 是 | none | 否 |  |
| E499 / audio.relinkKindMismatch | 所选路径的类型与来源不符。 | R/audio_library.rs:656; R/audio_library.rs:754；UI/pages/AudioPage.tsx:298（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 否 | none | 否 |  |
| E500 / audio.exportExists | 目标文件已存在，请选择其他文件名。 | R/audio_edit.rs:30; R/audio_edit.rs:120；UI/pages/AudioPage.tsx:299（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 是 | none | 否 |  |
| E501 / audio.toolsMissing | 缺少音频组件。请先下载音频组件。 | R/audio_mix.rs:69；UI/pages/AudioPage.tsx:300（按错误码映射） | UI/pages/AudioPage.tsx:488（alert） | 是 | 是 | AudioToolsDialog 下载组件 | 否 |  |
| E502 / audio.readFailed | 无法读取音频库。请检查音频库文件。 | UI/pages/AudioPage.tsx:119 | UI/pages/AudioPage.tsx:119（状态/alert；集中错误在 :488） | 否 | 是 | none | 否 |  |
| E503 / audio.operationFailed | 操作未能完成。请检查文件或设备后重试。 | UI/pages/AudioPage.tsx:301; UI/pages/AudioPage.tsx:310; UI/pages/AudioPage.tsx:315; UI/pages/AudioPage.tsx:615; UI/pages/AudioPage.tsx:618; UI/pages/AudioPage.tsx:621; UI/pages/AudioPage.tsx:671; UI/pages/AudioPage.tsx:675; UI/pages/AudioPage.tsx:678; UI/pages/AudioPage.tsx:681; UI/pages/AudioPage.tsx:705; UI/pages/AudioPage.tsx:712 | UI/pages/AudioPage.tsx:301; UI/pages/AudioPage.tsx:310; UI/pages/AudioPage.tsx:315; UI/pages/AudioPage.tsx:615; UI/pages/AudioPage.tsx:618; UI/pages/AudioPage.tsx:621; UI/pages/AudioPage.tsx:671; UI/pages/AudioPage.tsx:675; UI/pages/AudioPage.tsx:678; UI/pages/AudioPage.tsx:681; UI/pages/AudioPage.tsx:705; UI/pages/AudioPage.tsx:712（状态/alert；集中错误在 :488） | 否 | 是 | none | 否 |  |
| E504 / audio.numberInvalid | 请输入有效的正整数编号。 | UI/pages/AudioPage.tsx:370 | UI/pages/AudioPage.tsx:370（状态/alert；集中错误在 :488） | 否 | 是 | none | 否 |  |
| E505 / audio.chooseDevice | 请选择本地监听设备。 | UI/pages/AudioPage.tsx:429; UI/pages/AudioPage.tsx:614 | UI/pages/AudioPage.tsx:429; UI/pages/AudioPage.tsx:614（状态/alert；集中错误在 :488） | 否 | 是 | none | 否 |  |
| E506 / audio.missing | 文件不可用 | UI/pages/AudioPage.tsx:544; UI/pages/AudioPage.tsx:568 | UI/pages/AudioPage.tsx:544; UI/pages/AudioPage.tsx:568（状态/alert；集中错误在 :488） | 否 | 否 | none | 否 |  |
| E507 / audio.voicePlaybackFailed | 语音输出已中断。请检查设备后重试。 | UI/pages/AudioPage.tsx:715 | UI/pages/AudioPage.tsx:715（状态/alert；集中错误在 :488） | 是 | 是 | none | 否 |  |
| E508 / neptune.previewFailed | 无法试听此文件。 | UI/pages/AudioPage.tsx:624 | UI/pages/AudioPage.tsx:624（状态/alert；集中错误在 :488） | 否 | 否 | none | 否 |  |
| E509 / neptune.waveformFailed | 波形读取失败，仍可使用下方时间输入。 | UI/pages/AudioPage.tsx:603 | UI/pages/AudioPage.tsx:603（状态/alert；集中错误在 :488） | 否 | 是 | none | 否 |  |

### 全局与音频快捷键

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E510 / audio.hotkeyConflict | 组合键与现有绑定冲突，请换一个组合键。 | R/hotkey_catalog.rs:85; R/lib.rs:417; R/lib.rs:569; R/lib.rs:638；UI/components/AudioHotkeyEditor.tsx:88; UI/pages/SettingsPage.tsx:1274（按错误码映射） | UI/components/AudioHotkeyEditor.tsx:201；UI/pages/SettingsPage.tsx:1418（alert） | 否 | 是 | 重新录制/保存快捷键 | 否 |  |
| E511 / audio.hotkeyTaken | 这个组合键被系统或其他软件占用，已保留原组合。 | R/lib.rs:597; R/lib.rs:658；UI/components/AudioHotkeyEditor.tsx:89; UI/pages/SettingsPage.tsx:1275（按错误码映射） | UI/components/AudioHotkeyEditor.tsx:201；UI/pages/SettingsPage.tsx:1418（alert） | 是 | 否 | 重新录制/保存快捷键 | 否 |  |
| E512 / audio.hotkeySaveFailed | 未能保存快捷键。请检查组合键或设备占用情况。 | UI/components/AudioHotkeyEditor.tsx:89; UI/pages/SettingsPage.tsx:1275 | UI/components/AudioHotkeyEditor.tsx:89; UI/pages/SettingsPage.tsx:1275（alert/状态标签） | 否 | 是 | 重新录制/保存快捷键 | 否 |  |
| E513 / audio.hotkeySuspendFailed | 无法安全录制快捷键。请重试。 | UI/components/AudioHotkeyEditor.tsx:133; UI/pages/SettingsPage.tsx:1417 | UI/components/AudioHotkeyEditor.tsx:133; UI/pages/SettingsPage.tsx:1417（alert/状态标签） | 否 | 是 | 重新录制/保存快捷键 | 否 |  |
| E514 / audio.hotkeyConflictStatus | 冲突 | UI/components/AudioHotkeyEditor.tsx:193; UI/pages/SettingsPage.tsx:1284 | UI/components/AudioHotkeyEditor.tsx:193; UI/pages/SettingsPage.tsx:1284（alert/状态标签） | 否 | 否 | 重新录制/保存快捷键 | 否 |  |

### 社区账户与投稿

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E515 / publication.signInRequired | 请登录图灵镜账号后继续。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:342（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 否 | 是 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E516 / publication.readAgain | 请重新读取来源并确认文件。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:343（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 否 | 是 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E517 / publication.sourceChanged | 来源已变更。请重新读取并确认选择。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:344（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 是 | 是 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E518 / publication.coverError | 无法打开这张图片。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:345（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 否 | 否 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E519 / publication.unchangedPackage | 当前版本已使用此 ZIP。请选择更新后的 ZIP。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:346（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 是 | 是 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E520 / publication.unchangedVersion | 请填写与当前版本不同的版本号。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:347（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 否 | 是 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E521 / publication.hashMismatch | 文件与 SHA-256 校验值不一致。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:348（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 是 | 否 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E522 / publication.rateLimited | 来源繁忙，请稍后重试。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:349（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 是 | 是 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E523 / publication.retryQueued | 可以重试。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:349（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 否 | 否 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E524 / publication.publicSource | 请使用模搭、Hugging Face、GitHub Releases 或 CNB 的公开链接。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:350（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 否 | 是 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E525 / publication.requestFailed | 暂时无法完成操作，请重试。 | R/community_publish.rs:209、236、254；UI/lib/communityPublication.ts:351（API code 映射；远端原因不直接展示） | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） | 否 | 是 | 详情/列表有重试；投稿保留读取来源/提交按钮 | 否 |  |
| E526 / community.signInFailed | 登录失败，请重试。 | R/community_account.rs:139、186、248、266、528；UI/components/CommunityActions.tsx:53 | UI/components/CommunityActions.tsx:53、87 → trm-ui tip（toast） | 否 | 是 | 登录/退出/链接入口 | 否 |  |
| E527 / community.signOutFailed | 退出登录失败，请重试。 | R/community_account.rs:139、186、248、266、528；UI/components/CommunityActions.tsx:53 | UI/components/CommunityActions.tsx:53、87 → trm-ui tip（toast） | 否 | 是 | 登录/退出/链接入口 | 否 |  |
| E528 / community.linkFailed | 无法打开链接。 | R/community_account.rs:139、186、248、266、528；UI/components/CommunityActions.tsx:87 | UI/components/CommunityActions.tsx:53、87 → trm-ui tip（toast） | 否 | 否 | 登录/退出/链接入口 | 否 |  |
| E529 / dynamic.publication.reason | 【无 app zh-CN 条目】动态：服务端审核 reason 原文 | R/community_publish.rs:223; UI/components/CommunitySubmissionDetail.tsx:51 | UI/components/CommunitySubmissionDetail.tsx:51（审核记录正文） | 否 | 否 | 修改投稿 | 否 | 非 app 语言包；属于审核理由，不是异常/stderr/退出码。 |

### 社区投稿：本地校验与文件操作

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E530 / publication.copyFailed | 未能复制 SHA-256。 | UI/components/CommunityModelDetail.tsx:71 | UI/components/CommunityModelDetail.tsx:71（tip toast） | 否 | 否 | none | 否 |  |
| E531 / publication.authorProfileSaveFailed | 暂时无法保存作者主页，请重试。 | UI/components/CommunityAuthorProfileActions.tsx:86 | UI/components/CommunityAuthorProfileActions.tsx:86（Warn / toast / 行内校验；批量错误在 CommunityBatchPublisher.tsx:385） | 否 | 是 | 保存作者主页 | 否 |  |
| E532 / publication.noMatches | 没有 ZIP 与来源匹配。 | UI/components/CommunityBatchPublisher.tsx:172 | UI/components/CommunityBatchPublisher.tsx:272（Warn） | 否 | 否 | none | 否 |  |
| E533 / publication.packReadError | 无法读取或导出模型包。 | UI/components/CommunityBatchPublisher.tsx:174; UI/components/ExportVoicePackages.tsx:60 | UI/components/CommunityBatchPublisher.tsx:272（Warn）；UI/components/ExportVoicePackages.tsx:71（Warn） | 否 | 否 | 重试导出失败项 | 否 |  |
| E534 / publication.packFailed | 无法导出 {v0}。 | UI/components/ExportVoicePackages.tsx:80 | UI/components/ExportVoicePackages.tsx:80（条目标题） | 否 | 否 | 重试导出失败项 | 否 |  |
| E535 / publication.coverError | 无法打开这张图片。 | UI/components/CommunityCover.tsx:56 | UI/components/CommunityCover.tsx:56（Warn / toast / 行内校验；批量错误在 CommunityBatchPublisher.tsx:385） | 否 | 否 | none | 否 |  |
| E536 / publication.saveFailed | 无法在本机保存草稿。 | UI/components/CommunityBatchPublisher.tsx:77; UI/components/CommunityBatchPublisher.tsx:184; UI/pages/PlazaPage.tsx:84 | UI/components/CommunityBatchPublisher.tsx:272（Warn）；UI/pages/PlazaPage.tsx:84（toast） | 否 | 否 | 保存草稿 | 否 |  |
| E537 / publication.noFiles | 没有符合条件的 ZIP 文件。 | UI/components/CommunityBatchPublisher.tsx:305; UI/components/CommunityPublisher.tsx:231; UI/pages/PlazaPage.tsx:120 | UI/components/CommunityBatchPublisher.tsx:305; UI/components/CommunityPublisher.tsx:231; UI/pages/PlazaPage.tsx:120（Warn / toast / 行内校验；批量错误在 CommunityBatchPublisher.tsx:385） | 是 | 否 | none | 否 |  |
| E538 / publication.hashMismatch | 文件与 SHA-256 校验值不一致。 | UI/components/CommunityBatchPublisher.tsx:159 | UI/components/CommunityBatchPublisher.tsx:272（Warn） | 是 | 否 | none | 否 |  |
| E539 / publication.unchangedPackage | 当前版本已使用此 ZIP。请选择更新后的 ZIP。 | UI/components/CommunityPublisher.tsx:243 | UI/components/CommunityPublisher.tsx:243（Warn / toast / 行内校验；批量错误在 CommunityBatchPublisher.tsx:385） | 是 | 是 | none | 否 |  |
| E540 / publication.unchangedVersion | 请填写与当前版本不同的版本号。 | UI/components/CommunityPublisher.tsx:270 | UI/components/CommunityPublisher.tsx:270（Warn / toast / 行内校验；批量错误在 CommunityBatchPublisher.tsx:385） | 否 | 是 | none | 否 |  |
| E541 / publication.rejected | 需修改 | UI/components/CommunitySubmissionDetail.tsx:20; UI/components/CommunitySubmissionDetail.tsx:46; UI/components/CommunitySubmissions.tsx:124 | UI/components/CommunitySubmissionDetail.tsx:20; UI/components/CommunitySubmissionDetail.tsx:46; UI/components/CommunitySubmissions.tsx:124（Warn / toast / 行内校验；批量错误在 CommunityBatchPublisher.tsx:385） | 否 | 否 | none | 否 |  |
| E542 / raw.pack.export | 【无 app zh-CN 条目】动态：每个导出包的文件、ZIP、JSON 错误 | R/publication_packs.rs:30、44、129、130、133、152、154; R/voices.rs:2248、2268、2272、2273、2275、2276、2279、2280、2281、2283、2284 | UI/components/ExportVoicePackages.tsx:81（逐条正文） | 否 | 否 | 重试失败项 | 是 |  |
| E543 / literal.pack.path | 【无 app zh-CN 条目】Invalid package path. | R/publication_packs.rs:135 | UI/components/ExportVoicePackages.tsx:81（逐条正文） | 是 | 否 | 重试失败项 | 否 |  |
| E544 / literal.pack.weight | 【无 app zh-CN 条目】An RVC voice package needs one weight. | R/publication_packs.rs:142 | UI/components/ExportVoicePackages.tsx:81（逐条正文） | 是 | 否 | 重试失败项 | 否 |  |
| E545 / literal.pack.metadata | 【无 app zh-CN 条目】Package metadata is too large. | R/publication_packs.rs:153 | UI/components/ExportVoicePackages.tsx:81（逐条正文） | 是 | 否 | 重试失败项 | 否 |  |

### 移动端连接

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E546 / mobile.failed | 操作失败，请重试。 | R/mobile.rs:106、131、142、555、588（原生错误）；UI/hooks/useMobile.ts:36；UI/components/MobileSection.tsx:51、85、112（固定兜底） | UI/components/MobileSection.tsx:112（alert） | 否 | 是 | 刷新设备、重新配对、再次执行设备动作 | 否 |  |

### 自检、诊断与咨询包

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E547 / s.chkWorkerKilled | 本次运行中，引擎进程被系统终止过 | R/selfcheck.rs:108 | UI/components/FindingList.tsx:79（结论）；:89（证据）；调用点 MorePage.tsx:476、DiagnosticsDialog.tsx:313 | 是 | 否 | 查看说明 faq（FindingList.tsx:39–60） | 否 |  |
| E548 / s.chkSnapshotModel | 当前所选模型文件疑似训练检查点（以 G_ 或 D_ 开头），无法直接用于语音转换<br>{name} | R/selfcheck.rs:142 | UI/components/FindingList.tsx:79（结论）；:89（证据）；调用点 MorePage.tsx:476、DiagnosticsDialog.tsx:313 | 是 | 否 | 查看训练说明（FindingList.tsx:39–60） | 否 |  |
| E549 / s.chkStageMismatch | 实验「{a0}」的产物不完整：切片 {a1}、音高 {a2}、特征 {a3} | R/selfcheck.rs:224 | UI/components/FindingList.tsx:79（结论）；:89（证据）；调用点 MorePage.tsx:476、DiagnosticsDialog.tsx:313 | 是 | 否 | 查看训练说明（FindingList.tsx:39–60） | 否 |  |
| E550 / s.chkPreprocessFail | 实验「{a0}」预处理有 {a1} 个文件读取失败 | R/selfcheck.rs:251 | UI/components/FindingList.tsx:79（结论）；:89（证据）；调用点 MorePage.tsx:476、DiagnosticsDialog.tsx:313 | 是 | 否 | 查看训练说明（FindingList.tsx:39–60） | 否 |  |
| E551 / s.chkOom | 实验「{}」的训练日志末尾是显存不足 | R/selfcheck.rs:261 | UI/components/FindingList.tsx:79（结论）；:89（证据）；调用点 MorePage.tsx:476、DiagnosticsDialog.tsx:313 | 是 | 否 | 查看显存说明（FindingList.tsx:39–60） | 否 |  |
| E552 / s.chkPretrainedPartial | 底模缺 {}，可选采样率受限 | R/selfcheck.rs:294 | UI/components/FindingList.tsx:79（结论）；:89（证据）；调用点 MorePage.tsx:476、DiagnosticsDialog.tsx:313 | 是 | 否 | 下载训练底模（FindingList.tsx:39–60） | 否 |  |
| E553 / s.chkDiskLow | 产品所在磁盘只剩 {} GB | R/selfcheck.rs:314 | UI/components/FindingList.tsx:79（结论）；:89（证据）；调用点 MorePage.tsx:476、DiagnosticsDialog.tsx:313 | 是 | 否 | none（FindingList.tsx:39–60） | 否 |  |
| E554 / s.chkMmeDelay | 音频接口是 MME，实测延迟 {} 毫秒 | R/selfcheck.rs:347 | UI/components/FindingList.tsx:79（结论）；:89（证据）；调用点 MorePage.tsx:476、DiagnosticsDialog.tsx:313 | 是 | 否 | 查看延迟说明（FindingList.tsx:39–60） | 否 |  |
| E555 / s.chkUnderrun | 累计欠载 {} 次，声音会有卡顿 | R/selfcheck.rs:359 | UI/components/FindingList.tsx:79（结论）；:89（证据）；调用点 MorePage.tsx:476、DiagnosticsDialog.tsx:313 | 是 | 否 | 查看卡顿说明（FindingList.tsx:39–60） | 否 |  |
| E556 / raw.linkcheck.invoke | 【无 app zh-CN 条目】动态：diagnostics_link_check 拒绝的 String(e) | UI/components/LinkCheckDialog.tsx:66（diagnostics_link_check 拒绝值） | UI/components/LinkCheckDialog.tsx:323（错误正文） | 否 | 否 | 重新检查 | 是 |  |

### 设备链路自检

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E557 / s.lcRuntimeBad | 尚未补全，变声功能不可用 | UI/components/LinkCheckDialog.tsx:159 | UI/components/LinkCheckDialog.tsx:347（检查结果正文） | 是 | 否 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E558 / s.lcCableBad | 未安装，游戏和语音软件无法收到变声 | UI/components/LinkCheckDialog.tsx:168 | UI/components/LinkCheckDialog.tsx:347（检查结果正文） | 是 | 否 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E559 / s.lcOutputNone | 未设置，请在「设置 → 设备与音频」中选择输出设备 | UI/components/LinkCheckDialog.tsx:178 | UI/components/LinkCheckDialog.tsx:347（检查结果正文） | 是 | 是 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E560 / s.lcOutputReversed | 当前选择为 CABLE Output，应选择 CABLE Input | UI/components/LinkCheckDialog.tsx:187 | UI/components/LinkCheckDialog.tsx:347（检查结果正文） | 是 | 是 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E561 / s.lcOutputPhysical | 当前：{v0}（非虚拟声卡时，游戏侧将收不到变声） | UI/components/LinkCheckDialog.tsx:203 | UI/components/LinkCheckDialog.tsx:347（检查结果正文） | 是 | 否 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E562 / s.lcInputNone | 未设置，请在「设置 → 设备与音频」中选择麦克风 | UI/components/LinkCheckDialog.tsx:214 | UI/components/LinkCheckDialog.tsx:347（检查结果正文） | 是 | 是 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E563 / s.lcInputWrong | 当前选择为 {v0}，这是虚拟声卡，不是你的麦克风 | UI/components/LinkCheckDialog.tsx:223 | UI/components/LinkCheckDialog.tsx:347（检查结果正文） | 是 | 否 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E564 / s.lcDefaultUnknown | 引擎未启动或设备列表未读取，暂时无法判断 | UI/components/LinkCheckDialog.tsx:241 | UI/components/LinkCheckDialog.tsx:347（检查结果正文） | 是 | 否 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E565 / s.lcDefaultCable | 当前为 {v0}，系统其他声音将无法正常播放，建议改回耳机或音箱 | UI/components/LinkCheckDialog.tsx:250 | UI/components/LinkCheckDialog.tsx:347（检查结果正文） | 否 | 是 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E566 / s.lcMicSilent | 未检测到输入，请检查麦克风连接与选择 | UI/components/LinkCheckDialog.tsx:144 | UI/components/LinkCheckDialog.tsx:391（麦克风结果） | 是 | 是 | 对应帮助段 / 打开系统声音设置 / 麦克风测试 | 否 |  |
| E567 / s.lcBad | 异常 | UI/components/LinkCheckDialog.tsx:274; UI/components/LinkCheckDialog.tsx:282; UI/components/LinkCheckDialog.tsx:303; UI/components/LinkCheckDialog.tsx:368 | UI/components/LinkCheckDialog.tsx:339、368（异常状态标签） | 否 | 否 | 各检查项修复按钮 | 否 |  |

### 维护、存储与诊断提示

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E568 / s.storageScanFailed | 存储信息刷新失败，请重新统计。 | UI/components/StorageSection.tsx:182 | UI/components/StorageSection.tsx:182（状态/错误正文） | 否 | 是 | 重新统计 | 否 |  |
| E569 / s.selfCheckFailed | 检查未能完成，请稍后重试。 | UI/pages/MorePage.tsx:455 | UI/pages/MorePage.tsx:455（状态/错误正文） | 否 | 是 | 重新检查 | 否 |  |
| E570 / s.sumCopyFailed | 复制失败，请重试。 | UI/pages/ModelsPage.tsx:1109; UI/pages/MorePage.tsx:175 | UI/pages/MorePage.tsx:448（ListItem desc）；UI/pages/ModelsPage.tsx:1109→527（toast） | 否 | 是 | 再次复制 | 否 |  |
| E571 / s.7fae0289b6 | 生成诊断包失败：{v0} | UI/pages/MorePage.tsx:198 | UI/pages/MorePage.tsx:483（ListItem desc） | 否 | 否 | 生成诊断包 | 是 |  |
| E572 / s.diagShotUnreadable | 「{}」无法读取为图片，未添加。 | UI/components/DiagnosticsDialog.tsx:127 | UI/components/DiagnosticsDialog.tsx:285（截图选择状态正文） | 否 | 否 | 重新添加截图 | 否 |  |
| E573 / s.diagShotsFull | 已达到 6 张上限，未添加更多图片。 | UI/components/DiagnosticsDialog.tsx:128 | UI/components/DiagnosticsDialog.tsx:285（截图选择状态正文） | 是 | 否 | 重新添加截图 | 否 |  |
| E574 / s.valueFailed | 读取失败 | UI/pages/MorePage.tsx:75 | UI/pages/MorePage.tsx:311、321（软件版本/安装位置字段） | 否 | 否 | none | 否 |  |
| E575 / raw.storage.clean | 【无 app zh-CN 条目】动态：unknown storage kind: {bad}；异步任务/IPC 失败。实际删除失败仅记录日志。 | R/lib.rs:738、746、972、977; R/paths.rs:628; R/train.rs:593 | UI/components/StorageSection.tsx:249（正文） | 否 | 否 | 重新统计；清理 | 是 |  |

### 性能测试与诊断包

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E576 / s.f9e62f8c38 | 性能测试已结束，但未生成报告文件。 | R/shell_extras.rs:699 | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） | 否 | 否 | 重新生成诊断包 | 否 |  |
| E577 / s.c8c05e7db7 | 运行环境未就绪，无法运行性能测试 | R/shell_extras.rs:563 | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） | 是 | 否 | 重新生成诊断包 | 否 |  |
| E578 / s.c41c6ca117 | 找不到 benchmark_realtime.py | R/shell_extras.rs:566 | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） | 是 | 否 | 重新生成诊断包 | 否 |  |
| E579 / s.40019094c0 | 没有可用的音色模型，请先在首页选择一个音色，再运行性能测试 | R/shell_extras.rs:587 | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） | 是 | 是 | 重新生成诊断包 | 否 |  |
| E580 / s.84256012c6 | 性能测试启动失败：{e} | R/shell_extras.rs:691 | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） | 否 | 否 | 重新生成诊断包 | 是 |  |
| E581 / s.470a002848 | 性能测试失败（退出码 {a0}），详见 User_Data/logs/perf_bench.log | R/shell_extras.rs:694 | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） | 否 | 否 | 重新生成诊断包 | 是 |  |
| E582 / raw.diagnostics.pack | 【无 app zh-CN 条目】动态：文件创建/ZIP 打包/图片读取错误（外包 s.7fae0289b6） | R/shell_extras.rs:876、877、1350、1354、1438、1439、1450 | UI/pages/MorePage.tsx:483（ListItem 描述） | 否 | 否 | 生成诊断包；打开日志目录 | 是 |  |
| E583 / s.eea9655c7b | 性能测试未完成：{e} | R/shell_extras.rs:1342 | UI/pages/MorePage.tsx:483（生成诊断包结果中的 perf_note） | 是 | 否 | 生成诊断包；打开日志目录 | 是 |  |

### 原版实时面板与 WebUI：启动

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E584 / s.4f09ae24cf | 运行环境未就绪，请先在首次运行向导中补全运行环境 | R/legacy.rs:29 | UI/pages/MorePage.tsx:505、512（ListItem 描述） | 是 | 是 | 重新打开；打开日志目录 | 否 |  |
| E585 / s.f1f3d2302b | 启动失败：{e} | R/legacy.rs:76 | UI/pages/MorePage.tsx:505、512（ListItem 描述） | 否 | 否 | 重新打开；打开日志目录 | 是 |  |
| E586 / s.0c5475c6d8 | 找不到实时面板脚本：{a0} | R/legacy.rs:88 | UI/pages/MorePage.tsx:505、512（ListItem 描述） | 是 | 否 | 重新打开；打开日志目录 | 否 |  |
| E587 / s.fb5c249625 | 找不到 WebUI 脚本：{a0} | R/legacy.rs:116 | UI/pages/MorePage.tsx:505、512（ListItem 描述） | 是 | 否 | 重新打开；打开日志目录 | 否 |  |
| E588 / s.ea582ad463 | 启动失败：{v0} | UI/pages/MorePage.tsx:136 | UI/pages/MorePage.tsx:505、512（ListItem 描述） | 否 | 否 | 重新打开；打开日志目录 | 是 |  |

### 界面启动与渲染

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E589 / s.61f43bf584 | 界面出错了 | UI/components/ErrorBoundary.tsx:63 | UI/components/ErrorBoundary.tsx:63、64（整页错误提示） | 否 | 否 | 生成诊断包；关闭（详情默认展开） | 否 |  |
| E590 / s.d851b62cf4 | 后台变声不受影响，可从系统托盘右键菜单继续控制。请将「其他 → 维护」生成的诊断包发给我们，以便排查。本页也可直接生成。 | UI/components/ErrorBoundary.tsx:64 | UI/components/ErrorBoundary.tsx:63、64（整页错误提示） | 否 | 是 | 生成诊断包；关闭（详情默认展开） | 否 |  |
| E591 / raw.ui.render | 【无 app zh-CN 条目】动态：JavaScript error.stack / componentStack / String(error) | UI/components/ErrorBoundary.tsx:38 | UI/components/ErrorBoundary.tsx:97（整页 pre，默认展开） | 否 | 否 | 生成诊断包；关闭 | 是 |  |
| E592 / literal.boot.resource | 【无 app zh-CN 条目】界面资源载入失败<br>{URL} 未能载入 | app/index.html:101 | app/index.html:87、91（启动页标题 + 展开详情） | 否 | 否 | none | 否 |  |
| E593 / literal.boot.script | 【无 app zh-CN 条目】界面脚本出错<br>{e.message &#124;&#124; "unknown"}<br>{filename}:{lineno}<br>{stack} | app/index.html:105 | app/index.html:87、91（启动页标题 + 展开详情） | 否 | 否 | none | 是 |  |
| E594 / literal.boot.rejection | 【无 app zh-CN 条目】界面出错<br>{reason.message + stack 或 String(reason)} | app/index.html:122 | app/index.html:87、91（启动页标题 + 展开详情） | 否 | 否 | none | 是 |  |
| E595 / literal.boot.timeout | 【无 app zh-CN 条目】界面加载超时<br>8 秒内界面没有挂载；脚本没有报错。 | app/index.html:135 | app/index.html:87、91（启动页标题 + 详情） | 否 | 否 | none | 否 |  |
| E596 / literal.boot.help | 【无 app zh-CN 条目】界面没能载入。请把 User_Data\logs\shell.log 发给我们。 | app/index.html:89 | app/index.html:88（启动页帮助正文） | 否 | 是 | none | 否 |  |

### 已知问题与设备断开

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E597 / s.kiAsioCrashTitle | 读取音频设备列表时出错 | app/src-tauri/known_issues.json:4; R/known_issues.rs:157、158 | UI/App.tsx:1498（Nudge 标题）；UI/components/FindingList.tsx:79（结论标题） | 否 | 否 | 关闭；仅 fixed_in 非空时更新（当前表为空） | 否 |  |
| E598 / s.kiAsioCrashBody | 读取音频设备列表时进程异常退出。仅凭已安装的驱动无法确定原因，可尝试「设备与音频」设置中的兼容模式。 | app/src-tauri/known_issues.json:4; R/known_issues.rs:157、158 | UI/App.tsx:1521（Nudge 正文） | 是 | 是 | 关闭；仅 fixed_in 非空时更新（当前表为空） | 否 |  |
| E599 / s.unplug.title | 设备已断开 | UI/App.tsx:1534 | UI/App.tsx:1534、1542（Nudge） | 是 | 否 | 关闭；选择设备；设备恢复且此前运行时继续变声 | 否 |  |
| E600 / s.unplug.bodyRunning | {device}「{name}」已断开，变声已暂停。重新插好后可以直接继续，也可以改用其他设备。 | UI/App.tsx:1542 | UI/App.tsx:1534、1542（Nudge） | 是 | 否 | 关闭；选择设备；设备恢复且此前运行时继续变声 | 否 |  |
| E601 / s.unplug.bodyIdle | {device}「{name}」已断开。开启变声前请重新插好，或改用其他设备。 | UI/App.tsx:1542 | UI/App.tsx:1534、1542（Nudge） | 是 | 是 | 关闭；选择设备；设备恢复且此前运行时继续变声 | 否 |  |
| E602 / s.kiNoUpdateYet | 当前已是最新版本。此问题的修复尚未发布，将在下一个版本中提供。 | UI/App.tsx:305 | UI/App.tsx:1522（已知问题 Nudge 的更新反馈） | 否 | 否 | 关闭 | 否 |  |

### 语音转换：自动降级

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E603 / msg.sts.degraded | 当前设置无法完成这次转换（{why}），已自动改用「{rung}」继续，速度会慢一些。 | tools/sts_core.py:770 | UI/components/TtsPanel.tsx:2205（进度正文） | 否 | 否 | none | 否 |  |
| E604 / msg.sts.hot_dml_fallback | 显卡无法完成这次处理，改用独立进程转换，速度可能降低。 | gui_v1.py:4178 | UI/components/TtsPanel.tsx:2205（进度正文） | 否 | 否 | none | 否 |  |
| E605 / neptune.fallbackOom | 显卡内存不足 | R/i18n.rs:408 | UI/components/TtsPanel.tsx:2205（msg.sts.degraded 的 why） | 是 | 否 | none | 否 |  |
| E606 / neptune.fallbackBackend | 显卡不支持此操作 | R/i18n.rs:409 | UI/components/TtsPanel.tsx:2205（msg.sts.degraded 的 why） | 是 | 否 | none | 否 |  |

### 语音转换：录音 worker 原文

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E607 / record.nopath | 【无 app zh-CN 条目】缺少输出路径 | tools/record_worker.py:231 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E608 / record.notfound | 【无 app zh-CN 条目】找不到输入设备：{device_name} | tools/record_worker.py:251 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E609 / record.silent.read | 【无 app zh-CN 条目】没有读到任何输入 | tools/record_worker.py:325 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E610 / record.silent.record | 【无 app zh-CN 条目】没有录到声音 | tools/record_worker.py:336 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E611 / record.usage | 【无 app zh-CN 条目】缺请求文件参数 | tools/record_worker.py:346 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录 | 否 |  |
| E612 / record.busy | 【无 app zh-CN 条目】打不开麦克风。常见原因：实时变声正在用这块设备（尤其开了 WASAPI 独占），或别的软件占着输入。请先在主界面停止变声后再试。 | tools/record_worker.py:210 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 是 | 是 | 复制完整错误；打开日志目录 | 否 |  |
| E613 / record.nolib | 【无 app zh-CN 条目】录音组件不可用：{e} | tools/record_worker.py:241 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |
| E614 / record.enum | 【无 app zh-CN 条目】枚举输入设备失败：{e} | tools/record_worker.py:247 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |
| E615 / record.open | 【无 app zh-CN 条目】动态：str(exc) or type(exc).__name__ | tools/record_worker.py:213 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |
| E616 / record.request | 【无 app zh-CN 条目】请求文件读不了：{e} | tools/record_worker.py:351 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |
| E617 / record.unhandled | 【无 app zh-CN 条目】动态：str(e) | tools/record_worker.py:363 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） | 否 | 否 | 复制完整错误；打开日志目录 | 是 |  |

### 封面裁剪

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E618 / raw.cover.io | 【无 app zh-CN 条目】动态：本地读取/远程请求/图片保存错误 | R/voices.rs:2405、2410、2414、2446、2504; UI/components/CropCoverDialog.tsx:20 | app/node_modules/trm-ui/lib/index.js:6425（ImageCropDialog alert）；社区首次打开失败另映射 publication.coverError | 否 | 否 | 重新选择图片；保存 | 是 |  |
| E619 / ui.crop.badImage | 【无 app zh-CN 条目】图片数据无效，保存失败 | app/node_modules/trm-ui/lib/index.js:5978、6311、6316 | app/node_modules/trm-ui/lib/index.js:6425（alert） | 是 | 否 | 重新选择图片；保存 | 否 | 不在 app 的 zh-CN.json；来自已安装 trm-ui 内置 zh。 |

### 原版实时面板与 WebUI：原版实时面板

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E620 / legacy.auto_start | 【无 app zh-CN 条目】自动开始音频转换失败<br><br>{type(e).__name__}: {e}<br><br>请检查输入/输出设备，或手动点「开始音频转换」。 | gui_v1.py:864 | gui_v1.py:864（PySimpleGUI popup_error） | 否 | 是 | 关闭 | 是 |  |
| E621 / legacy.start | 【无 app zh-CN 条目】启动音频转换失败<br><br>{type(e).__name__}: {e}<br><br>常见原因：模型路径无效、显存不足、声卡占用、index 损坏。无 index 文件时可把 Index Rate 设为 0。 | gui_v1.py:913 | gui_v1.py:913（PySimpleGUI popup_error） | 是 | 是 | 关闭 | 是 |  |
| E622 / legacy.check.dsp | 【无 app zh-CN 条目】请先选用一个 DSP 预设 | gui_v1.py:1103 | gui_v1.py:1046（popup）；worker 模式同时至 Dock.tsx:217 | 是 | 是 | 关闭 | 否 |  |
| E623 / legacy.check.voice | 【无 app zh-CN 条目】请选择音色，或先选用一个 DSP 预设 | gui_v1.py:1111 | gui_v1.py:1046（popup）；worker 模式同时至 Dock.tsx:217 | 是 | 是 | 关闭 | 否 |  |
| E624 / legacy.check.core | 【无 app zh-CN 条目】实时变声需要引擎资源。请到广场下载模型，或先选用一个 DSP 预设。 | gui_v1.py:1118 | gui_v1.py:1046（popup）；worker 模式同时至 Dock.tsx:217 | 是 | 是 | 关闭 | 否 |  |
| E625 / legacy.check.pth | 【无 app zh-CN 条目】pth文件不存在<br>{path} | gui_v1.py:1162 | gui_v1.py:1046（popup）；worker 模式同时至 Dock.tsx:217 | 是 | 否 | 关闭 | 否 |  |
| E626 / legacy.check.device | 【无 app zh-CN 条目】设备无效: {e} | gui_v1.py:1169 | gui_v1.py:1046（popup）；worker 模式同时至 Dock.tsx:217 | 否 | 否 | 关闭 | 是 |  |

### 原版实时面板与 WebUI：推理

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E627 / legacy.vc.no_input | 【无 app zh-CN 条目】You need to upload an audio | infer/modules/vc/modules.py:168 | infer-web.py:954（vc_output1 文本框） | 是 | 否 | 重新选择音频 | 否 |  |
| E628 / legacy.vc.traceback | 【无 app zh-CN 条目】动态：vc_single 完整 traceback | infer/modules/vc/modules.py:245、247 | infer-web.py:954（vc_output1 文本框） | 否 | 否 | none | 是 |  |
| E629 / legacy.vc.batch_traceback | 【无 app zh-CN 条目】动态：逐文件结果中的完整 traceback / 外层 traceback | infer/modules/vc/modules.py:321、326 | infer-web.py:1094（vc_output3 文本框） | 否 | 否 | none | 是 |  |

### 原版实时面板与 WebUI：训练

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E630 / legacy.train.preprocess | 【无 app zh-CN 条目】动态：preprocess.log 全文含 traceback | infer-web.py:251、258; infer/modules/train/preprocess.py:119、145 | infer-web.py:1179（info1 文本框） | 否 | 否 | none | 是 |  |
| E631 / legacy.train.feature | 【无 app zh-CN 条目】动态：extract_f0_feature.log 全文 | infer-web.py:343、350、392、399 | infer-web.py:1223（info2 文本框） | 否 | 否 | none | 是 |  |
| E632 / legacy.train.index | 【无 app zh-CN 条目】动态：聚类异常 traceback，追加至 infos 并 yield | infer-web.py:662、665 | infer-web.py:1328（info3 文本框） | 否 | 否 | none | 是 |  |

### 原版实时面板与 WebUI：模型工具

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E633 / legacy.ckpt.traceback | 【无 app zh-CN 条目】动态：融合/信息修改/查看/提取的 traceback 返回值 | infer/lib/train/process_ckpt.py:77、207、219、277 | infer-web.py:1427、1465、1481、1523（info4/5/6/7 文本框） | 否 | 否 | none | 是 |  |
| E634 / legacy.ckpt.architecture | 【无 app zh-CN 条目】Fail to merge the models. The model architectures are not the same. | infer/lib/train/process_ckpt.py:247 | infer-web.py:1427（info4 文本框） | 是 | 否 | none | 否 |  |

### 原版实时面板与 WebUI：说明文档

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E635 / legacy.faq.load | 【无 app zh-CN 条目】动态：FAQ Markdown 文件读取失败的 traceback | infer-web.py:1562 | infer-web.py:1562（gr.Markdown） | 否 | 否 | none | 是 |  |

### Windows 安装器

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E636 / nsis.appRunning | 【无 app zh-CN 条目】{{product_name}} 正在运行！请关闭后再试。 | app/src-tauri/nsis-languages/SimpChinese.nsh:4 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:4 | 是 | 是 | 模板控制（本仓库未保存模板源码） | 否 | 不在 app zh-CN.json；这里逐字记录仓库 NSIS 简体中文语言文件。 |
| E637 / nsis.failedToKillApp | 【无 app zh-CN 条目】无法终止 {{product_name}}。请关闭后再试。 | app/src-tauri/nsis-languages/SimpChinese.nsh:11 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:11 | 否 | 是 | 模板控制（本仓库未保存模板源码） | 否 | 不在 app zh-CN.json；这里逐字记录仓库 NSIS 简体中文语言文件。 |
| E638 / nsis.silentDowngrades | 【无 app zh-CN 条目】降级操作在此安装程序上已禁用，无法进行安静安装，请使用图形操作界面。$\n | app/src-tauri/nsis-languages/SimpChinese.nsh:16 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:16 | 是 | 是 | 模板控制（本仓库未保存模板源码） | 否 | 不在 app zh-CN.json；这里逐字记录仓库 NSIS 简体中文语言文件。 |
| E639 / nsis.unableToUninstall | 【无 app zh-CN 条目】无法卸载！ | app/src-tauri/nsis-languages/SimpChinese.nsh:17 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:17 | 否 | 否 | 模板控制（本仓库未保存模板源码） | 否 | 不在 app zh-CN.json；这里逐字记录仓库 NSIS 简体中文语言文件。 |
| E640 / nsis.webview2AbortError | 【无 app zh-CN 条目】无法安装 WebView2！没有它，此应用就无法运行。尝试重启安装程序。 | app/src-tauri/nsis-languages/SimpChinese.nsh:21 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:21 | 否 | 是 | 模板控制（本仓库未保存模板源码） | 否 | 不在 app zh-CN.json；这里逐字记录仓库 NSIS 简体中文语言文件。 |
| E641 / nsis.webview2DownloadError | 【无 app zh-CN 条目】错误：无法下载 WebView2 - $0 | app/src-tauri/nsis-languages/SimpChinese.nsh:22 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:22 | 否 | 否 | 模板控制（本仓库未保存模板源码） | 是 | 不在 app zh-CN.json；这里逐字记录仓库 NSIS 简体中文语言文件。 |
| E642 / nsis.webview2InstallError | 【无 app zh-CN 条目】错误：安装 WebView2 时失败，错误代码：$1 | app/src-tauri/nsis-languages/SimpChinese.nsh:25 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:25 | 否 | 否 | 模板控制（本仓库未保存模板源码） | 是 | 不在 app zh-CN.json；这里逐字记录仓库 NSIS 简体中文语言文件。 |
| E643 / nsis.non_ascii | 【无 app zh-CN 条目】安装路径里有中文或其他非英文字符。$\r$\n$\r$\n音色检索等功能在这种路径下无法使用。$\r$\n请改到纯英文路径，例如 D:\RVCFabric。$\r$\n$\r$\n仍要安装到这里吗？ | app/src-tauri/installer-hooks.nsh:49 | app/src-tauri/installer-hooks.nsh:49（MessageBox） | 是 | 是 | 是：继续；否：返回 | 否 |  |
| E644 / nsis.move_failed | 【无 app zh-CN 条目】搬移没有完成：$\r$\n$R3$\r$\n$\r$\n原位置的软件和数据都没有改动，本次安装已取消。 | app/src-tauri/installer-hooks.nsh:117、130 | app/src-tauri/installer-hooks.nsh:130（MessageBox） | 否 | 否 | 确定 | 是 |  |
| E645 / install_move.overlap | 【无 app zh-CN 条目】新位置 {new_s} 和原位置 {old_s} 重叠，请选择另一个目录。 | R/install_move.rs:161 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） | 是 | 是 | 确定 | 否 |  |
| E646 / install_move.occupied | 【无 app zh-CN 条目】新位置已经有 {}。请选择一个空目录，或先处理新位置里的这些文件。 | R/install_move.rs:170 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） | 是 | 是 | 确定 | 否 |  |
| E647 / install_move.read | 【无 app zh-CN 条目】读取 {} 失败：{e} | R/install_move.rs:189 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） | 否 | 否 | 确定 | 是 |  |
| E648 / install_move.disk | 【无 app zh-CN 条目】新位置空间不足：需要 {} GB，剩余 {} GB。 | R/install_move.rs:197 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） | 是 | 否 | 确定 | 否 |  |
| E649 / install_move.create | 【无 app zh-CN 条目】无法创建 {new_s}：{e} | R/install_move.rs:205 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） | 否 | 否 | 确定 | 是 |  |
| E650 / install_move.copycheck | 【无 app zh-CN 条目】复制后的文件数或大小与原文件不一致 | R/install_move.rs:225 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） | 是 | 否 | 确定 | 否 |  |
| E651 / install_move.move | 【无 app zh-CN 条目】搬移 {} 失败：{e}。原位置未改动。 | R/install_move.rs:237 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） | 否 | 否 | 确定 | 是 |  |
| E652 / install_move.rewrite | 【无 app zh-CN 条目】更新设置里的路径失败：{e}。原位置未改动。 | R/install_move.rs:246 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） | 否 | 否 | 确定 | 是 |  |

### Python 推理底层：可到达错误正文的自定义异常

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E653 / python.model_read | 【无 app zh-CN 条目】{basename} 读取失败，文件可能不完整或已损坏（{type(e).__name__}: {e}）。<br>下载来的音色：删除后重新下载；自己训练的：检查当时的磁盘空间，再用「进阶设置 → 模型提取」从训练存档恢复。 | infer/lib/safe_load.py:114 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 | 是 | 是 | Tauri ErrorNote 提供复制/日志；原版文本框无专用按钮 | 是 | 不在 app zh-CN.json；原异常类型或 traceback 可随调用链附加。 |
| E654 / python.not_dict | 【无 app zh-CN 条目】{name} 不是音色模型：文件里不是权重字典。 | infer/lib/safe_load.py:142 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 | 是 | 否 | Tauri ErrorNote 提供复制/日志；原版文本框无专用按钮 | 是 | 不在 app zh-CN.json；原异常类型或 traceback 可随调用链附加。 |
| E655 / python.checkpoint | 【无 app zh-CN 条目】{name} 是训练过程中的存档（G_ / D_ 开头那种），不能直接当音色用。<br>请在训练窗「进阶设置 → 模型提取」里把它转成音色模型，或者改选训练完成后生成的那个音色 .pth。 | infer/lib/safe_load.py:147 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 | 是 | 是 | Tauri ErrorNote 提供复制/日志；原版文本框无专用按钮 | 是 | 不在 app zh-CN.json；原异常类型或 traceback 可随调用链附加。 |
| E656 / python.missing_keys | 【无 app zh-CN 条目】{name} 不是 RVC 音色模型：缺少 {missing}。 | infer/lib/safe_load.py:152 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 | 是 | 否 | Tauri ErrorNote 提供复制/日志；原版文本框无专用按钮 | 是 | 不在 app zh-CN.json；原异常类型或 traceback 可随调用链附加。 |
| E657 / python.hubert | 【无 app zh-CN 条目】找不到 hubert 模型（引擎资源未补全）：{path}<br>请回到主界面完成「引擎资源」下载（hubert / rmvpe / ffmpeg）。 | infer/modules/vc/utils.py:72 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 | 是 | 是 | Tauri ErrorNote 提供复制/日志；原版文本框无专用按钮 | 是 | 不在 app zh-CN.json；原异常类型或 traceback 可随调用链附加。 |
| E658 / python.dml_cache | 【无 app zh-CN 条目】DirectML 无法在当前显卡（%s）上分配模型缓存（%s） | infer/lib/rtrvc.py:156 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 | 是 | 否 | Tauri ErrorNote 提供复制/日志；原版文本框无专用按钮 | 是 | 不在 app zh-CN.json；原异常类型或 traceback 可随调用链附加。 |
| E659 / python.audio_path | 【无 app zh-CN 条目】You input a wrong audio path that does not exists, please fix it! | infer/lib/audio.py:41 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 | 是 | 是 | Tauri ErrorNote 提供复制/日志；原版文本框无专用按钮 | 是 | 不在 app zh-CN.json；原异常类型或 traceback 可随调用链附加。 |
| E660 / python.audio_read | 【无 app zh-CN 条目】Failed to load audio: {e} | infer/lib/audio.py:52 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 | 否 | 否 | Tauri ErrorNote 提供复制/日志；原版文本框无专用按钮 | 是 | 不在 app zh-CN.json；原异常类型或 traceback 可随调用链附加。 |
| E661 / python.audio_empty | 【无 app zh-CN 条目】audio path is empty | infer/lib/audio.py:60 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 | 是 | 否 | Tauri ErrorNote 提供复制/日志；原版文本框无专用按钮 | 是 | 不在 app zh-CN.json；原异常类型或 traceback 可随调用链附加。 |

### 实时变声：音频负载

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E662 / s.tearAskBlock | 检测到音频处理负载过高（可能出现断续或爆音），是否自动放宽分块延迟并重启变声？ | R/lib.rs:208 | UI/App.tsx:1482（Nudge 正文） | 是 | 是 | 保持现状；放宽延迟并重启变声 | 否 |  |

### 原版 WebUI：本地已安装 Gradio 3.14.0

| 编号 / id | zh-CN 原文 | producer：抛出/构造位置 | shown in：渲染位置与方式 | 原因 | 步骤 | 按钮 | 原始透传 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E663 / gradio.callback | 【无 app zh-CN 条目】Error | infer-web.py:1548; infer/modules/onnx/export.py:8; Runtime/Lib/site-packages/gradio/routes.py:338、341 | Runtime/Lib/site-packages/gradio/templates/frontend/assets/index.990b6b98.js:77（输出组件错误状态） | 否 | 否 | none | 否 | 不在 app zh-CN.json；依据当前 Runtime 中的依赖。infer-web.py:1567 未设置 show_error，默认 false，未捕获回调异常不传正文。 |
| E664 / gradio.busy | 【无 app zh-CN 条目】This application is too busy. Keep trying! | Runtime/Lib/site-packages/gradio/templates/frontend/assets/index.990b6b98.js:34 | Runtime/Lib/site-packages/gradio/templates/frontend/assets/index.990b6b98.js:77（输出组件状态） | 是 | 是 | none | 否 | 不在 app zh-CN.json；依据当前 Runtime 中的依赖。infer-web.py:1567 未设置 show_error，默认 false，未捕获回调异常不传正文。 |
| E665 / gradio.network | 【无 app zh-CN 条目】Connection errored out. | Runtime/Lib/site-packages/gradio/templates/frontend/assets/index.990b6b98.js:34 | Runtime/Lib/site-packages/gradio/templates/frontend/assets/index.990b6b98.js:77（输出组件状态） | 否 | 否 | none | 否 | 不在 app zh-CN.json；依据当前 Runtime 中的依赖。infer-web.py:1567 未设置 show_error，默认 false，未捕获回调异常不传正文。 |
| E666 / gradio.microphone | 【无 app zh-CN 条目】Please allow access to the microphone for recording. | Runtime/Lib/site-packages/gradio/templates/frontend/assets/index.1caa99ed.js:4 | Runtime/Lib/site-packages/gradio/templates/frontend/assets/index.990b6b98.js:77（Audio 输出组件错误状态） | 是 | 是 | none | 否 | 不在 app zh-CN.json；依据当前 Runtime 中的依赖。infer-web.py:1567 未设置 show_error，默认 false，未捕获回调异常不传正文。 |

## 原始异常、stderr、traceback 与退出码进入正文的索引

本表逐行引用主清单，包含 Python 原始异常、Rust/系统错误、浏览器异常与退出码。相同模板在不同入口的显示行为保留为不同记录。普通 ErrorNote 折叠 traceback 全文仍会将异常末行作为主文；“已折叠”不等于没有原始异常主文。

| 主表编号 / id | 产生位置 | 显示位置 |
| --- | --- | --- |
| E010 / s.5ee0565f28 | R/train.rs:1516 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E012 / s.217047672d | R/train.rs:1547 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E015 / s.d21a4981b7 | R/train.rs:1586 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E029 / s.trainOutUnwritable | R/train.rs:1375 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E031 / s.7803aff201 | R/train.rs:1595 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E033 / raw.train.queue_io | R/train_queue.rs:72、73、75、78、80、95; R/lib.rs:702、717 | UI/components/TrainingQueue.tsx:28（ErrorNote）；UI/components/TrainPanel.tsx:865 |
| E036 / msg.train.step_failed | tools/train_worker.py:528 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E037 / msg.train.preprocess_failed | tools/train_worker.py:567 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E040 / msg.train.f0_failed | tools/train_worker.py:650 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E042 / msg.train.feature_failed | tools/train_worker.py:670 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E048 / msg.train.train_failed | tools/train_worker.py:772 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E053 / msg.train.bad_request | tools/train_worker.py:912 | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E079 / raw.train.preprocess_file | infer/modules/train/preprocess.py:119; R/train.rs:705、715、752 | UI/components/TrainPanel.tsx:821（展开失败文件清单后显示原始原因） |
| E080 / s.auditionFailed | UI/components/TrainPanel.tsx:239 | UI/components/TrainPanel.tsx:865（ErrorNote） |
| E081 / raw.train.audition | UI/lib/audition.ts:31; UI/components/TrainPanel.tsx:239、260 | UI/components/TrainPanel.tsx:865（ErrorNote，外包 s.auditionFailed） |
| E087 / s.5ee0565f28 | R/ckpt.rs:150 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E089 / s.217047672d | R/ckpt.rs:177 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E092 / s.d21a4981b7 | R/ckpt.rs:219 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E093 / s.ckptFail | R/ckpt.rs:224 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E102 / msg.ckpt.mkdir_failed | tools/ckpt_worker.py:178 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E103 / msg.ckpt.onnx_missing_deps | tools/ckpt_worker.py:182 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E104 / msg.ckpt.onnx_failed | tools/ckpt_worker.py:187 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E105 / msg.ckpt.bad_request | tools/ckpt_worker.py:197 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E107 / raw.ckpt.info | infer/lib/train/process_ckpt.py:77; tools/ckpt_worker.py:94 | UI/components/CkptAdvanced.tsx:394（ErrorNote error=false，直接显示全文） |
| E108 / raw.ckpt.operations | infer/lib/train/process_ckpt.py:207、219、277; tools/ckpt_worker.py:111、140、161 | UI/components/CkptAdvanced.tsx:394（ErrorNote，异常末行主文） |
| E121 / s.5ee0565f28 | R/sts.rs:978; R/sts.rs:1821 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E125 / s.4f592d4fc2 | R/sts.rs:1013; R/sts.rs:1892 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E127 / s.e9ddef6eab | R/sts.rs:1760 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E130 / s.stsDeleteFail | R/sts.rs:775; R/sts_sources.rs:457 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E131 / s.stsRenameFail | R/sts.rs:829; R/sts_sources.rs:513 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E133 / s.stsRecordNoFolder | R/sts.rs:947 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E140 / s.cdad0c927d | R/sts.rs:2104 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E141 / s.0d8ec50de8 | R/sts.rs:2115 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E142 / s.stsStateUnreadable | R/sts_sources.rs:114; R/sts_sources.rs:116; R/sts_sources.rs:121 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E147 / msg.sts.all_failed | tools/sts_worker.py:464 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E148 / msg.sts.bad_request | tools/sts_worker.py:489 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E149 / raw.sts.worker | tools/sts_worker.py:418、549; tools/sts_core.py:64、698、1025; gui_v1.py:4010、4024、4041、4136 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E151 / literal.sts.dml | tools/sts_core.py:83 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E157 / raw.sts.source_io | R/sts_sources.rs:130、131; R/sts.rs:314、836、843 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E172 / s.itemReason | UI/components/TtsPanel.tsx:2253 | UI/components/TtsPanel.tsx:2253（条目正文） |
| E176 / s.e9ddef6eab | R/tts.rs:411; R/tts.rs:458 | UI/components/TtsPanel.tsx:2541（ErrorNote） |
| E177 / s.6fe5607f45 | R/tts.rs:190 | UI/components/TtsPanel.tsx:2541（ErrorNote） |
| E180 / s.9273991f94 | R/tts.rs:211 | UI/components/TtsPanel.tsx:2541（ErrorNote） |
| E181 / s.6619dda8e2 | R/tts.rs:217; R/tts.rs:220 | UI/components/TtsPanel.tsx:2541（ErrorNote） |
| E185 / s.9f8084f7cb | R/tts.rs:425; R/tts.rs:516 | UI/components/TtsPanel.tsx:2541（ErrorNote） |
| E191 / raw.tts.sts | R/tts.rs:475; UI/components/TtsPanel.tsx:2341、2352、2359、2404 | UI/components/TtsPanel.tsx:2541（ErrorNote） |
| E195 / s.5ee0565f28 | R/separate.rs:290 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E201 / s.e9ddef6eab | R/separate.rs:262 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E202 / s.c727da1f5b | R/separate.rs:320 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E204 / s.a4abecd0fe | R/separate.rs:400 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E205 / s.6b7047af91 | R/separate.rs:405 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E207 / msg.sep.bad_request | tools/separate_worker.py:81 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E208 / msg.sep.failed | tools/separate_worker.py:152 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E213 / python.sep.catalog | tools/pymss/model_registry.py:132 | UI/components/SeparatePanel.tsx:250（在 msg.sep.failed 后的 detail） |
| E217 / s.7611f15dff | R/worker.rs:961; R/worker.rs:977 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 |
| E218 / s.wkKilledBySystem | R/worker.rs:1064; R/worker.rs:1875 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 |
| E219 / s.wkExitedWithCode | R/worker.rs:1066 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 |
| E230 / s.exitAccessViolation | R/crash.rs:63 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） |
| E231 / s.exitDivideByZero | R/crash.rs:64 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） |
| E232 / s.exitIllegalInstruction | R/crash.rs:65 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） |
| E233 / s.exitStackBufferOverrun | R/crash.rs:66 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） |
| E234 / s.exitStackOverflow | R/crash.rs:67 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） |
| E235 / s.exitMissingDll | R/crash.rs:68 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） |
| E236 / s.exitInterrupted | R/crash.rs:69 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（嵌入退出码描述） |
| E237 / raw.engine.invoke | UI/hooks/useEngine.ts:176、199、423、485、512; UI/components/Overlay.tsx:135; R/lib.rs:2049、2093、2130 | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） |
| E246 / msg.engine.missing_gui | tools/realtime_worker.py:215 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E247 / msg.engine.crash_load | tools/dsp_worker.py:1032; tools/realtime_worker.py:266 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E248 / msg.engine.loop_error | tools/dsp_worker.py:988; gui_v1.py:4398 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E249 / msg.engine.files_corrupt | tools/realtime_worker.py:264 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E250 / msg.engine.nvidia_cuda_missing | gui_v1.py:3804、4248 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E254 / msg.vc.start_failed | tools/dsp_worker.py:918; gui_v1.py:3811 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E255 / msg.vc.dml_alloc | gui_v1.py:3808 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E256 / msg.vc.stop_failed | tools/dsp_worker.py:940; gui_v1.py:3830 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E259 / msg.dev.list_failed | tools/dsp_worker.py:856; gui_v1.py:2844 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E260 / msg.dev.invalid | gui_v1.py:1169 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E261 / raw.vc.status_error | gui_v1.py:1676、2842、3814、3828、4397; tools/realtime_worker.py:269、279; tools/dsp_worker.py:854、917、938、987 | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） |
| E265 / python.device_input | gui_v1.py:2429 | UI/components/Dock.tsx:217；gui_v1.py:1046（popup） |
| E266 / python.device_output | gui_v1.py:2431 | UI/components/Dock.tsx:217；gui_v1.py:1046（popup） |
| E282 / s.dspPresetSaveFail | R/dsp.rs:204; R/dsp.rs:213 | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 |
| E284 / s.dspPresetDeleteFail | R/dsp.rs:227 | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 |
| E285 / raw.dsp.load_apply | UI/components/DspPresetGrid.tsx:90; UI/pages/ModelsPage.tsx:144 | UI/components/DspPresetGrid.tsx:124；UI/pages/ModelsPage.tsx:527 |
| E293 / modelVersions.installFailed | R/model_versions.rs:285; R/model_versions.rs:350 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 |
| E300 / s.a5a2f91ea1 | R/voices.rs:1736 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 |
| E303 / s.1090b966ea | R/voices.rs:1936 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 |
| E304 / s.voiceDeleteFailed | R/voices.rs:2129 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 |
| E310 / home.switchFail | UI/pages/HomePage.tsx:268 | UI/pages/HomePage.tsx:268（toast / 卡片警告 / 轮次说明；home.switchFail 在 HomePage.tsx:340） |
| E317 / s.c4a98bd0e6 | UI/pages/HomePage.tsx:297 | UI/pages/HomePage.tsx:297（加载错误正文） |
| E318 / raw.voice.io | R/voices.rs:214、216、225、226、229、380、396、1667、1735、1775、1822、1933、2153、2159、2248、2268、2272、2273、2275、2276、2279、2280、2281、2283、2284、2304、2557、2563、2571 | UI/pages/ModelsPage.tsx:527（toast）；UI/pages/HomePage.tsx:297、340（加载正文/切换 toast） |
| E319 / raw.voice.import_result | R/voices.rs:1857、1875、1879、1909、1911; UI/pages/ModelsPage.tsx:494 | UI/pages/ModelsPage.tsx:527（toast）；UI/pages/HomePage.tsx:297、340（加载正文/切换 toast） |
| E320 / s.47a27ebb17 | R/config.rs:391; R/config.rs:510; R/config.rs:676; R/config.rs:692; R/config.rs:749; R/config.rs:829; R/config.rs:839 | UI/pages/SettingsPage.tsx:277（文本）；触发保存的音色/设备/工具面板也接收 invoke 拒绝 |
| E321 / s.4ad9fdccd9 | R/config.rs:500 | UI/pages/SettingsPage.tsx:277（文本）；触发保存的音色/设备/工具面板也接收 invoke 拒绝 |
| E322 / s.1455f353e7 | R/config.rs:866; R/config.rs:904; R/config.rs:944 | UI/pages/SettingsPage.tsx:277（文本）；触发保存的音色/设备/工具面板也接收 invoke 拒绝 |
| E324 / s.e0125710be | UI/pages/MorePage.tsx:113 | UI/pages/MorePage.tsx:350（ListItem desc） |
| E329 / raw.settings.auto | UI/pages/SettingsPage.tsx:250 | UI/pages/SettingsPage.tsx:427（自动配置提示） |
| E331 / s.audioProbeCrash | R/audio_probe.rs:74 | UI/components/AudioRecovery.tsx:41（Nudge）、66（alert）；探测崩溃也至 Dock.tsx:217 |
| E334 / raw.recovery.native | R/audio_recovery.rs:17、22、23、26、34、36、41、45、47、48、56、72、76、77、174 | UI/components/AudioRecovery.tsx:41（Nudge error）及 :66（alert） |
| E338 / s.5ee0565f28 | R/mic.rs:123; R/mic.rs:135 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） |
| E346 / s.4f592d4fc2 | R/mic.rs:164 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） |
| E348 / raw.mic.unknown | R/mic.rs:75; tools/record_worker.py:351、363 | UI/components/MicTest.tsx:153；UI/components/LinkCheckDialog.tsx:391（结果正文） |
| E352 / neptune.trimFailed | R/audio_edit.rs:195; R/audio_edit.rs:274 | UI/components/AudioTrim.tsx:181（错误/校验正文）；:152（波形失败） |
| E354 / raw.trim.native | R/audio_edit.rs:146、186、208、265、297、317 | UI/components/AudioTrim.tsx:181（正文） |
| E363 / s.90e6bba99d | R/provision.rs:763; R/provision.rs:770; R/runtime_migration.rs:173 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） |
| E378 / raw.runtime.io | R/provision.rs:467、469、482、484、742、745、761; UI/components/RuntimeMigrationDialog.tsx:65、92、197、223 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（正文） |
| E386 / s.dlDetail | R/download.rs:276 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E391 / s.242a3a8640 | R/extract.rs:221 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E403 / s.21ce93c732 | R/download.rs:553 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E405 / s.fe9e98a65c | R/download.rs:883 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E406 / s.9f44b201ee | R/extract.rs:83 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E408 / s.79a3d2ebab | R/extract.rs:151 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E409 / s.f456299616 | R/extract.rs:154 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E410 / s.646bbce5a0 | R/extract.rs:166 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E412 / s.90e6bba99d | R/extract.rs:200 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E414 / s.e32a4f9295 | R/extract.rs:214 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E415 / s.c9aafa74d7 | R/extract.rs:215 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E417 / s.a4462e4266 | R/extract.rs:236 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E420 / raw.download.unknown | R/download.rs:254 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；ExtrasDialog.tsx:379、StoreSection.tsx:616（正文）；UpdateNudge.tsx:72 |
| E427 / s.extraRemoveFailed | R/extra_assets.rs:551 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 |
| E428 / s.ec982d9c98 | R/extra_assets.rs:602; R/extra_assets.rs:613 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 |
| E429 / s.0df1f31a67 | R/extra_assets.rs:638 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 |
| E430 / s.538ff61331 | R/extra_assets.rs:642 | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 |
| E440 / s.04c4e3b2b3 | R/engine_assets.rs:278; R/engine_assets.rs:331 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E442 / s.0707e8af4e | R/engine_assets.rs:280; R/engine_assets.rs:334 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E443 / s.vbcableUninstallFailedCode | R/engine_assets.rs:488 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E444 / s.vbcableFailedCode | R/engine_assets.rs:490 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E445 / s.23220ab448 | R/engine_assets.rs:517 | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E453 / s.vcrCancelled | R/vcredist.rs:64 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） |
| E454 / s.vcrBusy | R/vcredist.rs:65 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） |
| E455 / s.vcrFailed | R/vcredist.rs:66; R/vcredist.rs:168 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） |
| E456 / s.007e8f085e | R/store.rs:901 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 |
| E464 / s.8c8dade1e1 | R/store.rs:1304 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 |
| E466 / s.80b25fdbcd | R/store.rs:1825 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 |
| E468 / s.afcf23635f | R/store.rs:1913 | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 |
| E470 / raw.store.io | UI/lib/storeJobs.ts:141; UI/components/StoreSection.tsx:208、447、463; UI/hooks/usePlaza.ts:35 | UI/components/StoreSection.tsx:518、616（正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71；CommunityDownloadOrb.tsx:89（悬浮提示） |
| E471 / s.a005e42321 | R/plaza.rs:459 | UI/pages/PlazaPage.tsx:310（Warn）；StoreSection.tsx:518、616（正文） |
| E472 / s.d2620f4b90 | R/plaza.rs:466 | UI/pages/PlazaPage.tsx:310（Warn）；StoreSection.tsx:518、616（正文） |
| E479 / s.acc7dfe816 | R/update.rs:247 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） |
| E480 / s.0350fdf3a0 | R/update.rs:251 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） |
| E481 / s.a9fa441818 | R/update.rs:264 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） |
| E482 / s.7935e3dd3e | R/update.rs:270 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） |
| E483 / s.ac3a85a9c1 | UI/lib/updateFlow.ts:121 | UI/pages/SettingsPage.tsx:1177（检查结果）；UI/components/UpdateNudge.tsx:72（安装错误） |
| E484 / s.bac68ea7db | UI/lib/updateFlow.ts:147 | UI/pages/SettingsPage.tsx:1177（检查结果）；UI/components/UpdateNudge.tsx:72（安装错误） |
| E542 / raw.pack.export | R/publication_packs.rs:30、44、129、130、133、152、154; R/voices.rs:2248、2268、2272、2273、2275、2276、2279、2280、2281、2283、2284 | UI/components/ExportVoicePackages.tsx:81（逐条正文） |
| E556 / raw.linkcheck.invoke | UI/components/LinkCheckDialog.tsx:66（diagnostics_link_check 拒绝值） | UI/components/LinkCheckDialog.tsx:323（错误正文） |
| E571 / s.7fae0289b6 | UI/pages/MorePage.tsx:198 | UI/pages/MorePage.tsx:483（ListItem desc） |
| E575 / raw.storage.clean | R/lib.rs:738、746、972、977; R/paths.rs:628; R/train.rs:593 | UI/components/StorageSection.tsx:249（正文） |
| E580 / s.84256012c6 | R/shell_extras.rs:691 | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） |
| E581 / s.470a002848 | R/shell_extras.rs:694 | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） |
| E582 / raw.diagnostics.pack | R/shell_extras.rs:876、877、1350、1354、1438、1439、1450 | UI/pages/MorePage.tsx:483（ListItem 描述） |
| E583 / s.eea9655c7b | R/shell_extras.rs:1342 | UI/pages/MorePage.tsx:483（生成诊断包结果中的 perf_note） |
| E585 / s.f1f3d2302b | R/legacy.rs:76 | UI/pages/MorePage.tsx:505、512（ListItem 描述） |
| E588 / s.ea582ad463 | UI/pages/MorePage.tsx:136 | UI/pages/MorePage.tsx:505、512（ListItem 描述） |
| E591 / raw.ui.render | UI/components/ErrorBoundary.tsx:38 | UI/components/ErrorBoundary.tsx:97（整页 pre，默认展开） |
| E593 / literal.boot.script | app/index.html:105 | app/index.html:87、91（启动页标题 + 展开详情） |
| E594 / literal.boot.rejection | app/index.html:122 | app/index.html:87、91（启动页标题 + 展开详情） |
| E613 / record.nolib | tools/record_worker.py:241 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E614 / record.enum | tools/record_worker.py:247 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E615 / record.open | tools/record_worker.py:213 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E616 / record.request | tools/record_worker.py:351 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E617 / record.unhandled | tools/record_worker.py:363 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E618 / raw.cover.io | R/voices.rs:2405、2410、2414、2446、2504; UI/components/CropCoverDialog.tsx:20 | app/node_modules/trm-ui/lib/index.js:6425（ImageCropDialog alert）；社区首次打开失败另映射 publication.coverError |
| E620 / legacy.auto_start | gui_v1.py:864 | gui_v1.py:864（PySimpleGUI popup_error） |
| E621 / legacy.start | gui_v1.py:913 | gui_v1.py:913（PySimpleGUI popup_error） |
| E626 / legacy.check.device | gui_v1.py:1169 | gui_v1.py:1046（popup）；worker 模式同时至 Dock.tsx:217 |
| E628 / legacy.vc.traceback | infer/modules/vc/modules.py:245、247 | infer-web.py:954（vc_output1 文本框） |
| E629 / legacy.vc.batch_traceback | infer/modules/vc/modules.py:321、326 | infer-web.py:1094（vc_output3 文本框） |
| E630 / legacy.train.preprocess | infer-web.py:251、258; infer/modules/train/preprocess.py:119、145 | infer-web.py:1179（info1 文本框） |
| E631 / legacy.train.feature | infer-web.py:343、350、392、399 | infer-web.py:1223（info2 文本框） |
| E632 / legacy.train.index | infer-web.py:662、665 | infer-web.py:1328（info3 文本框） |
| E633 / legacy.ckpt.traceback | infer/lib/train/process_ckpt.py:77、207、219、277 | infer-web.py:1427、1465、1481、1523（info4/5/6/7 文本框） |
| E635 / legacy.faq.load | infer-web.py:1562 | infer-web.py:1562（gr.Markdown） |
| E641 / nsis.webview2DownloadError | app/src-tauri/nsis-languages/SimpChinese.nsh:22 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:22 |
| E642 / nsis.webview2InstallError | app/src-tauri/nsis-languages/SimpChinese.nsh:25 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:25 |
| E644 / nsis.move_failed | app/src-tauri/installer-hooks.nsh:117、130 | app/src-tauri/installer-hooks.nsh:130（MessageBox） |
| E647 / install_move.read | R/install_move.rs:189 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） |
| E649 / install_move.create | R/install_move.rs:205 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） |
| E651 / install_move.move | R/install_move.rs:237 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） |
| E652 / install_move.rewrite | R/install_move.rs:246 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） |
| E653 / python.model_read | infer/lib/safe_load.py:114 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 |
| E654 / python.not_dict | infer/lib/safe_load.py:142 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 |
| E655 / python.checkpoint | infer/lib/safe_load.py:147 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 |
| E656 / python.missing_keys | infer/lib/safe_load.py:152 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 |
| E657 / python.hubert | infer/modules/vc/utils.py:72 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 |
| E658 / python.dml_cache | infer/lib/rtrvc.py:156 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 |
| E659 / python.audio_path | infer/lib/audio.py:41 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 |
| E660 / python.audio_read | infer/lib/audio.py:52 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 |
| E661 / python.audio_empty | infer/lib/audio.py:60 | UI/components/Dock.tsx:217（实时状态）；UI/components/TtsPanel.tsx:2233、2253（转换错误/失败清单）；infer-web.py:954（原版推理文本框），按调用链显示 |

## 通用兜底与包装文案索引

下列固定模板没有给出具体原因，或仅包装异常/退出码/日志提示。运行时占位符可以带来更多信息，不改变模板本身是通用包装的事实；正文原文与使用位置均可回查主表。标有“动态”的项是原样回退边界。

| 主表编号 / id | 原文或动态来源 | 使用位置 |
| --- | --- | --- |
| E010 / s.5ee0565f28 | 写请求文件失败：{e} | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E012 / s.217047672d | 训练进程启动失败：{e} | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E013 / s.c73d43b29b | 无法读取训练进程的输出 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E014 / s.60a21a8105 | 训练失败 | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E015 / s.d21a4981b7 | 等待训练进程时出错：{e} | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E031 / s.7803aff201 | 训练进程异常退出（{a0}）。详情见 logs/{a1}/train.log | UI/components/TrainPanel.tsx:865（ErrorNote）；UI/components/TrainingQueue.tsx:28、55（ErrorNote） |
| E032 / trainingQueue.Failed | 训练失败 | UI/components/TrainingQueue.tsx:41（Tag 状态标签） |
| E033 / raw.train.queue_io | 动态：队列 JSON 解析、文件创建/写入/重命名或异步任务错误 | UI/components/TrainingQueue.tsx:28（ErrorNote）；UI/components/TrainPanel.tsx:865 |
| E036 / msg.train.step_failed | 该步骤失败（退出码 {code}），详情见 {log} | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E037 / msg.train.preprocess_failed | 数据预处理失败（退出码 {code}），详情见 {log} | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E040 / msg.train.f0_failed | 音高提取失败（退出码 {code}），详情见 {log} | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E042 / msg.train.feature_failed | 特征提取失败（退出码 {code}），详情见 {log} | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E048 / msg.train.train_failed | 训练失败（退出码 {code}），详情见 {log} | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E053 / msg.train.bad_request | 无法读取请求文件：{error} | UI/components/TrainingQueue.tsx:55（ErrorNote；train.rs:1568、train_queue.rs:327 转发） |
| E079 / raw.train.preprocess_file | 动态：preprocess.log 每个失败文件最后一条非空行，截取 200 个字符，最多 20 项 | UI/components/TrainPanel.tsx:821（展开失败文件清单后显示原始原因） |
| E080 / s.auditionFailed | 试听失败：{} | UI/components/TrainPanel.tsx:865（ErrorNote） |
| E081 / raw.train.audition | 动态：STS 调用或音频试听失败字符串 | UI/components/TrainPanel.tsx:865（ErrorNote，外包 s.auditionFailed） |
| E087 / s.5ee0565f28 | 写请求文件失败：{e} | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E089 / s.217047672d | 训练进程启动失败：{e} | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E090 / s.c73d43b29b | 无法读取训练进程的输出 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E091 / s.60a21a8105 | 训练失败 | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E092 / s.d21a4981b7 | 等待训练进程时出错：{e} | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E093 / s.ckptFail | 处理失败（退出码 {a0}） | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E102 / msg.ckpt.mkdir_failed | 无法创建输出目录：{error} | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E104 / msg.ckpt.onnx_failed | ONNX 导出失败：{error} | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E105 / msg.ckpt.bad_request | 无法读取请求文件：{error} | UI/components/CkptAdvanced.tsx:394（ErrorNote） |
| E121 / s.5ee0565f28 | 写请求文件失败：{e} | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E125 / s.4f592d4fc2 | 转换进程启动失败：{e} | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E126 / s.68759edc4b | 无法读取转换进程的输出 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E130 / s.stsDeleteFail | 删除失败：{a0} | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E131 / s.stsRenameFail | 重命名失败：{a0} | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E136 / s.stsHotFailed | 转换失败。详情请查看 User_Data/logs/sts/ 中本次的日志。 | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E140 / s.cdad0c927d | 等待转换进程时出错：{e} | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E141 / s.0d8ec50de8 | 转换进程异常退出（{a0}）。详情见 User_Data/logs/sts/ | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E142 / s.stsStateUnreadable | 无法读取来源清单：{a0} | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E147 / msg.sts.all_failed | {total} 个文件全部转换失败。第一个原因：{first} | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E148 / msg.sts.bad_request | 无法读取请求文件：{error} | UI/components/TtsPanel.tsx:2233（ErrorNote）；失败条目原因 :2253 |
| E149 / raw.sts.worker | 动态：模型加载失败／转换异常；friendly_error 未识别时原文或异常末行 + traceback | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E157 / raw.sts.source_io | 动态：来源清单序列化/写入、请求目录创建错误 | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E159 / literal.sts.unknown | 未知错误 | UI/components/TtsPanel.tsx:2233、2253（ErrorNote / 失败清单） |
| E170 / s.stsSkippedTitle | 以下 {v0} 个文件转换失败： | UI/components/TtsPanel.tsx:2245（状态/列表/错误提示；播放错误 → :2233 ErrorNote） |
| E177 / s.6fe5607f45 | PowerShell 启动失败：{e} | UI/components/TtsPanel.tsx:2541（ErrorNote） |
| E178 / s.787332269e | PowerShell 执行失败 | UI/components/TtsPanel.tsx:2541（ErrorNote） |
| E191 / raw.tts.sts | 动态：STS 后处理失败（与 raw.sts.worker 同一路径）及 Tauri 异步调用错误 | UI/components/TtsPanel.tsx:2541（ErrorNote） |
| E195 / s.5ee0565f28 | 写请求文件失败：{e} | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E202 / s.c727da1f5b | 分离进程启动失败：{e} | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E203 / s.1a66c860cd | 无法读取分离进程的输出 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E204 / s.a4abecd0fe | 等待分离进程时出错：{e} | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E205 / s.6b7047af91 | 分离进程异常退出（{a0}）。详情见 User_Data/logs/separate.log | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E207 / msg.sep.bad_request | 无法读取请求文件：{error} | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E208 / msg.sep.failed | 分离失败，详见日志 | UI/components/SeparatePanel.tsx:250（ErrorNote）；STS 内分离入口也可至 TtsPanel.tsx:2233 |
| E214 / s.wkReadyTimeout | 等待引擎就绪超时，请再试一次，或查看 User_Data/logs/realtime_worker.log | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 |
| E219 / s.wkExitedWithCode | 引擎进程已退出，退出码 {}。 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 |
| E220 / s.wkStartTimeout | 启动超时 | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 |
| E222 / s.7da520ca1f | 启动超时且引擎已退出，请查看 User_Data/logs/realtime_worker.log | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 |
| E223 / msg.vc.start_timeout | 启动超时：引擎未进入变声。请重试，或查看 User_Data/logs/realtime_worker.log | UI/components/Dock.tsx:205、217（状态主副行；useEngine.ts:164 优先 error）；UI/components/Overlay.tsx:182 |
| E237 / raw.engine.invoke | 动态：IPC/启动/停止/热参数更新失败；String(e) / Error.message | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） |
| E244 / s.wkDiedDuringLoad | 引擎进程在加载过程中退出，请查看 User_Data/logs/worker/ 中当天的日志。 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（状态文本） |
| E245 / s.wkPidNotAlive | 引擎进程已不在运行 | UI/components/Dock.tsx:217；UI/components/Overlay.tsx:182（状态文本） |
| E247 / msg.engine.crash_load | 引擎加载时崩溃，详见日志 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E248 / msg.engine.loop_error | 引擎内部错误，详见日志 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E254 / msg.vc.start_failed | 启动失败 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E256 / msg.vc.stop_failed | 停止失败 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E257 / msg.vc.swap_failed | 切换失败，仍在使用上一音色 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E259 / msg.dev.list_failed | 读取设备失败 | UI/components/Dock.tsx:217（message/error 状态行）；UI/components/Overlay.tsx:182 |
| E261 / raw.vc.status_error | 动态：status.error 原始异常；list_devices/start/stop/loop 的类型名与异常正文 | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） |
| E263 / literal.vc.swap_failed | 换模型失败，仍在用上一个音色 | UI/components/Dock.tsx:217（状态行）；UI/components/Overlay.tsx:182（状态行） |
| E272 / dock.engineError | 引擎错误 | UI/components/Dock.tsx:205、217（状态行） |
| E277 / s.trouble.unknown.body | 启动过程中出现了错误。运行自检会逐项检查运行环境、设备与虚拟声卡，并给出处理办法。 | UI/App.tsx:1553（Nudge 正文） |
| E278 / s.trouble.title | 变声未能启动 | UI/App.tsx:1545（Nudge 标题） |
| E282 / s.dspPresetSaveFail | 预设保存失败：{0} | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 |
| E284 / s.dspPresetDeleteFail | 预设删除失败：{0} | UI/components/DspPresetEditor.tsx:299（状态文本）；UI/components/DspPresetGrid.tsx:124（加载错误）；应用错误也至 ModelsPage.tsx:527 |
| E285 / raw.dsp.load_apply | 动态：获取预设/应用预设的 IPC 或文件错误 | UI/components/DspPresetGrid.tsx:124；UI/pages/ModelsPage.tsx:527 |
| E293 / modelVersions.installFailed | 切换模型失败。 | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 |
| E303 / s.1090b966ea | 复制 .pth 失败: {e} | UI/pages/ModelsPage.tsx:527（toast）；部分选择错误也至 HomePage.tsx:340 |
| E310 / home.switchFail | 切换失败：{error} | UI/pages/HomePage.tsx:268（toast / 卡片警告 / 轮次说明；home.switchFail 在 HomePage.tsx:340） |
| E317 / s.c4a98bd0e6 | 读取音色目录失败：{v0} | UI/pages/HomePage.tsx:297（加载错误正文） |
| E318 / raw.voice.io | 动态：档案 JSON/文件操作错误；copy index: {e}；读取、导出、复制、重命名、备份文件失败 | UI/pages/ModelsPage.tsx:527（toast）；UI/pages/HomePage.tsx:297、340（加载正文/切换 toast） |
| E319 / raw.voice.import_result | 动态：批量导入 errors[].error，界面合并显示 | UI/pages/ModelsPage.tsx:527（toast）；UI/pages/HomePage.tsx:297、340（加载正文/切换 toast） |
| E320 / s.47a27ebb17 | 保存设置失败：{e} | UI/pages/SettingsPage.tsx:277（文本）；触发保存的音色/设备/工具面板也接收 invoke 拒绝 |
| E321 / s.4ad9fdccd9 | 写入 inuse 配置失败：{e} | UI/pages/SettingsPage.tsx:277（文本）；触发保存的音色/设备/工具面板也接收 invoke 拒绝 |
| E322 / s.1455f353e7 | 文件保存失败：{e} | UI/pages/SettingsPage.tsx:277（文本）；触发保存的音色/设备/工具面板也接收 invoke 拒绝 |
| E324 / s.e0125710be | 保存失败：{v0} | UI/pages/MorePage.tsx:350（ListItem desc） |
| E329 / raw.settings.auto | 动态：设备列表刷新或自动配置 invoke 错误 | UI/pages/SettingsPage.tsx:427（自动配置提示） |
| E330 / neptune.deviceRecovery | 音频设备无法启动。可忽略检查失败的设备，然后重新配置。 | UI/components/AudioRecovery.tsx:41（Nudge）、66（alert）；探测崩溃也至 Dock.tsx:217 |
| E333 / neptune.deviceCheckFailed | 音频设备检查未能完成。请尝试兼容模式，或在设备与音频设置中重新选择设备。 | UI/components/AudioRecovery.tsx:66（alert） |
| E334 / raw.recovery.native | 动态：兼容组件下载/ZIP/文件读写、探测进程、JSON、异步错误 | UI/components/AudioRecovery.tsx:41（Nudge error）及 :66（alert） |
| E338 / s.5ee0565f28 | 写请求文件失败：{e} | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） |
| E346 / s.4f592d4fc2 | 转换进程启动失败：{e} | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） |
| E347 / s.68759edc4b | 无法读取转换进程的输出 | UI/components/MicTest.tsx:153（状态文本）；UI/components/LinkCheckDialog.tsx:391（麦克风结果） |
| E350 / neptune.waveformFailed | 波形读取失败，仍可使用下方时间输入。 | UI/components/AudioTrim.tsx:181（错误/校验正文）；:152（波形失败） |
| E352 / neptune.trimFailed | 音频裁剪失败。 | UI/components/AudioTrim.tsx:181（错误/校验正文）；:152（波形失败） |
| E354 / raw.trim.native | 动态：目录创建、ffmpeg 启动或异步任务失败 | UI/components/AudioTrim.tsx:181（正文） |
| E355 / s.e12d8322af | 未能识别显卡类型：{}，请手动选择 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） |
| E356 / s.rtExtractFailed | 下载与校验均已通过，失败发生在解压步骤，重新下载无法解决该问题。 | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） |
| E358 / s.dlReconnect | 连接失败，正在重连（第 {v0} 次）… | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） |
| E363 / s.90e6bba99d | 移动运行环境失败：{e} | UI/components/ProvisionGate.tsx:335（compact ErrorNote）；UI/components/RuntimeMigrationDialog.tsx:178（错误正文） |
| E373 / s.44c7946c76 | 补全失败 | UI/components/ProvisionGate.tsx:335（compact ErrorNote） |
| E380 / s.netUnknown | 无法获取在线信息。请稍后重试；问题持续时，请在「其他」页加入 QQ 群反馈。 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E382 / s.netRetryOrManual | 请重试；若仍失败，请前往官网下载安装包。 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E392 / s.e0dab22b1a | 下载失败 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E403 / s.21ce93c732 | 打开文件失败: {e} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E405 / s.fe9e98a65c | 完成重命名失败: {e} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E406 / s.9f44b201ee | 打开 tar 失败: {e} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E408 / s.79a3d2ebab | 读取 tar 失败: {e} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E409 / s.f456299616 | tar 条目错误: {e} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E410 / s.646bbce5a0 | 解压失败 {a0}: {a1} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E412 / s.90e6bba99d | 移动运行环境失败：{e} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E414 / s.e32a4f9295 | 打开压缩包失败：{e} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E415 / s.c9aafa74d7 | 读取压缩包失败：{e} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E417 / s.a4462e4266 | 写入 {a0} 失败：{a1} | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；UI/components/ExtrasDialog.tsx:379（正文）；StoreSection.tsx:518、616（Warn/正文）；UpdateNudge.tsx:72（Nudge） |
| E420 / raw.download.unknown | 动态：download_error_text 未识别的错误原文位于首行 | UI/components/ProvisionGate.tsx:335、AudioToolsDialog.tsx:129（compact ErrorNote）；ExtrasDialog.tsx:379、StoreSection.tsx:616（正文）；UpdateNudge.tsx:72 |
| E423 / s.dlReconnect | 连接失败，正在重连（第 {v0} 次）… | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 |
| E429 / s.0df1f31a67 | {a0} 下载失败：{a1} | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 |
| E430 / s.538ff61331 | {a0} 保存失败：{a1} | UI/components/ExtrasDialog.tsx:379（正文）；全局下载球 CommunityDownloadOrb.tsx:89 |
| E432 / s.e0dab22b1a | 下载失败 | UI/components/ExtrasDialog.tsx:379（正文）；CommunityDownloadOrb.tsx:89 |
| E440 / s.04c4e3b2b3 | 下载失败：{e} | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E442 / s.0707e8af4e | 解压失败：{e} | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E443 / s.vbcableUninstallFailedCode | 卸载失败（错误码 {e}） | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E444 / s.vbcableFailedCode | 安装失败（错误码 {e}） | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E445 / s.23220ab448 | 启动安装程序失败：{e} | UI/components/AudioToolsDialog.tsx:129 / ProvisionGate.tsx:335（compact ErrorNote）；UI/pages/HelpPage.tsx:461、UI/components/SetupGuide.tsx:238（驱动状态）；ExtrasDialog.tsx:379（资源错误） |
| E455 / s.vcrFailed | 运行库安装失败（代码 {e}） | UI/components/ProvisionGate.tsx:335（compact ErrorNote） |
| E459 / s.dlReconnect | 连接失败，正在重连（第 {v0} 次）… | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 |
| E464 / s.8c8dade1e1 | 复制 pth 失败：{e} | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 |
| E466 / s.80b25fdbcd | 删除失败：{e} | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 |
| E468 / s.afcf23635f | 复制模型失败：{e} | UI/components/StoreSection.tsx:518、616（Warn/正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71（alert）；CommunityDownloadOrb.tsx:89 |
| E470 / raw.store.io | 动态：下载/安装/删除失败的 String(e)；下载队列前缀为 {label &#124;&#124; id}： | UI/components/StoreSection.tsx:518、616（正文）；UI/pages/PlazaPage.tsx:310（Warn）；StarterVoices.tsx:71；CommunityDownloadOrb.tsx:89（悬浮提示） |
| E479 / s.acc7dfe816 | 下载更新失败：{e} | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） |
| E480 / s.0350fdf3a0 | 解压更新失败：{e} | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） |
| E481 / s.a9fa441818 | 备份旧界面失败：{e} | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） |
| E482 / s.7935e3dd3e | 替换界面失败：{e} | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（更新状态行） |
| E483 / s.ac3a85a9c1 | 检查更新失败：{v0} | UI/pages/SettingsPage.tsx:1177（检查结果）；UI/components/UpdateNudge.tsx:72（安装错误） |
| E484 / s.bac68ea7db | 更新失败：{v0} | UI/pages/SettingsPage.tsx:1177（检查结果）；UI/components/UpdateNudge.tsx:72（安装错误） |
| E485 / s.3d1fde4601 | 暂未获取到程序更新包，可先前往发布页手动下载 | UI/components/UpdateNudge.tsx:72（Nudge）；UI/pages/SettingsPage.tsx:1177（状态） |
| E502 / audio.readFailed | 无法读取音频库。请检查音频库文件。 | UI/pages/AudioPage.tsx:119（状态/alert；集中错误在 :488） |
| E503 / audio.operationFailed | 操作未能完成。请检查文件或设备后重试。 | UI/pages/AudioPage.tsx:301; UI/pages/AudioPage.tsx:310; UI/pages/AudioPage.tsx:315; UI/pages/AudioPage.tsx:615; UI/pages/AudioPage.tsx:618; UI/pages/AudioPage.tsx:621; UI/pages/AudioPage.tsx:671; UI/pages/AudioPage.tsx:675; UI/pages/AudioPage.tsx:678; UI/pages/AudioPage.tsx:681; UI/pages/AudioPage.tsx:705; UI/pages/AudioPage.tsx:712（状态/alert；集中错误在 :488） |
| E509 / neptune.waveformFailed | 波形读取失败，仍可使用下方时间输入。 | UI/pages/AudioPage.tsx:603（状态/alert；集中错误在 :488） |
| E512 / audio.hotkeySaveFailed | 未能保存快捷键。请检查组合键或设备占用情况。 | UI/components/AudioHotkeyEditor.tsx:89; UI/pages/SettingsPage.tsx:1275（alert/状态标签） |
| E523 / publication.retryQueued | 可以重试。 | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） |
| E525 / publication.requestFailed | 暂时无法完成操作，请重试。 | UI/components/CommunityPublisher.tsx:205；CommunityBatchPublisher.tsx:272、365、385；CommunitySubmissions.tsx:169；CommunityModelDetail.tsx:48；CommunityModelList.tsx:178（Warn） |
| E526 / community.signInFailed | 登录失败，请重试。 | UI/components/CommunityActions.tsx:53、87 → trm-ui tip（toast） |
| E527 / community.signOutFailed | 退出登录失败，请重试。 | UI/components/CommunityActions.tsx:53、87 → trm-ui tip（toast） |
| E530 / publication.copyFailed | 未能复制 SHA-256。 | UI/components/CommunityModelDetail.tsx:71（tip toast） |
| E533 / publication.packReadError | 无法读取或导出模型包。 | UI/components/CommunityBatchPublisher.tsx:272（Warn）；UI/components/ExportVoicePackages.tsx:71（Warn） |
| E542 / raw.pack.export | 动态：每个导出包的文件、ZIP、JSON 错误 | UI/components/ExportVoicePackages.tsx:81（逐条正文） |
| E546 / mobile.failed | 操作失败，请重试。 | UI/components/MobileSection.tsx:112（alert） |
| E568 / s.storageScanFailed | 存储信息刷新失败，请重新统计。 | UI/components/StorageSection.tsx:182（状态/错误正文） |
| E569 / s.selfCheckFailed | 检查未能完成，请稍后重试。 | UI/pages/MorePage.tsx:455（状态/错误正文） |
| E570 / s.sumCopyFailed | 复制失败，请重试。 | UI/pages/MorePage.tsx:448（ListItem desc）；UI/pages/ModelsPage.tsx:1109→527（toast） |
| E571 / s.7fae0289b6 | 生成诊断包失败：{v0} | UI/pages/MorePage.tsx:483（ListItem desc） |
| E572 / s.diagShotUnreadable | 「{}」无法读取为图片，未添加。 | UI/components/DiagnosticsDialog.tsx:285（截图选择状态正文） |
| E574 / s.valueFailed | 读取失败 | UI/pages/MorePage.tsx:311、321（软件版本/安装位置字段） |
| E575 / raw.storage.clean | 动态：unknown storage kind: {bad}；异步任务/IPC 失败。实际删除失败仅记录日志。 | UI/components/StorageSection.tsx:249（正文） |
| E580 / s.84256012c6 | 性能测试启动失败：{e} | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） |
| E581 / s.470a002848 | 性能测试失败（退出码 {a0}），详见 User_Data/logs/perf_bench.log | UI/pages/MorePage.tsx:483（诊断结果/perf_note 正文） |
| E582 / raw.diagnostics.pack | 动态：文件创建/ZIP 打包/图片读取错误（外包 s.7fae0289b6） | UI/pages/MorePage.tsx:483（ListItem 描述） |
| E583 / s.eea9655c7b | 性能测试未完成：{e} | UI/pages/MorePage.tsx:483（生成诊断包结果中的 perf_note） |
| E585 / s.f1f3d2302b | 启动失败：{e} | UI/pages/MorePage.tsx:505、512（ListItem 描述） |
| E588 / s.ea582ad463 | 启动失败：{v0} | UI/pages/MorePage.tsx:505、512（ListItem 描述） |
| E589 / s.61f43bf584 | 界面出错了 | UI/components/ErrorBoundary.tsx:63、64（整页错误提示） |
| E591 / raw.ui.render | 动态：JavaScript error.stack / componentStack / String(error) | UI/components/ErrorBoundary.tsx:97（整页 pre，默认展开） |
| E592 / literal.boot.resource | 界面资源载入失败<br>{URL} 未能载入 | app/index.html:87、91（启动页标题 + 展开详情） |
| E593 / literal.boot.script | 界面脚本出错<br>{e.message &#124;&#124; "unknown"}<br>{filename}:{lineno}<br>{stack} | app/index.html:87、91（启动页标题 + 展开详情） |
| E594 / literal.boot.rejection | 界面出错<br>{reason.message + stack 或 String(reason)} | app/index.html:87、91（启动页标题 + 展开详情） |
| E595 / literal.boot.timeout | 界面加载超时<br>8 秒内界面没有挂载；脚本没有报错。 | app/index.html:87、91（启动页标题 + 详情） |
| E597 / s.kiAsioCrashTitle | 读取音频设备列表时出错 | UI/App.tsx:1498（Nudge 标题）；UI/components/FindingList.tsx:79（结论标题） |
| E614 / record.enum | 枚举输入设备失败：{e} | UI/components/TtsPanel.tsx:2233（ErrorNote）；:2253（失败条目理由，不折叠） |
| E618 / raw.cover.io | 动态：本地读取/远程请求/图片保存错误 | app/node_modules/trm-ui/lib/index.js:6425（ImageCropDialog alert）；社区首次打开失败另映射 publication.coverError |
| E620 / legacy.auto_start | 自动开始音频转换失败<br><br>{type(e).__name__}: {e}<br><br>请检查输入/输出设备，或手动点「开始音频转换」。 | gui_v1.py:864（PySimpleGUI popup_error） |
| E635 / legacy.faq.load | 动态：FAQ Markdown 文件读取失败的 traceback | infer-web.py:1562（gr.Markdown） |
| E641 / nsis.webview2DownloadError | 错误：无法下载 WebView2 - $0 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:22 |
| E642 / nsis.webview2InstallError | 错误：安装 WebView2 时失败，错误代码：$1 | NSIS 标准模板的提示框/安装详情；本仓库语言绑定：app/src-tauri/nsis-languages/SimpChinese.nsh:25 |
| E647 / install_move.read | 读取 {} 失败：{e} | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） |
| E651 / install_move.move | 搬移 {} 失败：{e}。原位置未改动。 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） |
| E652 / install_move.rewrite | 更新设置里的路径失败：{e}。原位置未改动。 | app/src-tauri/installer-hooks.nsh:130（$R3 搬移报告正文） |
| E663 / gradio.callback | Error | Runtime/Lib/site-packages/gradio/templates/frontend/assets/index.990b6b98.js:77（输出组件错误状态） |
| E665 / gradio.network | Connection errored out. | Runtime/Lib/site-packages/gradio/templates/frontend/assets/index.990b6b98.js:77（输出组件状态） |

## 错误分类、转译、折叠和修复动作

| helper / 位置 | 匹配或判据 | 输出/显示事实 |
| --- | --- | --- |
| R/download.rs:189 explain_error | 按顺序匹配小写原文：sha256/signature；os error 112/no space left/not enough space；os error 5/access is denied/permission denied；11001/dns/failed to lookup；tls/handshake/certificate；429/too many requests；4xx/forbidden；5xx/bad gateway/service unavailable；timeout/10060；reset/10054/broken pipe；10061/unreachable/error sending request。 | 分别转为 hash、disk、permission、DNS、TLS、busy、refused、server、timeout、reset、unreachable 文案；未命中返回 None。 |
| R/download.rs:117 is_transient_download_error | 取消、401/403/404/410、sha256 不重连；500/502/503/504/429 与连接、DNS、TLS、timeout、reset、broken pipe、unexpected end of stream、10053/10054/10060/10061/11001 等可重试。 | 影响重试与 s.dlReconnect；不是所有错误都自动重试。 |
| R/download.rs:237 plain_error / :254 download_error_text | plain_error：先记录原文，未识别用 s.netUnknown；download_error_text：识别则中文首行，未识别直接原文首行。 | 下载详情附源列表、次数、帮助、技术原文。Extras/Store 不折叠；compact ErrorNote 折叠首行之后内容。 |
| R/provision.rs:690 extract_error_text | 复用 explain_error；未命中用 s.rtExtractFailed。 | 追加 s.rtExtractHelp 和 s.dlDetail；在 ProvisionGate 中后两段折叠。 |
| tools/train_worker.py:609 log_has_oom | 读取 train.log 最后 8000 字，小写匹配 outofmemoryerror / out of memory / 显存。 | 缺最终权重时改报 train.oom；本版本函数名不是 _looks_like_oom。 |
| R/train.rs:683 preprocess_tally / :705 preprocess_failure_list | 识别制表符后的 -&gt; Success / -&gt; 失败块；原因取最后非空行，跳过 start/end preprocess 和 Fail. 标记。 | 清单最多 20 项，每条原因最多 200 字；TrainPanel:821 直接显示该原因。 |
| tools/sts_core.py:64 friendly_error | OOM → 固定中文指引；已有“显存不够”/“缺少 hubert”原样；DML → 中文说明 + 原始末行；traceback → 最后错误行 + 全文；其他原样。 | 同一文本经 ErrorNote 与失败条目列表显示时，折叠行为不同。 |
| tools/sts_core.py:97、114、124、151、156、786 | OOM：显存不够/out of memory；DML：privateuse1/privateuseone/directml/dml backend，或 DML 模式的裸 RuntimeError；traceback：开头 Traceback 或 File 行。 | 选择降级档；OOM 下调一档，DML 转 CPU；产生 sts.degraded。 |
| infer/lib/safe_load.py:109、126 | 反序列化失败；不是 dict；包含 model/optimizer/iteration/learning_rate 训练存档键；缺 weight/config。 | 构造中文 RuntimeError；底层异常或 traceback 仍可能随调用链进入正文。 |
| tools/record_worker.py:193、207 / R/mic.rs:66 | PortAudio、error opening、invalid device、device unavailable、unanticipated host error → busy。Rust mic 映射 busy/notfound/nolib/silent/enum/open。 | 麦克风测试用本地化文案，未知 code 回退原 message；STS 录音使用 t_worker_msg，不能以普通 code 字段完成该映射。 |
| R/crash.rs:56、61、75 / R/audio_probe.rs:71 | &gt;= 0xC0000000 为 fatal；识别访问冲突、除零、非法指令、栈溢出、缺 DLL、中断等 NTSTATUS。探测只对 Crashed 拦截。 | 显示十六进制退出码及已知名称；可追加注册 ASIO 列表。探测超时/普通失败本身放行。 |
| R/known_issues.rs:96、149 | 版本范围、fixed_in、OS、后端、GPU/ASIO 名包含匹配、requires_fatal。当前内置表只有 realtek-asio-enum-crash。 | 命中后本地化 title_key/body_key；App Nudge 和 selfcheck 共用。 |
| R/selfcheck.rs:53、119、162、168、185、277、304、331 | G_/D_数字.pth；切片/F0/特征数量不一致；预处理失败行；训练尾部 OOM；仅部分底模缺失；磁盘 &lt; 10 GiB；MME 延迟 &gt; 600 ms；欠载 &gt; 20；fatal/已知问题。 | Finding 标题与证据。原文日志片段位于证据行，不替代标题。 |
| UI/lib/trouble.ts:16 | 有序正则：缺音色/模型；runtime/python.exe/运行时/not_ready/missing_python；out of memory/cuda memory/显存不足/vram；PortAudio/device/-999x/设备/采样率/WASAPI/MME；其他 unknown。 | App 显示独立 Nudge，引导音色、运行环境、设备、性能或自检；Dock 的原错误仍保留。 |
| UI/components/AudioRecovery.tsx:28 | status.error/message 匹配 audio/device/portaudio/asio/声卡/设备/音频/繁体同义词/0xc000 且 state=error。 | 默认显示固定恢复说明；用户点击恢复后返回的错误才写入 banner 的 error。 |
| R/tearing.rs:27、31、38、42、46、49、88、96 | 20 秒热身；10 秒窗口；欠载 &gt;= 5 且比例 &gt;= 25%；连续 2 个窗口；15 秒冷却；还能提高块长。 | 返回 AskBlock，界面询问是否放宽延迟。 |
| R/i18n.rs:405、416、456 | message_code 加 msg. 前缀查语言包，参数插值；code 为空或未登记回退 worker message；sts.degraded 的 why/rung 单独翻译。 | localize_status 只替换 message，不替换 error；不能据 message 已翻译断言正文无原始异常。 |
| app/node_modules/trm-ui/lib/fabric.js:1 / UI/components/ErrorNote.tsx:51 | 去空行；首行 Traceback 或任一 File "..." 行 → 最后非 File/Traceback 行作 head，全文 detail；普通文本首行 head，其余 detail。 | 普通版支持复制全文/打开日志/动作按钮；compact 只有 details；error=false 全文直显。此处核对的是实际导入的 trm-ui/fabric。 |
| UI/lib/errorActions.ts:33、91 | train.pretrained_missing/rmvpe_missing/mute_missing → 下载 train；train.no_feature → 下载 all；train.no_slices/no_f0/no_samples → 训练说明；runtime.not_ready/missing_python、engine.missing_gui → 下载 all；sts.model_is_archive → 打开训练工具。 | 仅普通 ErrorNote 收到 code 时生效；TrainingQueue:55 另给 train.oom 调小批大小。Dock 不使用 ErrorNote。 |
| UI/components/FindingList.tsx:34、45 | assets.pretrained_partial → 下载；engine killed、train OOM、audio underrun/MME → 对应 FAQ；模型检查点/训练数量/预处理失败 → 训练说明。 | 没有映射的 Finding 无修复按钮。 |
| UI/pages/AudioPage.tsx:279 / AudioHotkeyEditor.tsx:86 / SettingsPage.tsx:1272 | 音频错误字符串按编号、裁剪、设备、引擎占用、容量、重新定位、导出冲突、组件缺失等 code 映射；未知 → audio.operationFailed。快捷键 conflict/registration_failed → 冲突/占用，其余保存失败。 | 音频库正文不直接显示底层异常；试听、波形、语音输出状态另有固定兜底。 |
| UI/lib/communityPublication.ts:340 | unauthorized/auth_required；submit 的 read_source/conflict/not_found；source_changed；invalid_cover；unchanged_package/version；hash_mismatch；rate_limited；resolve 的 unsupported/not_found/auth_required。 | 转固定文案；其他一律 publication.requestFailed。API message 不透传；审核 reason 与导出包 error 是另外的显示路径。 |
| UI/lib/communityBatch.ts:25、31 | rate_limited 的 retry_after_seconds（带边界）触发等待后重试。 | 最终错误仍经 publicationError；批量稿件保留 retryQueued。 |
| R/model_versions.rs:284 | 轮次切换 I/O 错误调用 install_error；完整性检查可直接用 installFailed。 | I/O 分支是固定“切换模型失败。” + 原始 error，纯完整性失败无原文。 |
| R/catalog.rs:155、171 | 错误不含 “: HTTP ” 且不以 “JSON ” 开头则判断为传输失败。 | 仅连接失败等延迟 800 ms 重试一次；HTTP/JSON 错误直接返回。 |
| R/vcredist.rs:59 classify_exit | 0 成功；1638 已有更高版本；3010 成功但需重启；1602/1223 取消；1618 其他安装占用；其他失败。 | 只有后三类进入本地化错误正文，保留退出代码。 |
| UI/lib/voiceApply.ts:28 vcApplyError | state=error 或 state 不是 running；优先 st.error，再 st.message，最后 msg.vc.start_failed / msg.vc.need_model。 | 选音色流程可将 worker 原 error 包成 Error，再经 ModelsPage/HomePage toast 显示。 |
| UI/components/ProvisionGate.tsx:38 isCancelError | 包含当前语言“已取消”或小写 cancel。 | 补全取消走暂停/取消处理，与下载失败的显示状态分开。 |
| R/telemetry.rs:170 error_kind | sha256、timeout/10060、dns/11001、tls/handshake/certificate、status 4、status 5/bad gateway/unavailable、reset/connection/10054，其他 other。 | 仅遥测类别，不改屏幕错误正文。 |
| tools/worker_protocol.py:66 _is_retryable_replace_error | PermissionError；OSError winerror 5/32 或 errno 13/11/16。 | 状态文件替换重试；最终退回原位写入；不产生独立用户文案。 |

## 日志位置与打开/复制入口

`<root>` 为产品根目录；`<UD>` 通常为 `<root>/User_Data`，Rust 的 paths::user_data 在仅存在旧目录时仍可返回 `UserData`。下表区分完整 stderr、包装后的错误和仅返回给前端的异常；没有日志写入的链路不宣称能从日志取到完整错误。打开日志目录与复制错误文本是不同动作。

| 功能 | 路径/记录内容 | 写入位置 | UI 打开/复制 |
| --- | --- | --- | --- |
| 统一日志布局 | &lt;UD&gt;/logs/&lt;channel&gt;/YYYY-MM-DD.log；任务为 &lt;UD&gt;/logs/&lt;channel&gt;/&lt;channel&gt;_YYYYMMDD_HHMMSS[_pid].log；超过 2 MiB 轮换 .log.1，启动按 48 小时清理。 | R/paths.rs:75、87; R/logging.rs:32、34、68、76、87 | 普通 ErrorNote 打开 &lt;UD&gt;/logs、复制传入错误全文；MorePage:500 打开同目录。都不是复制日志文件内容。 |
| 实时变声 / DSP / 音频设备枚举 | &lt;UD&gt;/logs/worker/YYYY-MM-DD.log；Python tee 固定用 User_Data/logs/worker/YYYY-MM-DD.log，含 stdout/traceback；状态快照在 &lt;UD&gt;/runtime_control/status.json。 | R/worker.rs:23、937; tools/realtime_worker.py:38、57 | Dock/Overlay 没有复制错误/打开日志按钮；可运行自检；MorePage 打开日志、生成诊断包。 |
| 训练 worker / 模型处理工具 | &lt;UD&gt;/logs/train/train_YYYYMMDD_HHMMSS[_pid].log；stderr、进度、outcome。 | R/train.rs:1439; R/ckpt.rs:91、165 | 普通 ErrorNote 复制错误/打开日志；队列失败项提供；查看模型信息 error=false 没有这些按钮。 |
| 训练预处理 / F0 / 特征 / 训练 | &lt;root&gt;/logs/&lt;exp&gt;/preprocess.log、extract_f0_feature.log、train.log。 | R/train.rs:49、1262; tools/train_worker.py:553、629、659、750 | 预处理失败文件清单可展开；ErrorNote 打开的仍是 &lt;UD&gt;/logs，不是根目录 logs/&lt;exp&gt;。当前队列没有旧文案所述“底部日志”面板。 |
| 语音转换（冷/热路径） | &lt;UD&gt;/logs/sts/sts_YYYYMMDD_HHMMSS[_pid].log；热路径还写 worker 日志；失败条目及总体结果进入 RunTrace。 | R/sts.rs:1650; tools/sts_worker.py:549; gui_v1.py:4136 | ErrorNote 复制错误/打开日志；条目清单无独立复制按钮；可仅重试失败项。 |
| STS 录音 | 任务摘要 &lt;UD&gt;/logs/sts/sts_*.log；录音进程 stderr → &lt;UD&gt;/logs/sts/YYYY-MM-DD.log。 | R/sts.rs:876、991 | 录音错误进入 STS ErrorNote，复制错误/打开日志。 |
| 麦克风测试 | 进程 stderr → &lt;UD&gt;/logs/sts/YYYY-MM-DD.log；测试失败事件经 mic::message_for 本地化。 | R/mic.rs:66、94、142 | MicTest/LinkCheck 仅显示结果和重试；没有独立错误复制/日志按钮。MorePage 可打开目录。 |
| SAPI 文本转语音 | &lt;UD&gt;/logs/tts/tts_*.log；RVC 后处理另有 STS 日志。PowerShell stderr 被 Stdio::null 丢弃，日志只能保留包装后的失败。 | R/tts.rs:179、184、320、368、475 | TtsPanel 普通 ErrorNote 支持复制错误/打开日志。 |
| 人声分离 | &lt;UD&gt;/logs/separate/separate_*.log；PyMSS stderr 与 detail 写 RunTrace。 | R/separate.rs:167、387; tools/separate_worker.py:151 | SeparatePanel 普通 ErrorNote 支持复制错误/打开日志。 |
| 下载 / 环境补全 / 更新 / 社区 | &lt;UD&gt;/logs/shell/YYYY-MM-DD.log：plain_error 等显式日志；下载条目记录和 progress 不是完整异常日志的保证。 | R/download.rs:237; R/provision.rs:690; R/update.rs:480、499; R/logging.rs:51 | ProvisionGate/AudioToolsDialog compact 仅展开详情；Extras/Store/Update 提示不提供复制错误/日志按钮；MorePage 全局打开日志。 |
| 音色/档案/封面/轮次 / DSP | 删除与特定操作有 shell_log；许多 map_err(e.to_string()) 只返回给调用者，无专用完整日志文件。 | R/voices.rs:214、2111、2123; R/model_versions.rs:284; R/dsp.rs:167 | toast、裁剪对话框、DSP 文本无专用复制日志按钮；MorePage 是全局入口。 |
| 音频库 / 播放 / 裁剪 / 波形 | 不少底层失败只返回 code/异常，前端替换固定文案；audio_edit 捕获 ffmpeg stderr 后附加至裁剪错误，未看到持久化该 stderr 的写入。API audio_mix 单独写 &lt;output&gt;/&lt;job-id&gt;.ffmpeg.log。 | R/audio_edit.rs:186、193、265、272; R/audio_mix.rs:78; UI/pages/AudioPage.tsx:279 | AudioPage/AudioTrim 无专用复制错误/日志按钮；API 混音日志没有此仓库桌面页面的直接入口。 |
| 社区投稿 / 账户 / 包导出 | 社区 API 错误经 publicationError 隐去 raw message；逐包导出 error 保留在结果及导出 manifest 的处理过程中，成功清单 write_manifest 过滤失败项；无统一完整异常日志保证。 | R/community_publish.rs:223; R/publication_packs.rs:120; UI/lib/communityPublication.ts:340 | 投稿详情可看审核 reason；包导出可重试失败项；没有独立打开日志/复制异常按钮。 |
| 设备恢复 / 移动端 | 恢复中的下载可能走 shell 日志；设备探测输出在缓存 JSON；多数文件/IPC 错误只返回。移动端桌面 UI 统一 mobile.failed，不显示其 error 原文。 | R/audio_recovery.rs:56、76; UI/hooks/useMobile.ts:36; UI/components/MobileSection.tsx:112 | 无该错误的专用日志按钮；MorePage 全局日志/诊断入口。 |
| 性能测试 / 诊断包 / 清理 | 性能进程 stderr → &lt;UD&gt;/logs/bench/YYYY-MM-DD.log；报告 &lt;UD&gt;/perf_reports/；诊断包 &lt;UD&gt;/diagnostics/*.zip；删除失败记 shell 日志，清理可继续返回释放字节数。 | R/shell_extras.rs:633、636、1350; R/train.rs:611; R/paths.rs:628 | MorePage:493 打开性能报告、:500 打开日志、:487 生成诊断包；Storage 仅统计/清理。 |
| 启动页 / React ErrorBoundary | ui_log → shell 日志；ErrorBoundary componentDidCatch 写 stack；ErrorNote 本身不写日志。 | app/index.html:71、84; UI/components/ErrorBoundary.tsx:38、43; UI/components/ErrorNote.tsx:92、122 | 启动页无按钮；ErrorBoundary 可生成诊断包/关闭，stack 默认展开；普通 ErrorNote 只复制状态文本。 |
| 原版实时面板 / 原版 WebUI | &lt;UD&gt;/logs/realtime_gui.log、webui.log，detached 进程 stderr 重定向；stdout 丢弃。训练日志另在 &lt;root&gt;/logs/&lt;exp&gt;/。 | R/legacy.rs:42、56、102、141; infer-web.py:250、341 | 原版文本框/弹窗无 RVC Fabric 的复制错误/打开日志按钮；MorePage:500 提供外部入口。 |
| 安装搬移 / NSIS | 插件临时目录中的 MoveReport 保存搬移错误供 MessageBox 读取；没有永久错误日志路径保证。 | app/src-tauri/installer-hooks.nsh:117、125、130; R/install_move.rs:246 | 提示框只有确定；没有复制/打开日志动作。 |
| 路径文本与实际写入的差异 | s.wkReadyTimeout 等仍写 realtime_worker.log；s.6b7047af91 写 separate.log；s.470a002848 写 perf_bench.log；启动 HTML 写 shell.log。实际分别为 worker/日期.log、separate/单次.log、bench/日期.log、shell/日期.log。 | R/worker.rs:937; R/separate.rs:167; R/shell_extras.rs:636; R/logging.rs:68; app/index.html:89 | 表中文字按语言包原文保留；没有把旧提示路径改成新路径。 |

## 未重复计入与可见性边界

| 范围 | 文案/代码 | 依据 | 当前事实 |
| --- | --- | --- | --- |
| 训练进度的非终态失败/降级文本 | msg.train.preprocess_partial / no_feature_dir / no_feature_file / kmeans_failed / index_failed / reuse_sr / resume_f0_partial / resume_feature_partial | tools/train_worker.py:581、793、798、825、853、960、991、1004 → R/train_queue.rs:222 | 队列保留进度，但 UI/components/TrainingQueue.tsx:47 只渲染阶段名及计数；:55 只显示 failed 状态的 job.error。当前无进度正文，故不计主表。 |
| 训练 cancelled | msg.train.cancelled / s.a5ffdc95ee | tools/train_worker.py:1015; R/train_queue.rs:319 | 主动取消转 cancelled 标签；不是失败正文。主表保留通过 catch 显示的音频播放/运行库取消提示。 |
| 只有日志的字符串 | s.1db2e283ac / s.27ecfba771 / s.75af179e2d / s.298dd55e6d / s.324ed94533 | UI/components/ErrorBoundary.tsx:43; R/window_watch.rs:141、546; R/lib.rs:2088; R/legacy.rs:95 | ui_log / shell_log / worker log；对应错误页的实际标题与 stack 已分别列主表。 |
| 工具窗打开失败 | s.toolMainWindowGone / s.22a95f37e3 / s.c1c11dd8f6 / s.79a71841b6 | R/tool_window.rs:197、231、258、289 → UI/components/ToolWindow.tsx:67、81; UI/lib/downloadModels.ts:63 | 当前调用方 catch 后不显示；没有将后端每个 Err 自动计为用户可见。 |
| 托盘初始化 | tray.missingIcon | R/shell_extras.rs:53 | 构建托盘返回错误，没有找到该字符串对应的应用页面渲染。 |
| 能力说明未被调用 | s.capNeedNvidia / s.capNeedGpu / s.capCpuFallback | UI/lib/engine.ts:154、170、172、174 | capabilityLines 在当前源码只有定义，无调用点；不列为当前可见说明。 |
| 咨询包入口隐藏 | neptune.consultPartial / s.consultNeedRecording / consult 文件与 ZIP 原始错误 | UI/pages/MorePage.tsx:32、516; UI/components/ConsultDialog.tsx:130、232; R/consult.rs:144、300、307、347 | SHOW_CONSULT=false；组件保留但当前页面没有可达打开入口。错误保存在 consult.json 的 conversion_failures 或返回 ErrorNote 的分支未计主表。 |
| 仅复制/诊断包中的错误字段 | s.sumNo / s.sumLastError / s.lcHelpError | R/shell_extras.rs:1295; UI/components/LinkCheckDialog.tsx:291 | 诊断摘要或求助文本，当前页面不渲染正文；不混入屏幕消息数。 |
| 自检证据中的原始片段 | preprocess.log 失败首行 / train.log OOM 末行 | R/selfcheck.rs:246、262 → UI/components/FindingList.tsx:89 | 屏幕可见，但作为结论下方证据；主表按各 Finding 标题计行，不把证据误标为主标题原始透传。 |
| 原版 WebUI 索引预检 | 请先进行特征提取! / 请先进行特征提取！ | infer-web.py:633、636 | train_index 是 generator，这两处分支 return 字符串而非 yield；该返回值不作为文本框输出。 |
| 一般帮助与空态 | FAQ、参数 tip、搜索无匹配、未发布模型、正常外部模型标记、恢复成功 | UI/pages/HelpPage.tsx; UI/pages/ModelsPage.tsx; UI/components/CommunityModelList.tsx | 非运行中错误/失败反馈；未作为错误行。材料预检、缺组件、设备断开和自动降级警告已计入主表。 |
| 不存在独立界面入口的功能 | 独立标注 / ASR；外部 Fabric API 错误响应 | app/src/; R/audio_mix.rs:62 | 仓库桌面页面没有独立标注/ASR 面板；切片属于训练预处理。API JSON 错误不直接渲染到本仓库 UI；仅列已追到屏幕的调用链。 |
| 启动监听器作用范围 | app/index.html 的 error / unhandledrejection / timeout | app/index.html:81、85、118、133 | React 移除 #boot 后 fail 仅写 shell 日志，不再绘制启动错误页；不能将任意未捕获 Promise 都算作始终可见。 |

## 校验记录

| 检查 | 结果 |
| --- | --- |
| 应用语言包原文 | 主清单所有有 key 的文本均与当前 zh-CN.json 对照；无对应条目的内容单独标注。 |
| 代码只读 | 对初始读取的 387 个源码/配置文件重新计算 SHA-256，均未变化。 |
| 工作区 | 开始盘点时 git status 为空；本次只新增本报告，不执行 git commit。 |
| 动态验收 | 未运行 UI、Python worker、设备或安装流程；文案与按钮结论来自源码链路。 |


