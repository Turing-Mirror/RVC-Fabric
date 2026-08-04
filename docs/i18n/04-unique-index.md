# 去重原文索引

同一句中文只出现一次；「出处」列出所有出现位置。
翻译时可按本表建 key，避免同一句多种译法。

去重后共 **429** 条（含前端 / Rust / 引擎）。

| # | 原文（zh-CN） | 出现次数 | 出处（首条） |
|---:|---|---:|---|
| 1 | Runtime 未就绪，请先补全运行时 | 4 | rust `app/src-tauri/src/lib.rs:491` 等 4 处 |
| 2 | 写请求文件失败：{e} | 3 | rust `app/src-tauri/src/separate.rs:167` 等 3 处 |
| 3 | 建不了输出目录：{e} | 3 | rust `app/src-tauri/src/separate.rs:150` 等 3 处 |
| 4 | 特征提取 | 2 | python `tools/train_worker.py:281` 等 2 处 |
| 5 | 缺请求文件参数 | 2 | python `tools/separate_worker.py:47` 等 2 处 |
| 6 | 训练 | 2 | python `tools/train_worker.py:379` 等 2 处 |
| 7 | 请求文件读不了：{e} | 2 | python `tools/separate_worker.py:52` 等 2 处 |
| 8 | ${Math.floor(m / 60)} 小时 ${m % 60} 分 | 1 | frontend `app/src/components/ProvisionGate.tsx:42` |
| 9 | ${label}失败：${String(e)} | 1 | frontend `app/src/pages/MorePage.tsx:102` |
| 10 | ${label}完成：${r?.path ?? ""}${note} | 1 | frontend `app/src/pages/MorePage.tsx:100` |
| 11 | ${m} 分 ${s % 60} 秒 | 1 | frontend `app/src/components/ProvisionGate.tsx:41` |
| 12 | ${p.message \|\| p.phase \|\| "下载中"} ${<br>          p.percent != null ? | 1 | frontend `app/src/components/StoreSection.tsx:124` |
| 13 | %s失败（退出码 %s），详情见 %s | 1 | python `tools/train_worker.py:214` |
| 14 | === RVC Fabric {} 启动（pid {}）=== | 1 | rust `app/src-tauri/src/lib.rs:1212` |
| 15 | >=3则使用对harvest音高识别的结果使用中值滤波，数值为滤波半径，使用可以削弱哑音 | 1 | python `infer-web.py:923` |
| 16 | A模型权重 | 1 | python `infer-web.py:1452` |
| 17 | A模型路径 | 1 | python `infer-web.py:1444` |
| 18 | B模型路径 | 1 | python `infer-web.py:1447` |
| 19 | E:\语音音频+标注\米津玄师\src | 1 | python `infer-web.py:1230` |
| 20 | F0曲线文件, 可选, 一行一个音高, 代替默认F0及升降调 | 1 | python `infer-web.py:938` |
| 21 | Main app sets TM_AUTO_START_VC=1 when user clicks 开启变声. | 1 | python `gui_v1.py:710` |
| 22 | Onnx导出 | 1 | python `infer-web.py:1596` |
| 23 | Onnx输出路径 | 1 | python `infer-web.py:1603` |
| 24 | RVC模型路径 | 1 | python `infer-web.py:1599` |
| 25 | Runtime 就绪 | 1 | rust `app/src-tauri/src/provision.rs:364` |
| 26 | Runtime 就绪，但缺少 tools/realtime_worker.py | 1 | rust `app/src-tauri/src/provision.rs:362` |
| 27 | Runtime 已就绪，跳过下载 | 1 | rust `app/src-tauri/src/provision.rs:444` |
| 28 | Runtime 已就绪，跳过下载。 | 1 | rust `app/src-tauri/src/provision.rs:447` |
| 29 | Runtime 未就绪 | 1 | rust `app/src-tauri/src/lib.rs:851` |
| 30 | Runtime 未就绪（缺少 torch） | 1 | rust `app/src-tauri/src/lib.rs:509` |
| 31 | Runtime 未就绪，无法开启变声 | 1 | rust `app/src-tauri/src/lib.rs:525` |
| 32 | Runtime 未就绪，无法跑性能测试 | 1 | rust `app/src-tauri/src/shell_extras.rs:266` |
| 33 | Runtime 未就绪，请先在首次运行向导里补全运行时 | 1 | rust `app/src-tauri/src/legacy.rs:29` |
| 34 | Runtime 未就绪，请先补全运行环境 | 1 | rust `app/src-tauri/src/train.rs:212` |
| 35 | Runtime 补全完成 | 1 | rust `app/src-tauri/src/provision.rs:635` |
| 36 | WARNING: 安装路径含中文/特殊字符，部分组件可能异常，建议移到纯英文路径 | 1 | python `gui_v1.py:32` |
| 37 | Windows 管道下 stdout 常是系统代码页，中文 JSON 会 OSError 22。 | 1 | python `tools/sts_worker.py:60` |
| 38 | ckpt处理 | 1 | python `infer-web.py:1439` |
| 39 | connecting:{} · {} 连接 · 建立连接… | 1 | rust `app/src-tauri/src/download.rs:250` |
| 40 | connecting:{} · 请求服务器… | 1 | rust `app/src-tauri/src/download.rs:284` |
| 41 | cwd 切到产品根、加载 .env、补齐 RVC 路径（相对路径改成绝对路径）。 | 1 | python `tools/sts_worker.py:70` |
| 42 | download:{} · {} 连接 · 已连接 | 1 | rust `app/src-tauri/src/download.rs:162` |
| 43 | force_kill: 重写音色配置失败：{e} | 1 | rust `app/src-tauri/src/lib.rs:773` |
| 44 | harvest进程数 | 1 | python `gui_v1.py:619` |
| 45 | kill_tree pid={pid} (我们记录的 pid，镜像路径没匹配上) | 1 | rust `app/src-tauri/src/worker.rs:414` |
| 46 | load: 设备刷新失败，保留已保存的配置 | 1 | python `gui_v1.py:357` |
| 47 | pth文件不存在 | 1 | python `gui_v1.py:952` |
| 48 | rmvpe卡号配置：以-分隔输入使用的不同进程卡号,例如0-0-1使用在卡0上跑2个进程并在卡1上跑1个进程 | 1 | python `infer-web.py:1278` |
| 49 | sha256 不匹配<br>期望 {exp}<br>实际 {got} | 1 | rust `app/src-tauri/src/download.rs:83` |
| 50 | skip kill pid={pid} (不是 python 进程，可能是复用的 pid) | 1 | rust `app/src-tauri/src/worker.rs:420` |
| 51 | step1: 填写实验配置. 实验数据放在logs下, 每个实验一个文件夹, 需手工输入实验名路径, 内含实验配置, 日志, 训练得到的模型文件. | 1 | python `infer-web.py:1189` |
| 52 | step1:正在处理数据 | 1 | python `infer-web.py:753` |
| 53 | step2:正在提取音高&正在提取特征 | 1 | python `infer-web.py:757` |
| 54 | step2a: 自动遍历训练文件夹下所有可解码成音频的文件并进行切片归一化, 在实验目录下生成2个wav文件夹; 暂时只支持单人训练. | 1 | python `infer-web.py:1224` |
| 55 | step2b: 使用CPU提取音高(如果模型带音高), 使用GPU提取特征(选择卡号) | 1 | python `infer-web.py:1251` |
| 56 | step3: 填写训练设置, 开始训练模型和索引 | 1 | python `infer-web.py:1306` |
| 57 | step3a:正在训练模型 | 1 | python `infer-web.py:766` |
| 58 | tar 条目错误: {e} | 1 | rust `app/src-tauri/src/extract.rs:165` |
| 59 | {desc} · 相似度 {s:.2} | 1 | rust `app/src-tauri/src/voices.rs:1124` |
| 60 | {label} · 音高 {sign}{pitch} 共鸣 {formant:.2} | 1 | rust `app/src-tauri/src/voices.rs:743` |
| 61 | {src.name} 失败：{e} | 1 | python `tools/sts_worker.py:257` |
| 62 | {src.name} 转换失败：{info or '未知错误'} | 1 | python `tools/sts_worker.py:244` |
| 63 | {} Runtime 已安装 | 1 | rust `app/src-tauri/src/provision.rs:638` |
| 64 | {} 下载失败：{e} | 1 | rust `app/src-tauri/src/extra_assets.rs:440` |
| 65 | {} 落地失败：{e} | 1 | rust `app/src-tauri/src/extra_assets.rs:444` |
| 66 | 一次最多 {MAX_CHARS} 字，先分几段 | 1 | rust `app/src-tauri/src/tts.rs:239` |
| 67 | 一行一个 JSON。带锁是因为 tail 线程和主线程都会往 stdout 写。 | 1 | python `tools/train_worker.py:48` |
| 68 | 一键训练 | 1 | python `infer-web.py:1389` |
| 69 | 下载 {} Runtime v{}（约 {} · {} 连接） | 1 | rust `app/src-tauri/src/provision.rs:482` |
| 70 | 下载中 {} / {} · {} | 1 | rust `app/src-tauri/src/provision.rs:560` |
| 71 | 下载中 {} / {}（{:.1}%）· {} | 1 | rust `app/src-tauri/src/provision.rs:567` |
| 72 | 下载声卡安装包 {} / {}（{:.1}%） | 1 | rust `app/src-tauri/src/lib.rs:123` |
| 73 | 下载失败：{e} | 1 | rust `app/src-tauri/src/engine_assets.rs:149` |
| 74 | 下载引擎资源 {} / {}（{:.1}%） | 1 | rust `app/src-tauri/src/lib.rs:87` |
| 75 | 下载更新失败：{e} | 1 | rust `app/src-tauri/src/update.rs:238` |
| 76 | 不支持的采样率：%s | 1 | python `tools/train_worker.py:454` |
| 77 | 不支持的采样率：{} | 1 | rust `app/src-tauri/src/train.rs:218` |
| 78 | 临时清理（{phase}）root={}：删文件 {} 个、目录 {} 个，失败 {}，约 {:.1} MB | 1 | rust `app/src-tauri/src/paths.rs:264` |
| 79 | 主声音驱动 | 1 | python `gui_v1.py:1397` |
| 80 | 也可批量输入音频文件, 二选一, 优先读文件夹 | 1 | python `infer-web.py:1093` |
| 81 | 人声伴奏分离批量处理， 使用UVR5模型。 <br>合格的文件夹路径格式举例： E:\codes\py39\vits_vc_gpu\白鹭霜华测试样例(去文件管理器地址栏拷就行了)。 <br>模型分为三类： <br>1、保留人声：不带和声的音频选这个，对主人声保留比HP5更好。内置HP2和HP3两个模型，HP3可能轻微漏伴奏但对主人声保留比HP2稍微好一丁点； <br>2、仅保留主人声：带和声的音频选这个，对主人声可能有削弱。内置HP5一个模型； <br> 3、去混响、去延迟模型（by FoxJoy）：<br>  (1)MDX-Net(onnx_dereverb):对于双通道混响是最好的选择，不能去除单通道混响；<br>&emsp;(234)DeEcho:去除延迟效果。Aggressive比Normal去除得更彻底，DeReverb额外去除混响，可去除单声道混响，但是对高频重的板式混响去不干净。<br>去混响/去延迟，附：<br>1、DeEcho-DeReverb模型的耗时是另外2个DeEcho模型的接近2倍；<br>2、MDX-Net-Dereverb模型挺慢的；<br>3、个人推荐的… | 1 | python `infer-web.py:1132` |
| 82 | 人声分离 worker：跑一次 PyMSS，把进度按行吐给 Rust 侧。<br><br>为什么不直接调 `python -m tools.pymss.cli infer`：它的进度是 tqdm 画在<br>stderr 上的进度条，要靠正则去刮，格式一变就瞎。PyMSS 的 separator 本来就收<br>`progress_callback(done, total, message)`，接上它按行输出 JSON 干净得多。<br><br>用法（Rust 侧这么调）::<br><br>    pythonw tools/separate_worker.py <请求文件.json><br><br>请求文件::<br><br>    {"model": "...", "model_dir": "...", "input": "...", "output": "...",<br>     "device": "auto", "format": "wav"}<br><br>stdout 每行一条 JSON：<br>    {"phase":"start"}                          开始<br>    {"phase":"run","done":3,"total"… | 1 | python `tools/separate_worker.py:2` |
| 83 | 人声前倾 | 1 | python `tools/dsp_fx.py:40` |
| 84 | 人声提取激进程度 | 1 | python `infer-web.py:1153` |
| 85 | 以-分隔输入使用的卡号, 例如   0-1-2   使用卡0和卡1和卡2 | 1 | python `infer-web.py:1258` |
| 86 | 伴奏人声分离&去混响&去回声 | 1 | python `infer-web.py:1128` |
| 87 | 低沉厚实 | 1 | python `tools/dsp_fx.py:44` |
| 88 | 使用「${TITLES[kind]}」前，需要先下载引擎资源（hubert / rmvpe / ffmpeg，约 720 MB）。下载完成后即可打开工具。 | 1 | frontend `app/src/components/ToolWindow.tsx:37` |
| 89 | 使用本地缓存：{} | 1 | rust `app/src-tauri/src/provision.rs:511` |
| 90 | 使用模型采样率 | 1 | python `gui_v1.py:475` |
| 91 | 使用设备采样率 | 1 | python `gui_v1.py:482` |
| 92 | 保存名 | 1 | python `infer-web.py:1558` |
| 93 | 保存失败：${String(e)} | 1 | frontend `app/src/pages/MorePage.tsx:70` |
| 94 | 保存失败：{e} | 1 | rust `app/src-tauri/src/config.rs:411` |
| 95 | 保存的文件名, 默认空为和源文件同名 | 1 | python `infer-web.py:1520` |
| 96 | 保存的模型名不带后缀 | 1 | python `infer-web.py:1476` |
| 97 | 保存设置失败：{e} | 1 | rust `app/src-tauri/src/config.rs:345` |
| 98 | 保存频率save_every_epoch | 1 | python `infer-web.py:1312` |
| 99 | 保护清辅音和呼吸声，防止电音撕裂等artifact，拉满0.5不开启，调低加大保护力度但可能降低索引效果 | 1 | python `infer-web.py:913` |
| 100 | 修改 | 1 | python `infer-web.py:1526` |
| 101 | 修改模型信息(仅支持weights文件夹下提取的小模型文件) | 1 | python `infer-web.py:1507` |
| 102 | 停止失败 | 1 | python `gui_v1.py:2711` |
| 103 | 停止音频转换 | 1 | python `gui_v1.py:684` |
| 104 | 光标位置：{:.0},{:.0} | 1 | rust `app/src-tauri/src/window_watch.rs:143` |
| 105 | 全流程结束！ | 1 | python `infer-web.py:789` |
| 106 | 全部完成，共 {len(out_files)} 个 | 1 | python `tools/sts_worker.py:260` |
| 107 | 共 {total} 个文件 | 1 | python `tools/sts_worker.py:190` |
| 108 | 写不了文本文件：{e} | 1 | rust `app/src-tauri/src/tts.rs:134` |
| 109 | 写不了输出文件：{e} | 1 | rust `app/src-tauri/src/tts.rs:257` |
| 110 | 写入 inuse 配置失败：{e} | 1 | rust `app/src-tauri/src/config.rs:306` |
| 111 | 写入 {} 失败：{e} | 1 | rust `app/src-tauri/src/extract.rs:247` |
| 112 | 准备训练（%d 条样本）… | 1 | python `tools/train_worker.py:349` |
| 113 | 分离失败，详见日志 | 1 | python `tools/separate_worker.py:104` |
| 114 | 分离进程异常退出（{}）。详情见 User_Data/logs/separate.log | 1 | rust `app/src-tauri/src/separate.rs:250` |
| 115 | 切片与重采样… | 1 | python `tools/train_worker.py:230` |
| 116 | 删除失败：{e} | 1 | rust `app/src-tauri/src/store.rs:954` |
| 117 | 刷新音色列表和索引路径 | 1 | python `infer-web.py:837` |
| 118 | 加载 | 1 | rust `app/src-tauri/src/i18n.rs:234` |
| 119 | 加载模型 | 1 | python `gui_v1.py:404` |
| 120 | 加载模型失败：{e} | 1 | python `tools/sts_worker.py:206` |
| 121 | 加载预训练底模D路径 | 1 | python `infer-web.py:1361` |
| 122 | 加载预训练底模G路径 | 1 | python `infer-web.py:1356` |
| 123 | 单次推理 | 1 | python `infer-web.py:852` |
| 124 | 卸载音色省显存 | 1 | python `infer-web.py:839` |
| 125 | 压缩包{e} | 1 | rust `app/src-tauri/src/extract.rs:232` |
| 126 | 压缩包路径不安全：{name} | 1 | rust `app/src-tauri/src/extract.rs:237` |
| 127 | 参数已应用 | 1 | python `gui_v1.py:2810` |
| 128 | 发现新版本 ${String(r.remote)}，当前 ${String(r.local)} | 1 | frontend `app/src/App.tsx:112` |
| 129 | 变声中 | 1 | python `gui_v1.py:2683` |
| 130 | 变声中换音色。<br><br>            引擎原来根本不认 pth_path 这个热更新键：换模型只写了配置文件，正在跑<br>            的这个 worker 手里还攥着上一个模型，于是界面上名字变了、声音没变。<br>            上一版的做法是「停流再开流」—— 能换过去，但要几秒，设备重开，<br>            延迟设置重算，用户听到的是一段静音加一次咔哒。<br><br>            现在只换该换的那一件东西：RVC 实例。缓冲区的尺寸、音频进程、设备、<br>            SOLA 的窗口全都不动，因为它们只跟采样率有关，跟哪个音色无关。<br><br>            唯一换不了的情况是采样率真的会变 —— 只有「跟随模型」那档才可能，<br>            这时候整条流水线的几何尺寸都变了，老老实实重开。 | 1 | python `gui_v1.py:2459` |
| 131 | 变调(整数, 半音数量, 升八度12降八度-12) | 1 | python `infer-web.py:857` |
| 132 | 只读出这个权重的目标采样率，不建模型。<br><br>            换模型要不要重开流，只取决于采样率会不会变。为这一个数把整套<br>            RVC 建起来太贵，而 torch.load 出来的 cpt["config"][-1] 就是它。<br><br>            weights_only=True 是硬性的：.pth 是 pickle，允许它执行代码等于<br>            让任何一个从广场下下来的音色包在用户机器上跑任意程序。 | 1 | python `gui_v1.py:2443` |
| 133 | 合成完成：${r.file ?? ""} | 1 | frontend `app/src/components/TtsPanel.tsx:362` |
| 134 | 后处理重采样至最终采样率，0为不进行重采样 | 1 | python `infer-web.py:895` |
| 135 | 否 | 1 | python `infer-web.py:1334` |
| 136 | 含盘符路径：{name} | 1 | rust `app/src-tauri/src/extract.rs:47` |
| 137 | 启动 {}（pid {pid}），日志 {} | 1 | rust `app/src-tauri/src/legacy.rs:78` |
| 138 | 启动失败 | 1 | python `gui_v1.py:2700` |
| 139 | 启动失败：${String(e)} | 1 | frontend `app/src/pages/MorePage.tsx:91` |
| 140 | 启动失败：{e} | 1 | rust `app/src-tauri/src/legacy.rs:76` |
| 141 | 启动音频转换失败 | 1 | python `gui_v1.py:788` |
| 142 | 启用相位声码器 | 1 | python `gui_v1.py:665` |
| 143 | 响应阈值 | 1 | python `gui_v1.py:499` |
| 144 | 响度因子 | 1 | python `gui_v1.py:543` |
| 145 | 四类产物对不上号，没有一条可用的训练样本。建议清掉实验重来。 | 1 | python `tools/train_worker.py:304` |
| 146 | 处理数据 | 1 | python `infer-web.py:1240` |
| 147 | 备份旧界面失败：{e} | 1 | rust `app/src-tauri/src/update.rs:255` |
| 148 | 复制 .pth 失败: {e} | 1 | rust `app/src-tauri/src/voices.rs:1522` |
| 149 | 复制 pth: {e} | 1 | rust `app/src-tauri/src/store.rs:522` |
| 150 | 复制模型失败：{e} | 1 | rust `app/src-tauri/src/store.rs:1027` |
| 151 | 外部目录 {} | 1 | rust `app/src-tauri/src/ui_assets.rs:234` |
| 152 | 失败：${String(e)} | 1 | frontend `app/src/pages/HelpPage.tsx:186` |
| 153 | 安装不完整：缺少引擎主程序 | 1 | python `tools/realtime_worker.py:145` |
| 154 | 安装更新失败：{e} | 1 | rust `app/src-tauri/src/update.rs:434` |
| 155 | 完成 ${r.files?.length ?? 0} 个文件${r.output ? | 1 | frontend `app/src/components/TtsPanel.tsx:153` |
| 156 | 完成 {src.name} | 1 | python `tools/sts_worker.py:253` |
| 157 | 完成重命名失败: {e} | 1 | rust `app/src-tauri/src/download.rs:312` |
| 158 | 完成，输出 ${r.files?.length ?? 0} 个文件 | 1 | frontend `app/src/components/SeparatePanel.tsx:98` |
| 159 | 导出Onnx模型 | 1 | python `infer-web.py:1608` |
| 160 | 导出文件格式 | 1 | python `infer-web.py:1021` |
| 161 | 工具窗口地址不合法：{e} | 1 | rust `app/src-tauri/src/tool_window.rs:99` |
| 162 | 已停止 | 1 | python `gui_v1.py:2718` |
| 163 | 已取消 | 1 | python `tools/train_worker.py:532` |
| 164 | 已是最新版本 ${String(r.local)}（${clockNow()} 检查） | 1 | frontend `app/src/App.tsx:108` |
| 165 | 已更新至 ${String(b.version ?? r.remote)}，重启程序后生效 | 1 | frontend `app/src/App.tsx:125` |
| 166 | 已更新至 ${String(r.remote)}，重启程序后生效 | 1 | frontend `app/src/App.tsx:135` |
| 167 | 已有切片，跳过预处理 | 1 | python `tools/train_worker.py:513` |
| 168 | 已有特征，跳过 | 1 | python `tools/train_worker.py:525` |
| 169 | 已有音高，跳过 | 1 | python `tools/train_worker.py:520` |
| 170 | 已跑性能测试：{} | 1 | rust `app/src-tauri/src/shell_extras.rs:423` |
| 171 | 已退出 | 1 | python `gui_v1.py:2787` |
| 172 | 常见原因：模型路径无效、显存不足、声卡占用、index 损坏。 | 1 | python `gui_v1.py:791` |
| 173 | 常见问题解答 | 1 | python `infer-web.py:1613` |
| 174 | 常规设置 | 1 | python `gui_v1.py:592` |
| 175 | 平直 | 1 | python `tools/dsp_fx.py:39` |
| 176 | 广场内容：{e} | 1 | rust `app/src-tauri/src/plaza.rs:386` |
| 177 | 建不了工具窗口：{e} | 1 | rust `app/src-tauri/src/tool_window.rs:112` |
| 178 | 建不了目录：{e} | 1 | rust `app/src-tauri/src/extra_assets.rs:407` |
| 179 | 建不了缓存目录：{e} | 1 | rust `app/src-tauri/src/tts.rs:128` |
| 180 | 建检索索引。<br><br>    这段原版写在 infer-web.py 里且是 gradio generator，没法当脚本调用，所以在<br>    这里重写一遍 —— 逻辑就是 faiss IVF，几十行，比把 gradio 拖进来划算。 | 1 | python `tools/train_worker.py:383` |
| 181 | 开始下载 {name}… | 1 | rust `app/src-tauri/src/store.rs:652` |
| 182 | 开始训练 %s | 1 | python `tools/train_worker.py:502` |
| 183 | 开始音频转换 | 1 | python `gui_v1.py:683` |
| 184 | 引擎内部错误，详见日志 | 1 | python `gui_v1.py:2846` |
| 185 | 引擎加载时崩溃，详见日志 | 1 | python `tools/realtime_worker.py:176` |
| 186 | 引擎就绪 | 1 | python `gui_v1.py:2763` |
| 187 | 引擎资源不完整（缺 {miss}）。请先在主界面完成「引擎资源」下载（hubert / rmvpe / ffmpeg）。 | 1 | rust `app/src-tauri/src/sts.rs:156` |
| 188 | 引擎资源未补全（缺 ${(st.engine_core_missing \|\| []).join("、") \|\| "hubert/rmvpe"}）。请先在主界面完成引擎资源下载。 | 1 | frontend `app/src/components/TtsPanel.tsx:131` |
| 189 | 引擎资源缺了就直接说清楚，别进 torch 后再炸一长串 traceback。 | 1 | python `tools/sts_worker.py:102` |
| 190 | 引擎进程已启动，正在加载… | 1 | python `tools/realtime_worker.py:124` |
| 191 | 当前版本 ${String(r.local)}，需先更新至 ${String(<br>          r.min_app_version,<br>        )} 才能继续 | 1 | frontend `app/src/App.tsx:99` |
| 192 | 当前版本 ${updateOffer.local}。${<br>                updateOffer.notes \|\|<br>                "更新会在后台下载，不影响变声使用；下载完成后重启软件即可生效。"<br>              } | 1 | frontend `app/src/App.tsx:807` |
| 193 | 当前缺少：${assets.engine_core_missing.join("、")} | 1 | frontend `app/src/components/ExtrasDialog.tsx:309` |
| 194 | 录了几张图、重放了多少次、退回 eager 多少次。<br><br>            没有这个就没法判断加速到底有没有生效：CUDA Graph 抓不住的时候是<br>            静默退回普通调用的，延迟数字看起来只是「没变快」，和没开一模一样。 | 1 | python `gui_v1.py:2174` |
| 195 | 很遗憾您这没有能用的显卡来支持您训练 | 1 | python `infer-web.py:129` |
| 196 | 性别因子/声线粗细 | 1 | python `gui_v1.py:521` |
| 197 | 性能测试启动失败：{e} | 1 | rust `app/src-tauri/src/shell_extras.rs:394` |
| 198 | 性能测试失败（退出码 {:?}），详见 User_Data/logs/perf_bench.log | 1 | rust `app/src-tauri/src/shell_extras.rs:397` |
| 199 | 性能测试未完成：{e} | 1 | rust `app/src-tauri/src/shell_extras.rs:428` |
| 200 | 性能设置 | 1 | python `gui_v1.py:679` |
| 201 | 总训练轮数total_epoch | 1 | python `infer-web.py:1320` |
| 202 | 成功构建索引 added_IVF%s_Flat_nprobe_%s_%s_%s.index | 1 | python `infer-web.py:698` |
| 203 | 打开 tar 失败: {e} | 1 | rust `app/src-tauri/src/extract.rs:83` |
| 204 | 打开主界面 | 1 | rust `app/src-tauri/src/i18n.rs:231` |
| 205 | 打开压缩包失败：{e} | 1 | rust `app/src-tauri/src/extract.rs:225` |
| 206 | 打开文件失败: {e} | 1 | rust `app/src-tauri/src/download.rs:70` |
| 207 | 批量推理 | 1 | python `infer-web.py:983` |
| 208 | 批量转换, 输入待转换音频文件夹, 或上传多个音频文件, 在指定文件夹(默认opt)下输出转换的音频. | 1 | python `infer-web.py:986` |
| 209 | 找不到 Runtime\pythonw.exe（根目录 {}）。请先补全 Runtime。 | 1 | rust `app/src-tauri/src/worker.rs:460` |
| 210 | 找不到 WebUI 脚本：{} | 1 | rust `app/src-tauri/src/legacy.rs:116` |
| 211 | 找不到分离脚本：{} | 1 | rust `app/src-tauri/src/separate.rs:141` |
| 212 | 找不到实时 worker: {} | 1 | rust `app/src-tauri/src/worker.rs:456` |
| 213 | 找不到实时面板脚本：{} | 1 | rust `app/src-tauri/src/legacy.rs:88` |
| 214 | 找不到推理脚本：{} | 1 | rust `app/src-tauri/src/tts.rs:277` |
| 215 | 找不到转换脚本：{} | 1 | rust `app/src-tauri/src/sts.rs:161` |
| 216 | 找不到音色包：{} | 1 | rust `app/src-tauri/src/store.rs:442` |
| 217 | 找不到音色模型：{model} | 1 | python `tools/sts_worker.py:173` |
| 218 | 拼 filelist.txt。原版 click_train 的前半段。<br><br>    末尾要补两条 mute：数据集小的时候 batch 里可能全是有声帧，模型学不到<br>    「静音该输出什么」，推理时静音段会出噪声。这两条是原版的固定做法。 | 1 | python `tools/train_worker.py:288` |
| 219 | 指定输出主人声文件夹 | 1 | python `infer-web.py:1159` |
| 220 | 指定输出文件夹 | 1 | python `infer-web.py:996` |
| 221 | 指定输出非主人声文件夹 | 1 | python `infer-web.py:1162` |
| 222 | 换模型失败，仍在用上一个音色 | 1 | python `gui_v1.py:2545` |
| 223 | 换模型失败：%s | 1 | python `gui_v1.py:2544` |
| 224 | 换模型失败：新模型没建起来，保持原样 | 1 | python `gui_v1.py:2550` |
| 225 | 换模型完成：%s（tgt_sr=%s） | 1 | python `gui_v1.py:2575` |
| 226 | 换模型：已排队 %s | 1 | python `gui_v1.py:2516` |
| 227 | 换模型：文件不存在 %s | 1 | python `gui_v1.py:2476` |
| 228 | 换模型：采样率要从 %s 变，重开流 | 1 | python `gui_v1.py:2507` |
| 229 | 换音色失败（{}）。详情见 User_Data/logs/tts.log | 1 | rust `app/src-tauri/src/tts.rs:340` |
| 230 | 推理时间(ms): | 1 | python `gui_v1.py:701` |
| 231 | 推理音色 | 1 | python `infer-web.py:834` |
| 232 | 提取 | 1 | python `infer-web.py:1584` |
| 233 | 提取音色特征… | 1 | python `tools/train_worker.py:272` |
| 234 | 提取音高… | 1 | python `tools/train_worker.py:251` |
| 235 | 提取音高和处理数据使用的CPU进程数 | 1 | python `infer-web.py:1217` |
| 236 | 收集特征… | 1 | python `tools/train_worker.py:391` |
| 237 | 数据集目录不存在：%s | 1 | python `tools/train_worker.py:516` |
| 238 | 数据预处理 | 1 | python `tools/train_worker.py:240` |
| 239 | 无 index 文件时可把 Index Rate 设为 0。 | 1 | python `gui_v1.py:792` |
| 240 | 无效档案: {e} | 1 | rust `app/src-tauri/src/voices.rs:1326` |
| 241 | 无法启动 worker: {e} | 1 | rust `app/src-tauri/src/worker.rs:517` |
| 242 | 无法识别的指令：{action} | 1 | python `gui_v1.py:2818` |
| 243 | 是 | 1 | python `infer-web.py:595` |
| 244 | 是否仅保存最新的ckpt文件以节省硬盘空间 | 1 | python `infer-web.py:1333` |
| 245 | 是否在每次保存时间点将最终小模型保存至weights文件夹 | 1 | python `infer-web.py:1348` |
| 246 | 是否缓存所有训练集至显存. 10min以下小数据可缓存以加速训练, 大数据缓存会炸显存也加不了多少速 | 1 | python `infer-web.py:1340` |
| 247 | 显卡信息 | 1 | python `infer-web.py:1265` |
| 248 | 显示器 {}{}：位置 {},{} 尺寸 {}x{} 工作区 {},{} {}x{} 缩放 {:.2} | 1 | rust `app/src-tauri/src/window_watch.rs:126` |
| 249 | 更新失败：${String(e)} | 1 | frontend `app/src/App.tsx:193` |
| 250 | 更新日志：{e} | 1 | rust `app/src-tauri/src/plaza.rs:396` |
| 251 | 替换界面失败：{e} | 1 | rust `app/src-tauri/src/update.rs:261` |
| 252 | 未能识别显卡类型：{}，请手动选择 | 1 | rust `app/src-tauri/src/provision.rs:76` |
| 253 | 本软件以MIT协议开源, 作者不对软件具备任何控制力, 使用软件者、传播软件导出的声音者自负全责. <br>如不认可该条款, 则不能使用或引用软件包内任何代码和文件. 详见根目录<b>LICENSE</b>. | 1 | python `infer-web.py:828` |
| 254 | 查看 | 1 | python `infer-web.py:1542` |
| 255 | 查看模型信息(仅支持weights文件夹下提取的小模型文件) | 1 | python `infer-web.py:1536` |
| 256 | 校验 sha256…（{}） | 1 | rust `app/src-tauri/src/provision.rs:552` |
| 257 | 档案名不合法：{profile_id:?} | 1 | rust `app/src-tauri/src/voices.rs:993` |
| 258 | 检查更新失败：${String(e)} | 1 | frontend `app/src/App.tsx:147` |
| 259 | 检测到 AMD/Intel：{}，推荐 amd（DirectML）运行时 | 1 | rust `app/src-tauri/src/provision.rs:69` |
| 260 | 检测到 NVIDIA 50 系：{}，推荐 nvidia50 运行时 | 1 | rust `app/src-tauri/src/provision.rs:45` |
| 261 | 检测到 NVIDIA：{}，推荐 nvidia（CUDA）运行时 | 1 | rust `app/src-tauri/src/provision.rs:56` |
| 262 | 检索特征占比 | 1 | python `infer-web.py:932` |
| 263 | 模型 | 1 | python `infer-web.py:1147` |
| 264 | 模型 / 输入 / 输出 都不能为空 | 1 | python `tools/separate_worker.py:62` |
| 265 | 模型推理 | 1 | python `infer-web.py:832` |
| 266 | 模型提取(输入logs文件夹下大文件模型路径),适用于训一半不想训了模型没有自动提取保存小文件模型,或者想测试中间模型的情况 | 1 | python `infer-web.py:1548` |
| 267 | 模型是否带音高指导 | 1 | python `infer-web.py:1464` |
| 268 | 模型是否带音高指导(唱歌一定要, 语音可以不要) | 1 | python `infer-web.py:1201` |
| 269 | 模型是否带音高指导,1是0否 | 1 | python `infer-web.py:1567` |
| 270 | 模型版本型号 | 1 | python `infer-web.py:1482` |
| 271 | 模型融合, 可用于测试音色融合 | 1 | python `infer-web.py:1441` |
| 272 | 模型路径 | 1 | python `infer-web.py:1511` |
| 273 | 正在下载 {label} | 1 | rust `app/src-tauri/src/extra_assets.rs:432` |
| 274 | 正在下载界面更新 ${String(r.remote)}… | 1 | frontend `app/src/App.tsx:130` |
| 275 | 正在下载程序更新 ${String(r.remote)}… | 1 | frontend `app/src/App.tsx:121` |
| 276 | 正在加载音色模型… | 1 | python `gui_v1.py:2592` |
| 277 | 正在转换 {src.name}（{i}/{total}） | 1 | python `tools/sts_worker.py:215` |
| 278 | 每张显卡的batch_size | 1 | python `infer-web.py:1328` |
| 279 | 没有找到可转换的音频（支持 wav/mp3/flac/ogg/m4a 等） | 1 | python `tools/sts_worker.py:178` |
| 280 | 没有特征文件，建不了索引。 | 1 | python `tools/train_worker.py:395` |
| 281 | 没有这个工具窗口：{kind} | 1 | rust `app/src-tauri/src/tool_window.rs:83` |
| 282 | 消除鼻音 | 1 | python `tools/dsp_fx.py:43` |
| 283 | 淡入淡出长度 | 1 | python `gui_v1.py:632` |
| 284 | 清单给的落地路径不安全：{} | 1 | rust `app/src-tauri/src/extra_assets.rs:406` |
| 285 | 清单里没有 {key} 这条资源 | 1 | rust `app/src-tauri/src/extra_assets.rs:404` |
| 286 | 清晰明亮 | 1 | python `tools/dsp_fx.py:42` |
| 287 | 温暖饱满 | 1 | python `tools/dsp_fx.py:41` |
| 288 | 版本 | 1 | python `infer-web.py:1207` |
| 289 | 特征提取没有产出。多半是 assets/hubert/hubert_base.pt 缺失或损坏。 | 1 | python `tools/train_worker.py:284` |
| 290 | 特征检索库文件路径,为空则使用下拉的选择结果 | 1 | python `infer-web.py:868` |
| 291 | 特征过多，先聚类到 1 万个中心… | 1 | python `tools/train_worker.py:403` |
| 292 | 独占 WASAPI 设备 | 1 | python `gui_v1.py:446` |
| 293 | 生成诊断包失败：${String(e)} | 1 | frontend `app/src/pages/MorePage.tsx:128` |
| 294 | 生成诊断包完成：${r?.path ?? ""}${note} | 1 | frontend `app/src/pages/MorePage.tsx:126` |
| 295 | 用法：train_worker.py <request.json> | 1 | python `tools/train_worker.py:488` |
| 296 | 界面已挂载（共 {} 个资源请求） | 1 | rust `app/src-tauri/src/ui_assets.rs:104` |
| 297 | 界面资源缺失 404 rel={rel:?} uri={:?} 外部目录={:?} | 1 | rust `app/src-tauri/src/ui_assets.rs:223` |
| 298 | 界面资源被拒绝（路径不安全）：{:?} | 1 | rust `app/src-tauri/src/ui_assets.rs:196` |
| 299 | 界面资源读取失败 {}：{e} | 1 | rust `app/src-tauri/src/ui_assets.rs:210` |
| 300 | 目标采样率 | 1 | python `infer-web.py:1195` |
| 301 | 确定删除已下载的音色文件吗？<br><br>${s?.file \|\| v.name}<br><br>删除后如需使用需重新下载。 | 1 | frontend `app/src/components/StoreSection.tsx:260` |
| 302 | 离线语音转换 worker（Speech-to-Speech / 音频 → 目标音色）。<br><br>对应官方 RVC WebUI「推理 / 批量推理」：用当前选中的 .pth 把人声音频换成<br>目标音色。不是 TTS——输入必须是声音文件。<br><br>用法::<br><br>    Runtime\python.exe tools/sts_worker.py <请求.json><br><br>请求::<br><br>    {<br>      "input": "文件或文件夹",<br>      "output": "输出目录",<br>      "model": "绝对路径.pth",<br>      "index": "可选.index",<br>      "pitch": 0,<br>      "f0method": "rmvpe",<br>      "index_rate": 0.75,<br>      "filter_radius": 3,<br>      "resample_sr": 0,<br>      "rms_mix_rate": 1.0,<br>      "protect": 0.33<br>    }<br><br>stdout 每行一条 JSON（与 separate_wor… | 1 | python `tools/sts_worker.py:2` |
| 303 | 移动 Runtime 失败: {e} | 1 | rust `app/src-tauri/src/extract.rs:212` |
| 304 | 窗口开在了非当前显示器上（{},{}），挪到光标所在屏 {},{} | 1 | rust `app/src-tauri/src/window_watch.rs:576` |
| 305 | 窗口状态（{phase}）：可见={} 最小化={} 位置={} 尺寸={} 缩放={} | 1 | rust `app/src-tauri/src/window_watch.rs:96` |
| 306 | 窗口落在所有显示器之外，拉回 {},{} | 1 | rust `app/src-tauri/src/window_watch.rs:173` |
| 307 | 第 ${cur + 1} / ${total} 页 | 1 | frontend `app/src/pages/PlazaPage.tsx:96` |
| 308 | 第 %d / %d 轮 | 1 | python `tools/train_worker.py:167` |
| 309 | 第三方 · {origin} | 1 | rust `app/src-tauri/src/store.rs:283` |
| 310 | 等分离进程失败：{e} | 1 | rust `app/src-tauri/src/separate.rs:244` |
| 311 | 等推理进程失败：{e} | 1 | rust `app/src-tauri/src/tts.rs:336` |
| 312 | 等训练进程失败：{e} | 1 | rust `app/src-tauri/src/train.rs:347` |
| 313 | 等转换进程失败：{e} | 1 | rust `app/src-tauri/src/sts.rs:288` |
| 314 | 算法延迟(ms): | 1 | python `gui_v1.py:699` |
| 315 | 系统里没有这把嗓子：{voice} | 1 | rust `app/src-tauri/src/tts.rs:125` |
| 316 | 索引完成 | 1 | python `tools/train_worker.py:439` |
| 317 | 缺少 %s 的底模（assets/pretrained_v2/f0G%s.pth）。不用底模从零训练 | 1 | python `tools/train_worker.py:355` |
| 318 | 缺少 configs/%s | 1 | python `tools/train_worker.py:338` |
| 319 | 缺少 hubert_base.pt（引擎资源未补全）。期望路径：{hubert} | 1 | python `tools/sts_worker.py:106` |
| 320 | 缺少 logs/mute 静音样本，安装不完整。 | 1 | python `tools/train_worker.py:317` |
| 321 | 缺少 rmvpe.pt（引擎资源未补全）。期望路径：{rmvpe} | 1 | python `tools/sts_worker.py:113` |
| 322 | 缺少 {} 的训练底模，请先下载 | 1 | rust `app/src-tauri/src/train.rs:222` |
| 323 | 缺省用 default，写了但不合理就夹到 1。<br><br>        不能写成 `int(raw.get(k) or default)` —— 0 是假值，会被悄悄换成默认值。<br>        用户填了 0 轮，我们给他跑 200 轮，那是两回事。 | 1 | python `tools/train_worker.py:458` |
| 324 | 网易云 | 1 | python `gui_v1.py:1385` |
| 325 | 网易虚拟 | 1 | python `gui_v1.py:1384` |
| 326 | 耳机 | 1 | python `gui_v1.py:1499` |
| 327 | 聚类失败，改用全量特征：%s | 1 | python `tools/train_worker.py:420` |
| 328 | 自动开始音频转换失败 | 1 | python `gui_v1.py:739` |
| 329 | 自动检测index路径,下拉式选择(dropdown) | 1 | python `infer-web.py:874` |
| 330 | 获取设备列表 — must fully stop stream before re-init sounddevice. | 1 | python `gui_v1.py:2038` |
| 331 | 融合 | 1 | python `infer-web.py:1488` |
| 332 | 装上排队中的新模型。**只在音频线程里调用。** | 1 | python `gui_v1.py:2519` |
| 333 | 要改的模型信息 | 1 | python `infer-web.py:1514` |
| 334 | 要置入的模型信息 | 1 | python `infer-web.py:1470` |
| 335 | 解压 Runtime… {} / {} | 1 | rust `app/src-tauri/src/provision.rs:606` |
| 336 | 解压失败 {path}: {e} | 1 | rust `app/src-tauri/src/extract.rs:177` |
| 337 | 解压失败：{e} | 1 | rust `app/src-tauri/src/engine_assets.rs:152` |
| 338 | 解压更新失败：{e} | 1 | rust `app/src-tauri/src/update.rs:242` |
| 339 | 警告：12 秒内界面没有挂载（白屏）。UI 来源 {} · 已处理 {} 个资源请求 · 404 {} 次 | 1 | rust `app/src-tauri/src/lib.rs:1383` |
| 340 | 训练完成 | 1 | python `tools/train_worker.py:539` |
| 341 | 训练完成：${r.weights ?? ""} | 1 | frontend `app/src/components/TrainPanel.tsx:153` |
| 342 | 训练模型 | 1 | python `infer-web.py:1387` |
| 343 | 训练流水线驱动。<br><br>原版把训练做在 infer-web.py 里，和 gradio 缠在一起：每一步都是 generator，<br>进度靠 `yield 整个日志文件` 刷到网页上。我们要在 Tauri 壳里用，就不能把 gradio<br>拖进来 —— 那是几十兆的依赖和一个必须开着的 web 服务。<br><br>所以这里把「驱动」和「界面」拆开：本文件只负责按顺序把原版那几个训练脚本<br>起成子进程，把进度折算成 JSON 行打到 stdout；壳读这些行画进度条。原版那几个<br>脚本一行没改，将来跟进上游就只是替换文件。<br><br>协议（每行一个 JSON 对象，stdout）::<br><br>    {"phase": "stage", "stage": "preprocess", "index": 1, "total_stages": 5,<br>     "done": 12, "total": 40, "message": "切片中…"}<br>    {"phase": "done", "weights": "assets/weights/xx.pth", "index": "logs/xx/added_...index"}<br>… | 1 | python `tools/train_worker.py:1` |
| 344 | 训练特征索引 | 1 | python `infer-web.py:1388` |
| 345 | 训练索引（%d 条特征）… | 1 | python `tools/train_worker.py:428` |
| 346 | 训练结束, 您可查看控制台训练日志或实验文件夹下的train.log | 1 | python `infer-web.py:623` |
| 347 | 训练结束但没找到 %s。查看 logs/%s/train.log。 | 1 | python `tools/train_worker.py:537` |
| 348 | 训练进度只能从 train.log 里读。<br><br>    train.py 的 logger 只挂了 FileHandler，没有 StreamHandler —— 也就是说<br>    `====> Epoch: 12` 这行**不会**出现在 stdout 上，管道里读不到。所以只能<br>    盯着文件。 | 1 | python `tools/train_worker.py:115` |
| 349 | 训练进程异常退出（{}）。详情见 logs/{}/train.log | 1 | rust `app/src-tauri/src/train.rs:356` |
| 350 | 设备列表已刷新 | 1 | python `gui_v1.py:2334` |
| 351 | 设备无效: {e} | 1 | python `gui_v1.py:958` |
| 352 | 设备类型 | 1 | python `gui_v1.py:437` |
| 353 | 设置无效（模型路径 / 设备） | 1 | python `gui_v1.py:2605` |
| 354 | 设置无效，无法开始变声 | 1 | python `gui_v1.py:2607` |
| 355 | 设置输入输出设备（允许截断的设备名）。 | 1 | python `gui_v1.py:2093` |
| 356 | 诊断包已生成: %s | 1 | python `tools/collect_diagnostics.py:228` |
| 357 | 该步骤 | 1 | python `tools/train_worker.py:214` |
| 358 | 请先进行特征提取! | 1 | python `infer-web.py:637` |
| 359 | 请先进行特征提取！ | 1 | python `infer-web.py:640` |
| 360 | 请回到主界面完成「引擎资源」下载后再试。 | 1 | python `tools/sts_worker.py:107` |
| 361 | 请将该 zip 文件发送给团队/客服。内容仅包含日志与配置，不含音频或音色模型。 | 1 | python `tools/collect_diagnostics.py:229` |
| 362 | 请指定说话人id | 1 | python `infer-web.py:1236` |
| 363 | 请检查输入/输出设备，或手动点「开始音频转换」。 | 1 | python `gui_v1.py:741` |
| 364 | 请选择pth文件 | 1 | python `gui_v1.py:910` |
| 365 | 请选择说话人id | 1 | python `infer-web.py:844` |
| 366 | 读不了请求文件：%s | 1 | python `tools/train_worker.py:492` |
| 367 | 读不出 %s 的采样率：%s | 1 | python `gui_v1.py:2455` |
| 368 | 读取 tar 失败: {e} | 1 | rust `app/src-tauri/src/extract.rs:162` |
| 369 | 读取压缩包失败：{e} | 1 | rust `app/src-tauri/src/extract.rs:226` |
| 370 | 读取设备失败 | 1 | python `gui_v1.py:2342` |
| 371 | 起一个训练子进程。<br><br>    stdout/stderr 全部倒进日志文件而不是管道：这几个脚本会打大量 tqdm 进度，<br>    走管道既没人读又会在缓冲区满的时候把子进程卡死。 | 1 | python `tools/train_worker.py:182` |
| 372 | 起不来 PowerShell：{e} | 1 | rust `app/src-tauri/src/tts.rs:107` |
| 373 | 起不来分离进程：{e} | 1 | rust `app/src-tauri/src/separate.rs:197` |
| 374 | 起不来推理进程：{e} | 1 | rust `app/src-tauri/src/tts.rs:330` |
| 375 | 起不来训练进程：{e} | 1 | rust `app/src-tauri/src/train.rs:317` |
| 376 | 起不来转换进程：{e} | 1 | rust `app/src-tauri/src/sts.rs:235` |
| 377 | 路径越界：{name} | 1 | rust `app/src-tauri/src/extract.rs:53` |
| 378 | 路径非法：{name} | 1 | rust `app/src-tauri/src/extract.rs:54` |
| 379 | 转换 | 1 | python `infer-web.py:956` |
| 380 | 转换进程异常退出（{}）。详情见 User_Data/logs/sts.log | 1 | rust `app/src-tauri/src/sts.rs:294` |
| 381 | 轮询产物目录来估进度。<br><br>    原版是把整个日志文件 yield 到网页上，我们要的是一个百分比。数产物文件比<br>    解析日志稳：日志格式跟着上游变，产物目录的名字十年没动过。 | 1 | python `tools/train_worker.py:74` |
| 382 | 输入 / 输出 / 音色模型 都不能为空 | 1 | python `tools/sts_worker.py:170` |
| 383 | 输入实验名 | 1 | python `infer-web.py:1193` |
| 384 | 输入待处理音频文件夹路径 | 1 | python `infer-web.py:1138` |
| 385 | 输入待处理音频文件夹路径(去文件管理器地址栏拷就行了) | 1 | python `infer-web.py:1087` |
| 386 | 输入待处理音频文件路径(默认是正确格式示例) | 1 | python `infer-web.py:862` |
| 387 | 输入源音量包络替换输出音量包络融合比例，越靠近1越使用输出包络 | 1 | python `infer-web.py:904` |
| 388 | 输入监听 | 1 | python `gui_v1.py:686` |
| 389 | 输入训练文件夹路径 | 1 | python `infer-web.py:1229` |
| 390 | 输入设备 | 1 | python `gui_v1.py:453` |
| 391 | 输入设备不在列表中: {input_device!r} | 1 | python `gui_v1.py:2097` |
| 392 | 输入降噪 | 1 | python `gui_v1.py:655` |
| 393 | 输出信息 | 1 | python `infer-web.py:958` |
| 394 | 输出变声 | 1 | python `gui_v1.py:693` |
| 395 | 输出设备 | 1 | python `gui_v1.py:463` |
| 396 | 输出设备不在列表中: {output_device!r} | 1 | python `gui_v1.py:2099` |
| 397 | 输出降噪 | 1 | python `gui_v1.py:660` |
| 398 | 输出音频(右下角三个点,点了可以下载) | 1 | python `infer-web.py:960` |
| 399 | 连接中… · 准备下载声卡安装包约 {} | 1 | rust `app/src-tauri/src/lib.rs:120` |
| 400 | 连接中… · 准备下载引擎资源约 {} | 1 | rust `app/src-tauri/src/lib.rs:84` |
| 401 | 连接中… · 准备下载约 {} | 1 | rust `app/src-tauri/src/provision.rs:557` |
| 402 | 连接中… · 约 {} | 1 | rust `app/src-tauri/src/provision.rs:565` |
| 403 | 退出 | 1 | rust `app/src-tauri/src/i18n.rs:232` |
| 404 | 选择.index文件 | 1 | python `gui_v1.py:425` |
| 405 | 选择.pth文件 | 1 | python `gui_v1.py:412` |
| 406 | 选择音高提取算法,输入歌声可用pm提速,harvest低音好但巨慢无比,crepe效果好但吃GPU,rmvpe效果最好且微吃GPU | 1 | python `infer-web.py:880` |
| 407 | 选择音高提取算法:输入歌声可用pm提速,高质量语音但CPU差可用dio提速,harvest质量更好但慢,rmvpe效果最好且微吃CPU/GPU | 1 | python `infer-web.py:1270` |
| 408 | 采样率: | 1 | python `gui_v1.py:488` |
| 409 | 采样长度 | 1 | python `gui_v1.py:597` |
| 410 | 重载设备列表 | 1 | python `gui_v1.py:473` |
| 411 | 链接索引到外部-%s | 1 | python `infer-web.py:716` |
| 412 | 链接索引到外部-%s失败 | 1 | python `infer-web.py:718` |
| 413 | 需要 requests 库：pip install requests | 1 | python `tools/download_models.py:83` |
| 414 | 需要几十小时和上百小时素材，不是这个界面的用法。 | 1 | python `tools/train_worker.py:356` |
| 415 | 音色 {id} 缺少有效的 sha256，已拒绝安装 | 1 | rust `app/src-tauri/src/store.rs:635` |
| 416 | 音色切换失败：${String(e)} | 1 | frontend `app/src/pages/HomePage.tsx:120` |
| 417 | 音色包{e} | 1 | rust `app/src-tauri/src/store.rs:326` |
| 418 | 音色名不能为空，也不能含 \ / : * ? " < > \| 这些字符 | 1 | python `tools/train_worker.py:451` |
| 419 | 音色文件不在了，仍在用上一个音色 | 1 | python `gui_v1.py:2475` |
| 420 | 音调设置 | 1 | python `gui_v1.py:510` |
| 421 | 音频处理 | 1 | python `gui_v1.py:1761` |
| 422 | 音频设备 | 1 | python `gui_v1.py:492` |
| 423 | 音高 {pitch:+} · 共鸣 {formant:.2} | 1 | rust `app/src-tauri/src/voices.rs:1122` |
| 424 | 音高提取 | 1 | python `tools/train_worker.py:263` |
| 425 | 音高提取没有产出。换一种音高算法再试。 | 1 | python `tools/train_worker.py:265` |
| 426 | 音高算法 | 1 | python `gui_v1.py:554` |
| 427 | 预处理没有产出任何切片。检查数据集里是不是没有可读的音频文件。 | 1 | python `tools/train_worker.py:243` |
| 428 | 额外推理时长 | 1 | python `gui_v1.py:643` |
| 429 | 麦克风 | 1 | python `gui_v1.py:281` |

