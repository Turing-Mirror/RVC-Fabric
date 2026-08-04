# i18n key 草案（未迁入语义包）

已在 `app/i18n/locales/zh-CN.json` 语义化的原文：**976** 条（含子串级字符串）。
本表剩余待迁/待译：**277** 条。

生成：`python scripts/dev/build_i18n_catalog.py`

| key | zh-CN | en-US | 出处 |
|---|---|---|---|
| `auto.frontend.x.01a0d7c23c` | ${label}完成：${r?.path ?? ""}${note} |  | `app/src/pages/MorePage.tsx:100` |
| `auto.frontend.x.1ad20ee61e` | 训练完成：${r.weights ?? ""} |  | `app/src/components/TrainPanel.tsx:153` |
| `auto.frontend.x.1f3c65c190` | 确定删除已下载的音色文件吗？<br><br>${s?.file \|\| v.name}<br><br>删除后如需使用需重新下载。 |  | `app/src/components/StoreSection.tsx:260` |
| `auto.frontend.x.2d6d30580a` | 完成，输出 ${r.files?.length ?? 0} 个文件 |  | `app/src/components/SeparatePanel.tsx:98` |
| `auto.frontend.x.34e54780f7` | ${Math.floor(m / 60)} 小时 ${m % 60} 分 |  | `app/src/components/ProvisionGate.tsx:42` |
| `auto.frontend.x.3924fc37ec` | 第 ${cur + 1} / ${total} 页 |  | `app/src/pages/PlazaPage.tsx:96` |
| `auto.frontend.x.3c0cc285e5` | 检查更新失败：${String(e)} |  | `app/src/App.tsx:147` |
| `auto.frontend.x.3d3ca9458d` | 发现新版本 ${String(r.remote)}，当前 ${String(r.local)} |  | `app/src/App.tsx:112` |
| `auto.frontend.x.4d16b65880` | ${p.message \|\| p.phase \|\| "下载中"} ${<br>          p.percent != null ? |  | `app/src/components/StoreSection.tsx:124` |
| `auto.frontend.x.4dad70d965` | 合成完成：${r.file ?? ""} |  | `app/src/components/TtsPanel.tsx:362` |
| `auto.frontend.x.59aa9016ba` | 完成 ${r.files?.length ?? 0} 个文件${r.output ? |  | `app/src/components/TtsPanel.tsx:153` |
| `auto.frontend.x.6d2e92e04d` | 失败：${String(e)} |  | `app/src/pages/HelpPage.tsx:186` |
| `auto.frontend.x.6deda26aeb` | 生成诊断包完成：${r?.path ?? ""}${note} |  | `app/src/pages/MorePage.tsx:126` |
| `auto.frontend.x.730b9b9abb` | 更新失败：${String(e)} |  | `app/src/App.tsx:193` |
| `auto.frontend.x.73b37da828` | 引擎资源未补全（缺 ${(st.engine_core_missing \|\| []).join("、") \|\| "hubert/rmvpe"}）。请先在主界面完成引擎资源下载。 |  | `app/src/components/TtsPanel.tsx:131` |
| `auto.frontend.x.80241a56d3` | 已是最新版本 ${String(r.local)}（${clockNow()} 检查） |  | `app/src/App.tsx:108` |
| `auto.frontend.x.893ad3c090` | 保存失败：${String(e)} |  | `app/src/pages/MorePage.tsx:70` |
| `auto.frontend.x.8fbb40595a` | 当前缺少：${assets.engine_core_missing.join("、")} |  | `app/src/components/ExtrasDialog.tsx:309` |
| `auto.frontend.x.a821a59e88` | 启动失败：${String(e)} |  | `app/src/pages/MorePage.tsx:91` |
| `auto.frontend.x.ae500fb6ab` | 生成诊断包失败：${String(e)} |  | `app/src/pages/MorePage.tsx:128` |
| `auto.frontend.x.aec25def6b` | 正在下载界面更新 ${String(r.remote)}… |  | `app/src/App.tsx:130` |
| `auto.frontend.x.b0106e06e7` | 当前版本 ${updateOffer.local}。${<br>                updateOffer.notes \|\|<br>                "更新会在后台下载，不影响变声使用；下载完成后重启软件即可生效。"<br>              } |  | `app/src/App.tsx:807` |
| `auto.frontend.x.b0ec903b3f` | ${m} 分 ${s % 60} 秒 |  | `app/src/components/ProvisionGate.tsx:41` |
| `auto.frontend.x.b1bb04c308` | 使用「${TITLES[kind]}」前，需要先下载引擎资源（hubert / rmvpe / ffmpeg，约 720 MB）。下载完成后即可打开工具。 |  | `app/src/components/ToolWindow.tsx:37` |
| `auto.frontend.x.c11227b2d4` | 已更新至 ${String(b.version ?? r.remote)}，重启程序后生效 |  | `app/src/App.tsx:125` |
| `auto.frontend.x.c2352d1e60` | ${label}失败：${String(e)} |  | `app/src/pages/MorePage.tsx:102` |
| `auto.frontend.x.d38983b5dd` | 音色切换失败：${String(e)} |  | `app/src/pages/HomePage.tsx:120` |
| `auto.frontend.x.f0bab98244` | 已更新至 ${String(r.remote)}，重启程序后生效 |  | `app/src/App.tsx:135` |
| `auto.frontend.x.f5d5101a11` | 当前版本 ${String(r.local)}，需先更新至 ${String(<br>          r.min_app_version,<br>        )} 才能继续 |  | `app/src/App.tsx:99` |
| `auto.frontend.x.f9ef10d27a` | 正在下载程序更新 ${String(r.remote)}… |  | `app/src/App.tsx:121` |
| `auto.python.webui.072cf9a19d` | 本软件以MIT协议开源, 作者不对软件具备任何控制力, 使用软件者、传播软件导出的声音者自负全责. <br>如不认可该条款, 则不能使用或引用软件包内任何代码和文件. 详见根目录<b>LICENSE</b>. |  | `infer-web.py:828` |
| `auto.python.webui.109f24ef17` | A模型权重 |  | `infer-web.py:1452` |
| `auto.python.webui.118d2b1eb3` | 刷新音色列表和索引路径 |  | `infer-web.py:837` |
| `auto.python.webui.15ed819756` | step2:正在提取音高&正在提取特征 |  | `infer-web.py:757` |
| `auto.python.webui.166c5ae30f` | 保存名 |  | `infer-web.py:1558` |
| `auto.python.webui.17aa81d56b` | E:\语音音频+标注\米津玄师\src |  | `infer-web.py:1230` |
| `auto.python.webui.1c222429f1` | 模型路径 |  | `infer-web.py:1511` |
| `auto.python.webui.1d02842a21` | 后处理重采样至最终采样率，0为不进行重采样 |  | `infer-web.py:895` |
| `auto.python.webui.1f86a26845` | 训练特征索引 |  | `infer-web.py:1388` |
| `auto.python.webui.2073e332b1` | 自动检测index路径,下拉式选择(dropdown) |  | `infer-web.py:874` |
| `auto.python.webui.23a40d7813` | 链接索引到外部-%s |  | `infer-web.py:716` |
| `auto.python.webui.27eaf76835` | 请指定说话人id |  | `infer-web.py:1236` |
| `auto.python.webui.290c22dfc2` | 要置入的模型信息 |  | `infer-web.py:1470` |
| `auto.python.webui.298df24c7f` | 特征检索库文件路径,为空则使用下拉的选择结果 |  | `infer-web.py:868` |
| `auto.python.webui.29b4c880f5` | 全流程结束！ |  | `infer-web.py:789` |
| `auto.python.webui.30160a21b9` | 是 |  | `infer-web.py:595` |
| `auto.python.webui.31e85b8266` | 选择音高提取算法,输入歌声可用pm提速,harvest低音好但巨慢无比,crepe效果好但吃GPU,rmvpe效果最好且微吃GPU |  | `infer-web.py:880` |
| `auto.python.webui.34b77552ea` | 输入实验名 |  | `infer-web.py:1193` |
| `auto.python.webui.3903e6ea43` | 很遗憾您这没有能用的显卡来支持您训练 |  | `infer-web.py:129` |
| `auto.python.webui.3fc7ec4234` | 保存频率save_every_epoch |  | `infer-web.py:1312` |
| `auto.python.webui.40bd146740` | 一键训练 |  | `infer-web.py:1389` |
| `auto.python.webui.440004a6af` | 导出Onnx模型 |  | `infer-web.py:1608` |
| `auto.python.webui.444056eb7b` | step2a: 自动遍历训练文件夹下所有可解码成音频的文件并进行切片归一化, 在实验目录下生成2个wav文件夹; 暂时只支持单人训练. |  | `infer-web.py:1224` |
| `auto.python.webui.4662871d0b` | 查看模型信息(仅支持weights文件夹下提取的小模型文件) |  | `infer-web.py:1536` |
| `auto.python.webui.493abd81e2` | 指定输出主人声文件夹 |  | `infer-web.py:1159` |
| `auto.python.webui.4a0532a097` | 检索特征占比 |  | `infer-web.py:932` |
| `auto.python.webui.4baf02f95c` | 人声提取激进程度 |  | `infer-web.py:1153` |
| `auto.python.webui.4f3e24a999` | 模型是否带音高指导,1是0否 |  | `infer-web.py:1567` |
| `auto.python.webui.4fbcabffa8` | step2b: 使用CPU提取音高(如果模型带音高), 使用GPU提取特征(选择卡号) |  | `infer-web.py:1251` |
| `auto.python.webui.539585446e` | 模型是否带音高指导 |  | `infer-web.py:1464` |
| `auto.python.webui.5c7d8c39a3` | F0曲线文件, 可选, 一行一个音高, 代替默认F0及升降调 |  | `infer-web.py:938` |
| `auto.python.webui.5cba568e03` | 也可批量输入音频文件, 二选一, 优先读文件夹 |  | `infer-web.py:1093` |
| `auto.python.webui.5f6264f998` | 特征提取 |  | `infer-web.py:1284` |
| `auto.python.webui.61190f20f0` | Onnx导出 |  | `infer-web.py:1596` |
| `auto.python.webui.61cd955dbb` | 批量推理 |  | `infer-web.py:983` |
| `auto.python.webui.662d3ebc9f` | 处理数据 |  | `infer-web.py:1240` |
| `auto.python.webui.67b6a127f7` | 模型版本型号 |  | `infer-web.py:1482` |
| `auto.python.webui.67ce4f1d26` | 训练结束, 您可查看控制台训练日志或实验文件夹下的train.log |  | `infer-web.py:623` |
| `auto.python.webui.68fc922145` | 模型提取(输入logs文件夹下大文件模型路径),适用于训一半不想训了模型没有自动提取保存小文件模型,或者想测试中间模型的情况 |  | `infer-web.py:1548` |
| `auto.python.webui.69050e8c68` | 是否仅保存最新的ckpt文件以节省硬盘空间 |  | `infer-web.py:1333` |
| `auto.python.webui.69e3bebee7` | 保存的文件名, 默认空为和源文件同名 |  | `infer-web.py:1520` |
| `auto.python.webui.6fe5c91f22` | 提取 |  | `infer-web.py:1584` |
| `auto.python.webui.70a1bed422` | 训练模型 |  | `infer-web.py:1387` |
| `auto.python.webui.726bdb2b8d` | 批量转换, 输入待转换音频文件夹, 或上传多个音频文件, 在指定文件夹(默认opt)下输出转换的音频. |  | `infer-web.py:986` |
| `auto.python.webui.72a0d5de78` | 链接索引到外部-%s失败 |  | `infer-web.py:718` |
| `auto.python.webui.777e8ba054` | 加载预训练底模G路径 |  | `infer-web.py:1356` |
| `auto.python.webui.795143e2e1` | 输入源音量包络替换输出音量包络融合比例，越靠近1越使用输出包络 |  | `infer-web.py:904` |
| `auto.python.webui.7c5284ed52` | Onnx输出路径 |  | `infer-web.py:1603` |
| `auto.python.webui.7d1b7f685d` | 指定输出文件夹 |  | `infer-web.py:996` |
| `auto.python.webui.7e5417fbae` | 加载预训练底模D路径 |  | `infer-web.py:1361` |
| `auto.python.webui.8101ab287a` | 是否缓存所有训练集至显存. 10min以下小数据可缓存以加速训练, 大数据缓存会炸显存也加不了多少速 |  | `infer-web.py:1340` |
| `auto.python.webui.86fd6dc9c8` | 保护清辅音和呼吸声，防止电音撕裂等artifact，拉满0.5不开启，调低加大保护力度但可能降低索引效果 |  | `infer-web.py:913` |
| `auto.python.webui.8b7977d94b` | 转换 |  | `infer-web.py:956` |
| `auto.python.webui.8bf5c10ad9` | 否 |  | `infer-web.py:1334` |
| `auto.python.webui.90a08d32a7` | 融合 |  | `infer-web.py:1488` |
| `auto.python.webui.923d694909` | A模型路径 |  | `infer-web.py:1444` |
| `auto.python.webui.92befb3a82` | 保存的模型名不带后缀 |  | `infer-web.py:1476` |
| `auto.python.webui.934a206413` | 成功构建索引 added_IVF%s_Flat_nprobe_%s_%s_%s.index |  | `infer-web.py:698` |
| `auto.python.webui.966dc24d9e` | 常见问题解答 |  | `infer-web.py:1613` |
| `auto.python.webui.989d1affa0` | 版本 |  | `infer-web.py:1207` |
| `auto.python.webui.9ca944bf56` | 修改模型信息(仅支持weights文件夹下提取的小模型文件) |  | `infer-web.py:1507` |
| `auto.python.webui.a4fdb519a9` | 变调(整数, 半音数量, 升八度12降八度-12) |  | `infer-web.py:857` |
| `auto.python.webui.a74d2b2f6f` | 每张显卡的batch_size |  | `infer-web.py:1328` |
| `auto.python.webui.a7c9fca61f` | 请先进行特征提取! |  | `infer-web.py:637` |
| `auto.python.webui.a8f1b1f2f4` | >=3则使用对harvest音高识别的结果使用中值滤波，数值为滤波半径，使用可以削弱哑音 |  | `infer-web.py:923` |
| `auto.python.webui.aad36ade71` | 单次推理 |  | `infer-web.py:852` |
| `auto.python.webui.ab9228cd2f` | 请选择说话人id |  | `infer-web.py:844` |
| `auto.python.webui.b1d16d942b` | 伴奏人声分离&去混响&去回声 |  | `infer-web.py:1128` |
| `auto.python.webui.b6ae6e4225` | 请先进行特征提取！ |  | `infer-web.py:640` |
| `auto.python.webui.b8fbb7a444` | 总训练轮数total_epoch |  | `infer-web.py:1320` |
| `auto.python.webui.bc30fa1b34` | 输入训练文件夹路径 |  | `infer-web.py:1229` |
| `auto.python.webui.bc44eddb37` | step3: 填写训练设置, 开始训练模型和索引 |  | `infer-web.py:1306` |
| `auto.python.webui.bed091156e` | 模型融合, 可用于测试音色融合 |  | `infer-web.py:1441` |
| `auto.python.webui.c4a109e60a` | 输入待处理音频文件路径(默认是正确格式示例) |  | `infer-web.py:862` |
| `auto.python.webui.c54ae12262` | step1: 填写实验配置. 实验数据放在logs下, 每个实验一个文件夹, 需手工输入实验名路径, 内含实验配置, 日志, 训练得到的模型文件. |  | `infer-web.py:1189` |
| `auto.python.webui.c72ce3b9b7` | 指定输出非主人声文件夹 |  | `infer-web.py:1162` |
| `auto.python.webui.c76e499ea9` | B模型路径 |  | `infer-web.py:1447` |
| `auto.python.webui.c7a0a43b07` | 输出信息 |  | `infer-web.py:958` |
| `auto.python.webui.c85bde56ea` | 显卡信息 |  | `infer-web.py:1265` |
| `auto.python.webui.c9c77517fe` | 修改 |  | `infer-web.py:1526` |
| `auto.python.webui.ca637cd604` | 输入待处理音频文件夹路径(去文件管理器地址栏拷就行了) |  | `infer-web.py:1087` |
| `auto.python.webui.d8bc5741cc` | 输出音频(右下角三个点,点了可以下载) |  | `infer-web.py:960` |
| `auto.python.webui.db22efdae5` | 模型推理 |  | `infer-web.py:832` |
| `auto.python.webui.dea83a8c68` | 模型是否带音高指导(唱歌一定要, 语音可以不要) |  | `infer-web.py:1201` |
| `auto.python.webui.e3a06e881c` | 提取音高和处理数据使用的CPU进程数 |  | `infer-web.py:1217` |
| `auto.python.webui.e3be709057` | step1:正在处理数据 |  | `infer-web.py:753` |
| `auto.python.webui.e402bafe6e` | 输入待处理音频文件夹路径 |  | `infer-web.py:1138` |
| `auto.python.webui.e4b42fa3ae` | step3a:正在训练模型 |  | `infer-web.py:766` |
| `auto.python.webui.e4fd56037f` | 选择音高提取算法:输入歌声可用pm提速,高质量语音但CPU差可用dio提速,harvest质量更好但慢,rmvpe效果最好且微吃CPU/GPU |  | `infer-web.py:1270` |
| `auto.python.webui.e955aa9e1c` | 推理音色 |  | `infer-web.py:834` |
| `auto.python.webui.eb83979a9a` | 以-分隔输入使用的卡号, 例如   0-1-2   使用卡0和卡1和卡2 |  | `infer-web.py:1258` |
| `auto.python.webui.ed0443f887` | 导出文件格式 |  | `infer-web.py:1021` |
| `auto.python.webui.f00c806d0e` | 是否在每次保存时间点将最终小模型保存至weights文件夹 |  | `infer-web.py:1348` |
| `auto.python.webui.f311d8e366` | 目标采样率 |  | `infer-web.py:1195` |
| `auto.python.webui.f60e226fb7` | 人声伴奏分离批量处理， 使用UVR5模型。 <br>合格的文件夹路径格式举例： E:\codes\py39\vits_vc_gpu\白鹭霜华测试样例(去文件管理器地址栏拷就行了)。 <br>模型分为三类： <br>1、保留人声：不带和声的音频选这个，对主人声保留比HP5更好。内置HP2和HP3两个模型，HP3可能轻微漏伴奏但对主人声保留比HP2稍微好一丁点； <br>2、仅保留主人声：带和声的音频选这个，对主人声可能有削弱。内置HP5一个模型； <br> 3、去混响、去延迟模型（by FoxJoy）：<br>  (1)MDX-Net(onnx_dereverb):对于双通道混响是最好的选择，不能去除单通道混响；<br>&emsp;(234)DeEcho:去除延迟效果。Aggressive比Normal去除得更彻底，DeReverb额外去除混响，可去除单声道混响，但是对高频重的板式混响去不干净。<br>去混响/去延迟，附：<br>1、DeEcho-DeReverb模型的耗时是另外2个DeEcho模型的接近2倍；<br>2、MDX-Net-Dereverb模型挺慢的；<br>3、个人推荐的… |  | `infer-web.py:1132` |
| `auto.python.webui.f84b14ee31` | rmvpe卡号配置：以-分隔输入使用的不同进程卡号,例如0-0-1使用在卡0上跑2个进程并在卡1上跑1个进程 |  | `infer-web.py:1278` |
| `auto.python.webui.fa17a1a1fc` | RVC模型路径 |  | `infer-web.py:1599` |
| `auto.python.webui.fa394bbdf0` | 卸载音色省显存 |  | `infer-web.py:839` |
| `auto.python.webui.fbf23a5016` | 要改的模型信息 |  | `infer-web.py:1514` |
| `auto.python.webui.ff6750ad49` | ckpt处理 |  | `infer-web.py:1439` |
| `auto.python.worker.024c91ced8` | 提取音色特征… |  | `tools/train_worker.py:272` |
| `auto.python.worker.0f31a69bda` | 训练完成 |  | `tools/train_worker.py:539` |
| `auto.python.worker.14b4cdf2c9` | 请回到主界面完成「引擎资源」下载后再试。 |  | `tools/sts_worker.py:107` |
| `auto.python.worker.15407df90e` | 四类产物对不上号，没有一条可用的训练样本。建议清掉实验重来。 |  | `tools/train_worker.py:304` |
| `auto.python.worker.157064d803` | 数据预处理 |  | `tools/train_worker.py:240` |
| `auto.python.worker.1aa56d3403` | 全部完成，共 {len(out_files)} 个 |  | `tools/sts_worker.py:260` |
| `auto.python.worker.1bdba463e4` | Windows 管道下 stdout 常是系统代码页，中文 JSON 会 OSError 22。 |  | `tools/sts_worker.py:60` |
| `auto.python.worker.1d62f27a1d` | 音高提取 |  | `tools/train_worker.py:263` |
| `auto.python.worker.20c19ff77d` | 已有切片，跳过预处理 |  | `tools/train_worker.py:513` |
| `auto.python.worker.22096f5d9e` | 模型 / 输入 / 输出 都不能为空 |  | `tools/separate_worker.py:62` |
| `auto.python.worker.23108b9022` | 读不了请求文件：%s |  | `tools/train_worker.py:492` |
| `auto.python.worker.2aab038dd1` | 收集特征… |  | `tools/train_worker.py:391` |
| `auto.python.worker.2e6194f2b5` | 缺少 %s 的底模（assets/pretrained_v2/f0G%s.pth）。不用底模从零训练 |  | `tools/train_worker.py:355` |
| `auto.python.worker.2e6b0f8d39` | {src.name} 失败：{e} |  | `tools/sts_worker.py:257` |
| `auto.python.worker.331ae87bc9` | cwd 切到产品根、加载 .env、补齐 RVC 路径（相对路径改成绝对路径）。 |  | `tools/sts_worker.py:70` |
| `auto.python.worker.349e4a27eb` | 输入 / 输出 / 音色模型 都不能为空 |  | `tools/sts_worker.py:170` |
| `auto.python.worker.38c8a7fd21` | 拼 filelist.txt。原版 click_train 的前半段。<br><br>    末尾要补两条 mute：数据集小的时候 batch 里可能全是有声帧，模型学不到<br>    「静音该输出什么」，推理时静音段会出噪声。这两条是原版的固定做法。 |  | `tools/train_worker.py:288` |
| `auto.python.worker.3b35e1dc4d` | 起一个训练子进程。<br><br>    stdout/stderr 全部倒进日志文件而不是管道：这几个脚本会打大量 tqdm 进度，<br>    走管道既没人读又会在缓冲区满的时候把子进程卡死。 |  | `tools/train_worker.py:182` |
| `auto.python.worker.3cc83de1b6` | 请求文件读不了：{e} |  | `tools/separate_worker.py:52` +1 |
| `auto.python.worker.3da156fea9` | 预处理没有产出任何切片。检查数据集里是不是没有可读的音频文件。 |  | `tools/train_worker.py:243` |
| `auto.python.worker.3e9c98e766` | 数据集目录不存在：%s |  | `tools/train_worker.py:516` |
| `auto.python.worker.4989594d30` | 完成 {src.name} |  | `tools/sts_worker.py:253` |
| `auto.python.worker.4c91bcea32` | 正在转换 {src.name}（{i}/{total}） |  | `tools/sts_worker.py:215` |
| `auto.python.worker.4ea566f214` | 训练结束但没找到 %s。查看 logs/%s/train.log。 |  | `tools/train_worker.py:537` |
| `auto.python.worker.4f1c1bf03b` | 提取音高… |  | `tools/train_worker.py:251` |
| `auto.python.worker.5627b743e6` | 缺少 rmvpe.pt（引擎资源未补全）。期望路径：{rmvpe} |  | `tools/sts_worker.py:113` |
| `auto.python.worker.56d319e830` | 训练进度只能从 train.log 里读。<br><br>    train.py 的 logger 只挂了 FileHandler，没有 StreamHandler —— 也就是说<br>    `====> Epoch: 12` 这行**不会**出现在 stdout 上，管道里读不到。所以只能<br>    盯着文件。 |  | `tools/train_worker.py:115` |
| `auto.python.worker.5accb7502f` | 缺少 logs/mute 静音样本，安装不完整。 |  | `tools/train_worker.py:317` |
| `auto.python.worker.5f6264f998` | 特征提取 |  | `tools/train_worker.py:281` |
| `auto.python.worker.6071c2c01b` | 第 %d / %d 轮 |  | `tools/train_worker.py:167` |
| `auto.python.worker.675e1d57d0` | 切片与重采样… |  | `tools/train_worker.py:230` |
| `auto.python.worker.71da5454ee` | 音色名不能为空，也不能含 \ / : * ? " < > \| 这些字符 |  | `tools/train_worker.py:451` |
| `auto.python.worker.75127fc864` | 该步骤 |  | `tools/train_worker.py:214` |
| `auto.python.worker.7d63558436` | 人声分离 worker：跑一次 PyMSS，把进度按行吐给 Rust 侧。<br><br>为什么不直接调 `python -m tools.pymss.cli infer`：它的进度是 tqdm 画在<br>stderr 上的进度条，要靠正则去刮，格式一变就瞎。PyMSS 的 separator 本来就收<br>`progress_callback(done, total, message)`，接上它按行输出 JSON 干净得多。<br><br>用法（Rust 侧这么调）::<br><br>    pythonw tools/separate_worker.py <请求文件.json><br><br>请求文件::<br><br>    {"model": "...", "model_dir": "...", "input": "...", "output": "...",<br>     "device": "auto", "format": "wav"}<br><br>stdout 每行一条 JSON：<br>    {"phase":"start"}                          开始<br>    {"phase":"run","done":3,"total"… |  | `tools/separate_worker.py:2` |
| `auto.python.worker.8101838a6a` | 没有特征文件，建不了索引。 |  | `tools/train_worker.py:395` |
| `auto.python.worker.828c25e1aa` | 缺少 hubert_base.pt（引擎资源未补全）。期望路径：{hubert} |  | `tools/sts_worker.py:106` |
| `auto.python.worker.8cdc6762da` | 特征提取没有产出。多半是 assets/hubert/hubert_base.pt 缺失或损坏。 |  | `tools/train_worker.py:284` |
| `auto.python.worker.90e1d19bc3` | 需要几十小时和上百小时素材，不是这个界面的用法。 |  | `tools/train_worker.py:356` |
| `auto.python.worker.992dc973f5` | 离线语音转换 worker（Speech-to-Speech / 音频 → 目标音色）。<br><br>对应官方 RVC WebUI「推理 / 批量推理」：用当前选中的 .pth 把人声音频换成<br>目标音色。不是 TTS——输入必须是声音文件。<br><br>用法::<br><br>    Runtime\python.exe tools/sts_worker.py <请求.json><br><br>请求::<br><br>    {<br>      "input": "文件或文件夹",<br>      "output": "输出目录",<br>      "model": "绝对路径.pth",<br>      "index": "可选.index",<br>      "pitch": 0,<br>      "f0method": "rmvpe",<br>      "index_rate": 0.75,<br>      "filter_radius": 3,<br>      "resample_sr": 0,<br>      "rms_mix_rate": 1.0,<br>      "protect": 0.33<br>    }<br><br>stdout 每行一条 JSON（与 separate_wor… |  | `tools/sts_worker.py:2` |
| `auto.python.worker.9b0f5b8f01` | 训练索引（%d 条特征）… |  | `tools/train_worker.py:428` |
| `auto.python.worker.9dd7399a6b` | 准备训练（%d 条样本）… |  | `tools/train_worker.py:349` |
| `auto.python.worker.9fad49fb4a` | 音高提取没有产出。换一种音高算法再试。 |  | `tools/train_worker.py:265` |
| `auto.python.worker.a8b1f26975` | 特征过多，先聚类到 1 万个中心… |  | `tools/train_worker.py:403` |
| `auto.python.worker.b0324b4236` | 缺请求文件参数 |  | `tools/separate_worker.py:47` +1 |
| `auto.python.worker.b8066a64e3` | 聚类失败，改用全量特征：%s |  | `tools/train_worker.py:420` |
| `auto.python.worker.bdc5b96a54` | 没有找到可转换的音频（支持 wav/mp3/flac/ogg/m4a 等） |  | `tools/sts_worker.py:178` |
| `auto.python.worker.bfa7275759` | 用法：train_worker.py <request.json> |  | `tools/train_worker.py:488` |
| `auto.python.worker.c01b3ef143` | 共 {total} 个文件 |  | `tools/sts_worker.py:190` |
| `auto.python.worker.c2a65f00aa` | 索引完成 |  | `tools/train_worker.py:439` |
| `auto.python.worker.c38648744c` | 已有特征，跳过 |  | `tools/train_worker.py:525` |
| `auto.python.worker.c6d91692ab` | 不支持的采样率：%s |  | `tools/train_worker.py:454` |
| `auto.python.worker.c97efbc8d7` | {src.name} 转换失败：{info or '未知错误'} |  | `tools/sts_worker.py:244` |
| `auto.python.worker.c9d07b3194` | %s失败（退出码 %s），详情见 %s |  | `tools/train_worker.py:214` |
| `auto.python.worker.cb40563b2c` | 缺少 configs/%s |  | `tools/train_worker.py:338` |
| `auto.python.worker.d109f76da9` | 建检索索引。<br><br>    这段原版写在 infer-web.py 里且是 gradio generator，没法当脚本调用，所以在<br>    这里重写一遍 —— 逻辑就是 faiss IVF，几十行，比把 gradio 拖进来划算。 |  | `tools/train_worker.py:383` |
| `auto.python.worker.d368c166fb` | 缺省用 default，写了但不合理就夹到 1。<br><br>        不能写成 `int(raw.get(k) or default)` —— 0 是假值，会被悄悄换成默认值。<br>        用户填了 0 轮，我们给他跑 200 轮，那是两回事。 |  | `tools/train_worker.py:458` |
| `auto.python.worker.d46dbfec19` | 找不到音色模型：{model} |  | `tools/sts_worker.py:173` |
| `auto.python.worker.db63350251` | 开始训练 %s |  | `tools/train_worker.py:502` |
| `auto.python.worker.e1d412a619` | 轮询产物目录来估进度。<br><br>    原版是把整个日志文件 yield 到网页上，我们要的是一个百分比。数产物文件比<br>    解析日志稳：日志格式跟着上游变，产物目录的名字十年没动过。 |  | `tools/train_worker.py:74` |
| `auto.python.worker.e647f7011a` | 一行一个 JSON。带锁是因为 tail 线程和主线程都会往 stdout 写。 |  | `tools/train_worker.py:48` |
| `auto.python.worker.ea7775aa26` | 训练流水线驱动。<br><br>原版把训练做在 infer-web.py 里，和 gradio 缠在一起：每一步都是 generator，<br>进度靠 `yield 整个日志文件` 刷到网页上。我们要在 Tauri 壳里用，就不能把 gradio<br>拖进来 —— 那是几十兆的依赖和一个必须开着的 web 服务。<br><br>所以这里把「驱动」和「界面」拆开：本文件只负责按顺序把原版那几个训练脚本<br>起成子进程，把进度折算成 JSON 行打到 stdout；壳读这些行画进度条。原版那几个<br>脚本一行没改，将来跟进上游就只是替换文件。<br><br>协议（每行一个 JSON 对象，stdout）::<br><br>    {"phase": "stage", "stage": "preprocess", "index": 1, "total_stages": 5,<br>     "done": 12, "total": 40, "message": "切片中…"}<br>    {"phase": "done", "weights": "assets/weights/xx.pth", "index": "logs/xx/added_...index"}<br>… |  | `tools/train_worker.py:1` |
| `auto.python.worker.ec7d18df67` | 分离失败，详见日志 |  | `tools/separate_worker.py:104` |
| `auto.python.worker.f1ac3b5b22` | 加载模型失败：{e} |  | `tools/sts_worker.py:206` |
| `auto.python.worker.f3590339b1` | 引擎资源缺了就直接说清楚，别进 torch 后再炸一长串 traceback。 |  | `tools/sts_worker.py:102` |
| `auto.python.worker.f4bd0ca6c8` | 已有音高，跳过 |  | `tools/train_worker.py:520` |
| `auto.python.x.029d4cbaae` | 装上排队中的新模型。**只在音频线程里调用。** |  | `gui_v1.py:2519` |
| `auto.python.x.09240d11ce` | WARNING: 安装路径含中文/特殊字符，部分组件可能异常，建议移到纯英文路径 |  | `gui_v1.py:32` |
| `auto.python.x.0b59db544a` | 性别因子/声线粗细 |  | `gui_v1.py:521` |
| `auto.python.x.0eba6f0cba` | 换模型失败：新模型没建起来，保持原样 |  | `gui_v1.py:2550` |
| `auto.python.x.13ad7d8574` | 变声中换音色。<br><br>            引擎原来根本不认 pth_path 这个热更新键：换模型只写了配置文件，正在跑<br>            的这个 worker 手里还攥着上一个模型，于是界面上名字变了、声音没变。<br>            上一版的做法是「停流再开流」—— 能换过去，但要几秒，设备重开，<br>            延迟设置重算，用户听到的是一段静音加一次咔哒。<br><br>            现在只换该换的那一件东西：RVC 实例。缓冲区的尺寸、音频进程、设备、<br>            SOLA 的窗口全都不动，因为它们只跟采样率有关，跟哪个音色无关。<br><br>            唯一换不了的情况是采样率真的会变 —— 只有「跟随模型」那档才可能，<br>            这时候整条流水线的几何尺寸都变了，老老实实重开。 |  | `gui_v1.py:2459` |
| `auto.python.x.151eeabaf6` | 停止失败 |  | `gui_v1.py:2711` |
| `auto.python.x.180ec968ae` | pth文件不存在 |  | `gui_v1.py:952` |
| `auto.python.x.19a6463690` | 音频处理 |  | `gui_v1.py:1761` |
| `auto.python.x.214c8ab7c6` | 录了几张图、重放了多少次、退回 eager 多少次。<br><br>            没有这个就没法判断加速到底有没有生效：CUDA Graph 抓不住的时候是<br>            静默退回普通调用的，延迟数字看起来只是「没变快」，和没开一模一样。 |  | `gui_v1.py:2174` |
| `auto.python.x.24c4c5929f` | 正在加载音色模型… |  | `gui_v1.py:2592` |
| `auto.python.x.25cc9d4f2c` | Main app sets TM_AUTO_START_VC=1 when user clicks 开启变声. |  | `gui_v1.py:710` |
| `auto.python.x.2ab6e66ef2` | 推理时间(ms): |  | `gui_v1.py:701` |
| `auto.python.x.2d4e0a7a97` | 换模型失败：%s |  | `gui_v1.py:2544` |
| `auto.python.x.2d9711a949` | 获取设备列表 — must fully stop stream before re-init sounddevice. |  | `gui_v1.py:2038` |
| `auto.python.x.3204d2727f` | 主声音驱动 |  | `gui_v1.py:1397` |
| `auto.python.x.36ae8ccfcf` | 采样长度 |  | `gui_v1.py:597` |
| `auto.python.x.3ca74120fd` | 换模型：文件不存在 %s |  | `gui_v1.py:2476` |
| `auto.python.x.46cf156c68` | 设备无效: {e} |  | `gui_v1.py:958` |
| `auto.python.x.49dd8efdab` | 自动开始音频转换失败 |  | `gui_v1.py:739` |
| `auto.python.x.560e5fe4cf` | 需要 requests 库：pip install requests |  | `tools/download_models.py:83` |
| `auto.python.x.56173ef22a` | 输出设备不在列表中: {output_device!r} |  | `gui_v1.py:2099` |
| `auto.python.x.5655f44bf7` | 网易云 |  | `gui_v1.py:1385` |
| `auto.python.x.5faef468fb` | 音调设置 |  | `gui_v1.py:510` |
| `auto.python.x.6035649763` | 设置无效，无法开始变声 |  | `gui_v1.py:2607` |
| `auto.python.x.60c39e8a92` | 淡入淡出长度 |  | `gui_v1.py:632` |
| `auto.python.x.63047e8ce7` | 停止音频转换 |  | `gui_v1.py:684` |
| `auto.python.x.654833a58b` | 请将该 zip 文件发送给团队/客服。内容仅包含日志与配置，不含音频或音色模型。 |  | `tools/collect_diagnostics.py:229` |
| `auto.python.x.65525f0f44` | 启动失败 |  | `gui_v1.py:2700` |
| `auto.python.x.6bf23267ad` | load: 设备刷新失败，保留已保存的配置 |  | `gui_v1.py:357` |
| `auto.python.x.70c7767c5e` | 无法识别的指令：{action} |  | `gui_v1.py:2818` |
| `auto.python.x.75dddf524e` | 已停止 |  | `gui_v1.py:2718` |
| `auto.python.x.8474de4367` | 换模型：采样率要从 %s 变，重开流 |  | `gui_v1.py:2507` |
| `auto.python.x.84f60f42a9` | 换模型：已排队 %s |  | `gui_v1.py:2516` |
| `auto.python.x.863c59fed2` | 使用设备采样率 |  | `gui_v1.py:482` |
| `auto.python.x.8a1bf7f6c6` | 读取设备失败 |  | `gui_v1.py:2342` |
| `auto.python.x.8c0647fe8c` | 请检查输入/输出设备，或手动点「开始音频转换」。 |  | `gui_v1.py:741` |
| `auto.python.x.8c2a8089e4` | 引擎内部错误，详见日志 |  | `gui_v1.py:2846` |
| `auto.python.x.8cc5a6052e` | 常见原因：模型路径无效、显存不足、声卡占用、index 损坏。 |  | `gui_v1.py:791` |
| `auto.python.x.8e468eec6b` | 输入监听 |  | `gui_v1.py:686` |
| `auto.python.x.96183d82ed` | 设置无效（模型路径 / 设备） |  | `gui_v1.py:2605` |
| `auto.python.x.99193e1379` | 选择.pth文件 |  | `gui_v1.py:412` |
| `auto.python.x.997772ced1` | 加载模型 |  | `gui_v1.py:404` |
| `auto.python.x.9acdcde488` | 参数已应用 |  | `gui_v1.py:2810` |
| `auto.python.x.a118dcd8a1` | 诊断包已生成: %s |  | `tools/collect_diagnostics.py:228` |
| `auto.python.x.a203967e23` | 只读出这个权重的目标采样率，不建模型。<br><br>            换模型要不要重开流，只取决于采样率会不会变。为这一个数把整套<br>            RVC 建起来太贵，而 torch.load 出来的 cpt["config"][-1] 就是它。<br><br>            weights_only=True 是硬性的：.pth 是 pickle，允许它执行代码等于<br>            让任何一个从广场下下来的音色包在用户机器上跑任意程序。 |  | `gui_v1.py:2443` |
| `auto.python.x.a258244381` | 换模型失败，仍在用上一个音色 |  | `gui_v1.py:2545` |
| `auto.python.x.a4c49dfa1e` | 换模型完成：%s（tgt_sr=%s） |  | `gui_v1.py:2575` |
| `auto.python.x.aa16830a3c` | 选择.index文件 |  | `gui_v1.py:425` |
| `auto.python.x.af50c05eef` | 算法延迟(ms): |  | `gui_v1.py:699` |
| `auto.python.x.b177818236` | 使用模型采样率 |  | `gui_v1.py:475` |
| `auto.python.x.b6290a6793` | 启动音频转换失败 |  | `gui_v1.py:788` |
| `auto.python.x.bff05a83cd` | 已退出 |  | `gui_v1.py:2787` |
| `auto.python.x.c155ef2300` | 网易虚拟 |  | `gui_v1.py:1384` |
| `auto.python.x.c292968290` | 独占 WASAPI 设备 |  | `gui_v1.py:446` |
| `auto.python.x.c44eda71a0` | 采样率: |  | `gui_v1.py:488` |
| `auto.python.x.c88bc536f3` | 输出变声 |  | `gui_v1.py:693` |
| `auto.python.x.c8ff6b08eb` | 设备列表已刷新 |  | `gui_v1.py:2334` |
| `auto.python.x.c9b6411daa` | 设置输入输出设备（允许截断的设备名）。 |  | `gui_v1.py:2093` |
| `auto.python.x.cb2e797a0c` | 读不出 %s 的采样率：%s |  | `gui_v1.py:2455` |
| `auto.python.x.cd1e117c70` | 输入设备不在列表中: {input_device!r} |  | `gui_v1.py:2097` |
| `auto.python.x.d11aaac275` | 音频设备 |  | `gui_v1.py:492` |
| `auto.python.x.d8c0ea3065` | 无 index 文件时可把 Index Rate 设为 0。 |  | `gui_v1.py:792` |
| `auto.python.x.dc9a2c7058` | harvest进程数 |  | `gui_v1.py:619` |
| `auto.python.x.df752e7aa9` | 音色文件不在了，仍在用上一个音色 |  | `gui_v1.py:2475` |
| `auto.python.x.f4e5f5707b` | 常规设置 |  | `gui_v1.py:592` |
| `auto.python.x.f726adc0fe` | 请选择pth文件 |  | `gui_v1.py:910` |
| `auto.python.x.f9bd877ab3` | 启用相位声码器 |  | `gui_v1.py:665` |
| `auto.python.x.f9d166976a` | 响度因子 |  | `gui_v1.py:543` |
| `auto.python.x.fbe37298bc` | 开始音频转换 |  | `gui_v1.py:683` |
| `auto.rust.i18n_rs.3363f3729b` | 加载 |  | `app/src-tauri/src/i18n.rs:234` |
| `auto.rust.webui.4f09ae24cf` | Runtime 未就绪，请先在首次运行向导里补全运行时 |  | `app/src-tauri/src/legacy.rs:29` |
| `auto.rust.x.227d108a35` | Runtime 已就绪，跳过下载。 |  | `app/src-tauri/src/provision.rs:447` |
| `auto.rust.x.45309ba4c5` | Runtime 未就绪，无法开启变声 |  | `app/src-tauri/src/lib.rs:525` |
| `auto.rust.x.75b84a31d6` | Runtime 未就绪，请先补全运行时 |  | `app/src-tauri/src/separate.rs:137` +3 |
| `auto.rust.x.9f39847f54` | Runtime 未就绪 |  | `app/src-tauri/src/lib.rs:851` |
| `auto.rust.x.a36cb645c2` | Runtime 未就绪（缺少 torch） |  | `app/src-tauri/src/lib.rs:509` |
| `auto.rust.x.a64a986f63` | Runtime 补全完成 |  | `app/src-tauri/src/provision.rs:635` |
| `auto.rust.x.c8c05e7db7` | Runtime 未就绪，无法跑性能测试 |  | `app/src-tauri/src/shell_extras.rs:266` |
| `auto.rust.x.dc92f52f68` | Runtime 未就绪，请先补全运行环境 |  | `app/src-tauri/src/train.rs:212` |
| `auto.rust.x.e1b39abf92` | Runtime 已就绪，跳过下载 |  | `app/src-tauri/src/provision.rs:444` |
| `auto.rust.x.ee7e83d91d` | Runtime 就绪，但缺少 tools/realtime_worker.py |  | `app/src-tauri/src/provision.rs:362` |
| `auto.rust.x.f2e88c071e` | Runtime 就绪 |  | `app/src-tauri/src/provision.rs:364` |
