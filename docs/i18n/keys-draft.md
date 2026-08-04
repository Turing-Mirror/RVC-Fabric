# i18n key 草案（未迁入语义包）

已在 `app/i18n/locales/zh-CN.json` 语义化的原文：**152** 条（含子串级字符串）。
本表剩余待迁/待译：**1133** 条。

生成：`python scripts/dev/build_i18n_catalog.py`

| key | zh-CN | en-US | 出处 |
|---|---|---|---|
| `auto.frontend.x.002dcbcd28` | 产品根目录自动解析 |  | `app/src/pages/MorePage.tsx:210` |
| `auto.frontend.x.004a3a2b67` | 不会用？转至说明页 |  | `app/src/pages/SettingsPage.tsx:222` |
| `auto.frontend.x.0096454995` | 可为音色保存多套参数预设（音高/音效/性能），一键切换，也能导出分享、导入他人预设。 |  | `app/src/pages/ModelsPage.tsx:495` |
| `auto.frontend.x.01a0d7c23c` | ${label}完成：${r?.path ?? ""}${note} |  | `app/src/pages/MorePage.tsx:99` |
| `auto.frontend.x.02942ba343` | 麦克风增益 dB |  | `app/src/pages/SettingsPage.tsx:258` |
| `auto.frontend.x.031c105578` | 打开目录 |  | `app/src/pages/ModelsPage.tsx:263` |
| `auto.frontend.x.03877888b6` | 未选择目标音色。请到首页或「模型」页先选一个音色。 |  | `app/src/components/TtsPanel.tsx:137` |
| `auto.frontend.x.038c681d8c` | 噪声门 |  | `app/src/pages/SettingsPage.tsx:593` |
| `auto.frontend.x.03f0ef8930` | 显卡在系统里的排序和显卡驱动的排序不保证一致。 |  | `app/src/components/MainGpuPicker.tsx:11` |
| `auto.frontend.x.041b014e3a` | · ${it.files.length} 个文件 |  | `app/src/components/ExtrasDialog.tsx:470` |
| `auto.frontend.x.0709bd6ae7` | 选 CABLE Input，游戏里才收得到 |  | `app/src/pages/HelpPage.tsx:270` |
| `auto.frontend.x.07a1fa9790` | 推荐运行时 |  | `app/src/pages/MorePage.tsx:243` |
| `auto.frontend.x.087db63ab1` | 安装 |  | `app/src/components/StoreSection.tsx:580` +1 |
| `auto.frontend.x.090840132b` | 转换中… |  | `app/src/components/TtsPanel.tsx:295` |
| `auto.frontend.x.094beaeab9` | 正在准备虚拟声卡安装包… |  | `app/src/components/ProvisionGate.tsx:197` |
| `auto.frontend.x.09febb1c95` | 朗读嗓音 |  | `app/src/components/TtsPanel.tsx:410` |
| `auto.frontend.x.0a432092e4` | 暂未获取到更新日志。 |  | `app/src/pages/PlazaPage.tsx:102` |
| `auto.frontend.x.0b6e0b33c3` | render 崩溃：${stack} |  | `app/src/components/ErrorBoundary.tsx:32` |
| `auto.frontend.x.0c593a479c` | 下载训练底模 |  | `app/src/components/TrainPanel.tsx:309` |
| `auto.frontend.x.0d63fa301f` | 音色目录 |  | `app/src/pages/ModelsPage.tsx:222` |
| `auto.frontend.x.0df76209a8` | 人声前倾 |  | `app/src/pages/SettingsPage.tsx:61` |
| `auto.frontend.x.0e2d3a3c09` | 使用 |  | `app/src/pages/ModelsPage.tsx:366` |
| `auto.frontend.x.0ec38407bc` | 停不干净、声卡一直被占 |  | `app/src/pages/HelpPage.tsx:59` |
| `auto.frontend.x.0eeffdd75b` | 已启动 |  | `app/src/pages/MorePage.tsx:81` |
| `auto.frontend.x.0f14377cdd` | 选你真实的麦克风 |  | `app/src/pages/HelpPage.tsx:265` |
| `auto.frontend.x.0f843238e9` | 低于此电平的声音会被压低。<br>环境吵就往上调（接近 −20）；调太高会把气音也切掉。 |  | `app/src/lib/config.ts:69` |
| `auto.frontend.x.10481886ca` | 你已经有虚拟声卡了，不必再装 VB-Cable —— 多装一套只会多出几个容易接错的设备。把软件输出选到它的输入端，游戏麦克风选到它的输出端即可。 |  | `app/src/pages/HelpPage.tsx:231` |
| `auto.frontend.x.10c5cf2954` | 素材目录 |  | `app/src/components/TrainPanel.tsx:195` |
| `auto.frontend.x.1148b67ccc` | 已就绪；可强制重装 |  | `app/src/pages/MorePage.tsx:248` |
| `auto.frontend.x.122abe360d` | 连不上服务器，检查网络后再试。 |  | `app/src/components/ExtrasDialog.tsx:242` |
| `auto.frontend.x.149ab7bf0a` | 虚拟声卡怎么连 |  | `app/src/pages/HelpPage.tsx:261` |
| `auto.frontend.x.14b8f39742` | 运行时未就绪 |  | `app/src/hooks/useEngine.ts:106` |
| `auto.frontend.x.1747a288fd` | WASAPI 独占（一般无需开启，只在你清楚自己在做什么时开启） |  | `app/src/pages/SettingsPage.tsx:304` |
| `auto.frontend.x.1784a97067` | 已转为可管理音色 |  | `app/src/pages/ModelsPage.tsx:438` |
| `auto.frontend.x.17d9ff0c09` | 正在启动官方安装程序… |  | `app/src/pages/HelpPage.tsx:180` |
| `auto.frontend.x.1831f7eb53` | 还没读到设备，点右边「重载设备列表」以重试 |  | `app/src/pages/SettingsPage.tsx:182` |
| `auto.frontend.x.185368440e` | 更新日志 |  | `app/src/pages/PlazaPage.tsx:84` |
| `auto.frontend.x.18b35795d9` | 输入降噪 |  | `app/src/pages/SettingsPage.tsx:511` |
| `auto.frontend.x.19e933ad2a` | 后期处理 |  | `app/src/pages/SettingsPage.tsx:533` |
| `auto.frontend.x.1a2edaedf8` | 生成咨询包 |  | `app/src/pages/MorePage.tsx:358` |
| `auto.frontend.x.1a37ffe775` | 切片 |  | `app/src/components/TrainPanel.tsx:41` |
| `auto.frontend.x.1a3fe8f826` | 1. 输出设备：实体声卡的播放通道 |  | `app/src/pages/HelpPage.tsx:50` |
| `auto.frontend.x.1ad20ee61e` | 训练完成：${r.weights ?? ""} |  | `app/src/components/TrainPanel.tsx:152` |
| `auto.frontend.x.1ae90bfb23` | 按系列 |  | `app/src/components/StoreSection.tsx:346` |
| `auto.frontend.x.1b94ca3bf5` | 无法查询安装包状态，点右侧仍可尝试下载并安装 |  | `app/src/pages/HelpPage.tsx:247` |
| `auto.frontend.x.1bce2ccca4` | 关闭时只走「输出设备」（通常 CABLE）；开启后在耳机里听变声 |  | `app/src/pages/SettingsPage.tsx:292` |
| `auto.frontend.x.1be7ae4fc2` | 名称 |  | `app/src/pages/ModelsPage.tsx:290` |
| `auto.frontend.x.1ca9f4246d` | 切片块时长（Block Size）：每次处理的音频切片长度。数值越小延迟越低，但越吃 GPU/CPU，过小会导致声音断断续续。<br>修改后需重新「开启变声」生效。 |  | `app/src/lib/config.ts:51` |
| `auto.frontend.x.1cac8ac7f5` | 处理中… |  | `app/src/pages/HelpPage.tsx:254` |
| `auto.frontend.x.1cd12cf03d` | 说话间隙自动压低底噪，比响应阈值更柔和。 |  | `app/src/lib/config.ts:67` |
| `auto.frontend.x.1cd80fd7a8` | 重命名 |  | `app/src/pages/ModelsPage.tsx:669` |
| `auto.frontend.x.1d1c09492b` | 共 ${models.length} 个音色 · 当前使用：${cur} |  | `app/src/pages/ModelsPage.tsx:92` |
| `auto.frontend.x.1d2f7d6189` | 其他虚拟声卡 |  | `app/src/pages/HelpPage.tsx:102` |
| `auto.frontend.x.1da56dd72c` | 变声后依次经过噪声门、压缩器、均衡器。<br>关闭则直接输出模型原生声音，下方所有设置失效。运行中可实时开关。 |  | `app/src/lib/config.ts:63` |
| `auto.frontend.x.1e1016e5c8` | 首次使用需下载运行时环境（含 PyTorch，需几 GB 空间），下载后自动部署。 |  | `app/src/components/ProvisionGate.tsx:304` |
| `auto.frontend.x.1e48570a18` | CPU 线程数 |  | `app/src/pages/SettingsPage.tsx:484` |
| `auto.frontend.x.1f3c65c190` | 确定删除已下载的音色文件吗？<br><br>${s?.file \|\| v.name}<br><br>删除后如需使用需重新下载。 |  | `app/src/components/StoreSection.tsx:259` |
| `auto.frontend.x.1fd4658c44` | 还没查过。开机时会自动查一次。 |  | `app/src/pages/SettingsPage.tsx:869` |
| `auto.frontend.x.206f264868` | 暂不参与 |  | `app/src/App.tsx:826` |
| `auto.frontend.x.209d309d58` | 常见情况 |  | `app/src/pages/HelpPage.tsx:290` |
| `auto.frontend.x.2105061e3e` | 准备… |  | `app/src/components/ProvisionGate.tsx:224` |
| `auto.frontend.x.21a8e41cf6` | 抖音 |  | `app/src/lib/links.ts:41` |
| `auto.frontend.x.22067787e1` | 显示 / 隐藏主界面 |  | `app/src/pages/SettingsPage.tsx:900` |
| `auto.frontend.x.2282c91c77` | 分离中… |  | `app/src/components/SeparatePanel.tsx:197` |
| `auto.frontend.x.22b8661995` | 可选绑定 · 提升音色还原度 |  | `app/src/pages/ModelsPage.tsx:409` |
| `auto.frontend.x.22dda461eb` | 给算法更多上下文：数值越大音质与音高越稳，但延迟随之增加。 |  | `app/src/lib/config.ts:55` |
| `auto.frontend.x.23cb78c4b5` | 首次开启变声需加载 PyTorch 和音色模型，通常 20–40 秒；之后再开会快很多。 |  | `app/src/pages/HelpPage.tsx:66` |
| `auto.frontend.x.245826185c` | 未选择（文件或文件夹） |  | `app/src/components/TtsPanel.tsx:181` |
| `auto.frontend.x.25d87929cc` | 调节麦克风输入音量：说话声太小就调高；已经够大还调高会削波破音。 |  | `app/src/lib/config.ts:28` |
| `auto.frontend.x.262d11e2d6` | 未选择模型 |  | `app/src/App.tsx:200` |
| `auto.frontend.x.265e64c266` | 浏览器预览（引擎未接入） |  | `app/src/lib/engine.ts:74` |
| `auto.frontend.x.26a85f2a66` | · 已安装 |  | `app/src/components/ExtrasDialog.tsx:471` |
| `auto.frontend.x.26ad7c406b` | 保持选择耳机，不要选 CABLE |  | `app/src/pages/HelpPage.tsx:285` |
| `auto.frontend.x.279450164a` | 还没有选择音色。 |  | `app/src/pages/ModelsPage.tsx:210` |
| `auto.frontend.x.2898cbf891` | 耳机，只有你自己听得到 |  | `app/src/pages/HelpPage.tsx:275` |
| `auto.frontend.x.291c041b0a` | 不再显示 |  | `app/src/components/AdBanner.tsx:53` |
| `auto.frontend.x.29a29efed7` | 第一次开启特别慢 |  | `app/src/pages/HelpPage.tsx:64` |
| `auto.frontend.x.29abc60b6f` | 该音色的模型文件与绑定预设将一并删除，无法恢复。<br><br>确认删除？ |  | `app/src/pages/ModelsPage.tsx:687` |
| `auto.frontend.x.2a26295b90` | 还没有本地音色呢~ 去「模型」页导入，或到「广场」逛逛吧！ |  | `app/src/pages/HomePage.tsx:133` |
| `auto.frontend.x.2a4080ad9f` | 运行状态 |  | `app/src/pages/MorePage.tsx:175` |
| `auto.frontend.x.2a4b19a6b1` | 产品根目录 |  | `app/src/pages/MorePage.tsx:184` |
| `auto.frontend.x.2a7b36e853` | 作者 : ${v.author} |  | `app/src/pages/HomePage.tsx:242` +2 |
| `auto.frontend.x.2af26573b0` | 作者 : — |  | `app/src/pages/ModelsPage.tsx:358` |
| `auto.frontend.x.2b9d013177` | 下载 |  | `app/src/components/StoreSection.tsx:587` +1 |
| `auto.frontend.x.2b9ddc0b69` | 暂时没有可下载的训练底模。 |  | `app/src/components/ExtrasDialog.tsx:244` |
| `auto.frontend.x.2bd28fc9c2` | 仓库与社媒 |  | `app/src/pages/MorePage.tsx:381` |
| `auto.frontend.x.2d5f93d547` | 提取歌曲中的人声干声与伴奏 |  | `app/src/pages/HomePage.tsx:266` |
| `auto.frontend.x.2d6d30580a` | 完成，输出 ${r.files?.length ?? 0} 个文件 |  | `app/src/components/SeparatePanel.tsx:97` |
| `auto.frontend.x.2d6e3da5e1` | 改完要重新「开启变声」才生效。 |  | `app/src/components/MainGpuPicker.tsx:9` |
| `auto.frontend.x.2de4352d13` | 音色模型由声音素材训练而来，相关权利属于原声权利人。 |  | `app/src/components/StoreSection.tsx:276` |
| `auto.frontend.x.2de72cf04d` | 你有多块 N 卡。不指定的话引擎用排在第一的那块，不一定是最快的那块。 以后也可以在「其他 → 运行状态」里改。 |  | `app/src/components/ProvisionGate.tsx:368` |
| `auto.frontend.x.2fe9b75856` | 缺失 |  | `app/src/pages/ModelsPage.tsx:346` |
| `auto.frontend.x.3076e38c53` | 正在下载安装包… |  | `app/src/pages/HelpPage.tsx:176` |
| `auto.frontend.x.30e91c9e4d` | 用干声素材训练专属音色模型 |  | `app/src/pages/HomePage.tsx:271` |
| `auto.frontend.x.310f4d242c` | A 卡 / 核显（DirectML）路径上这一项不生效。 |  | `app/src/components/MainGpuPicker.tsx:12` |
| `auto.frontend.x.31469944aa` | 按下组合键… |  | `app/src/pages/SettingsPage.tsx:999` |
| `auto.frontend.x.314a72cba4` | 这个音色的模型文件缺失或不完整，请重新下载或修复。 |  | `app/src/pages/HomePage.tsx:90` +1 |
| `auto.frontend.x.3166554c46` | 继续训练 |  | `app/src/components/TrainPanel.tsx:291` |
| `auto.frontend.x.31a98593f1` | 跳过 |  | `app/src/components/ProvisionGate.tsx:459` |
| `auto.frontend.x.31e9cad169` | 开始转换 |  | `app/src/components/TtsPanel.tsx:295` |
| `auto.frontend.x.33246f6a5e` | 完成 |  | `app/src/components/ProvisionGate.tsx:459` |
| `auto.frontend.x.33dadd8dd6` | 引擎资源已就绪 |  | `app/src/components/ExtrasDialog.tsx:198` |
| `auto.frontend.x.344a481fa0` | 打开输出目录 |  | `app/src/components/TtsPanel.tsx:288` |
| `auto.frontend.x.34e54780f7` | ${Math.floor(m / 60)} 小时 ${m % 60} 分 |  | `app/src/components/ProvisionGate.tsx:41` |
| `auto.frontend.x.35de158fda` | 音色使用须知 |  | `app/src/components/StoreSection.tsx:275` |
| `auto.frontend.x.3620fe63a3` | 这个音色不支持绑定。 |  | `app/src/pages/ModelsPage.tsx:216` |
| `auto.frontend.x.364b26a260` | Windows 默认播放 |  | `app/src/pages/HelpPage.tsx:284` |
| `auto.frontend.x.3755f56f2f` | 删除 |  | `app/src/pages/ModelsPage.tsx:682` +1 |
| `auto.frontend.x.3800ff2864` | 2. 设备列表里没有设备时，点「重载设备列表」或重启软件 |  | `app/src/pages/HelpPage.tsx:55` |
| `auto.frontend.x.38108eaa1d` | 刷新 |  | `app/src/pages/ModelsPage.tsx:256` +1 |
| `auto.frontend.x.3848444f8c` | 变声 / 原声 |  | `app/src/pages/SettingsPage.tsx:893` |
| `auto.frontend.x.384eef0c3e` | 音频接口类型：<br>• MME：兼容性最好，几乎不挑设备；<br>• WASAPI：延迟更低，但对设备更挑。<br>修改后需重新「开启变声」生效。 |  | `app/src/lib/config.ts:24` |
| `auto.frontend.x.389bc211b2` | 检索强度 |  | `app/src/pages/SettingsPage.tsx:383` +1 |
| `auto.frontend.x.3924fc37ec` | 第 ${cur + 1} / ${total} 页 |  | `app/src/pages/PlazaPage.tsx:97` |
| `auto.frontend.x.3a070016e2` | 直接关闭 |  | `app/src/App.tsx:774` |
| `auto.frontend.x.3a23a85820` | 压缩比 |  | `app/src/pages/SettingsPage.tsx:645` |
| `auto.frontend.x.3aa83c304c` | 输出设备 |  | `app/src/pages/SettingsPage.tsx:272` |
| `auto.frontend.x.3bf3d98458` | 音频变声 / 文字合成，换成目标音色 |  | `app/src/pages/HomePage.tsx:276` |
| `auto.frontend.x.3c0cc285e5` | 检查更新失败：${String(e)} |  | `app/src/App.tsx:146` |
| `auto.frontend.x.3d136b7951` | 按时间 |  | `app/src/components/StoreSection.tsx:345` |
| `auto.frontend.x.3d13883b98` | 商业推广 |  | `app/src/pages/PlazaPage.tsx:253` +1 |
| `auto.frontend.x.3d19649847` | （缺底模） |  | `app/src/components/TrainPanel.tsx:229` |
| `auto.frontend.x.3d1fde4601` | 暂未获取到程序更新包，可先前往发布页手动下载 |  | `app/src/App.tsx:125` |
| `auto.frontend.x.3d2c784f94` | 系统里已经有 CABLE 设备，不用再装。重装只在设备损坏时才需要 |  | `app/src/pages/HelpPage.tsx:243` |
| `auto.frontend.x.3d3ca9458d` | 发现新版本 ${String(r.remote)}，当前 ${String(r.local)} |  | `app/src/App.tsx:111` |
| `auto.frontend.x.3d4e683008` | 最后一步：安装虚拟声卡 |  | `app/src/components/ProvisionGate.tsx:445` |
| `auto.frontend.x.3e510eb16a` | 第 ${prog.index}/${prog.total_stages} 步 · ${stageLabel} |  | `app/src/components/TrainPanel.tsx:166` |
| `auto.frontend.x.3e6b1657c7` | 训练中… |  | `app/src/components/TrainPanel.tsx:291` |
| `auto.frontend.x.3ff3e5ff9b` | 参与用户统计 |  | `app/src/pages/SettingsPage.tsx:799` |
| `auto.frontend.x.402fd697c1` | 声卡内录 / 立体声混音 |  | `app/src/pages/HelpPage.tsx:107` |
| `auto.frontend.x.405125fb37` | 补全运行时 |  | `app/src/components/ProvisionGate.tsx:301` |
| `auto.frontend.x.42667034ec` | 使用人声干声素材训练专属音色。推荐 10 分钟以上的高质量录音， 含背景音乐的素材请先使用「人声分离」进行处理。 |  | `app/src/components/TrainPanel.tsx:172` |
| `auto.frontend.x.42d0633ac9` | 系统里没有可用的语音。到「Windows 设置 → 时间和语言 → 语音」里添加一个语音包。 |  | `app/src/components/TtsPanel.tsx:347` |
| `auto.frontend.x.43b19c9a61` | 关闭 RVC Fabric |  | `app/src/App.tsx:756` |
| `auto.frontend.x.445b04ec19` | 控制输出音量跟随原声的程度，越低越接近训练音色本身的响度。 |  | `app/src/lib/config.ts:47` |
| `auto.frontend.x.44c7946c76` | 补全失败 |  | `app/src/components/ProvisionGate.tsx:146` |
| `auto.frontend.x.44e681a374` | 中断 |  | `app/src/components/TrainPanel.tsx:284` |
| `auto.frontend.x.4500b5dfc7` | 第三方 |  | `app/src/components/StoreSection.tsx:335` |
| `auto.frontend.x.468c96d425` | 打开作者链接 |  | `app/src/pages/ModelsPage.tsx:703` |
| `auto.frontend.x.46e66f6321` | 当前版本 |  | `app/src/pages/SettingsPage.tsx:859` |
| `auto.frontend.x.46ecac2910` | 文件夹 |  | `app/src/components/TtsPanel.tsx:197` |
| `auto.frontend.x.479fcc1cc0` | 稍后 |  | `app/src/components/ProvisionGate.tsx:479` +1 |
| `auto.frontend.x.47a991d18c` | 设备类型 |  | `app/src/pages/SettingsPage.tsx:233` |
| `auto.frontend.x.481ec6c2df` | 开启变声前，需要先下载引擎资源（hubert / rmvpe / ffmpeg）。请到「其他 → 下载模型」补全。 |  | `app/src/hooks/useEngine.ts:161` |
| `auto.frontend.x.481ee2d4bc` | 正在检查… |  | `app/src/pages/HelpPage.tsx:245` +1 |
| `auto.frontend.x.489b99d4d7` | 引擎资源未补全，请先到「其他 → 下载模型」下载引擎资源 |  | `app/src/hooks/useEngine.ts:164` |
| `auto.frontend.x.4951a916f7` | 这是实体声卡的内录通道，也能走通：软件输出选实体声卡的播放，游戏麦克风选这个内录通道。展开下面「实体声卡怎么连」有详细接法。 |  | `app/src/pages/HelpPage.tsx:232` |
| `auto.frontend.x.497e7d9af6` | 提取音频中的人声干声与伴奏，可用于清理音色训练素材里的背景音乐。 模型按需下载，与 RVC/UVR 官方权重同源。 |  | `app/src/components/SeparatePanel.tsx:120` |
| `auto.frontend.x.49c4c2a8bb` | 1. 输入设备：实体声卡的录音通道（名字里带声卡型号） |  | `app/src/pages/HelpPage.tsx:45` |
| `auto.frontend.x.49deaf7da2` | 文件 |  | `app/src/components/TtsPanel.tsx:188` |
| `auto.frontend.x.49e4ba4794` | 越高越贴近目标音色，但吐字可能变糊；越低越保留你自己的发音。<br>未绑定 .index 检索库时此项无效。 |  | `app/src/lib/config.ts:46` |
| `auto.frontend.x.49fd445d8b` | 读取设置… |  | `app/src/pages/SettingsPage.tsx:213` |
| `auto.frontend.x.4aa2306395` | 生成 |  | `app/src/pages/MorePage.tsx:321` |
| `auto.frontend.x.4b829fbdac` | 初始值 |  | `app/src/components/controls.tsx:303` |
| `auto.frontend.x.4bbcf94739` | 下载完成 |  | `app/src/components/ExtrasDialog.tsx:221` |
| `auto.frontend.x.4bbfde15f2` | 3. 音高算法换 FCPE 或 RMVPE 试听 |  | `app/src/pages/HelpPage.tsx:35` |
| `auto.frontend.x.4c65a5e25e` | NVIDIA（推荐大多数 N 卡） |  | `app/src/components/ProvisionGate.tsx:167` |
| `auto.frontend.x.4d0b4688c7` | 取消 |  | `app/src/components/SeparatePanel.tsx:190` +2 |
| `auto.frontend.x.4d16b65880` | ${p.message \|\| p.phase \|\| "下载中"} ${<br>          p.percent != null ? |  | `app/src/components/StoreSection.tsx:123` |
| `auto.frontend.x.4dad70d965` | 合成完成：${r.file ?? ""} |  | `app/src/components/TtsPanel.tsx:370` |
| `auto.frontend.x.4e22f58ed9` | 预录制 GPU 推理指令，减少 CPU 与 GPU 的交互开销，可降低延迟、减少显存占用。<br>仅 NVIDIA 显卡有效；环境不兼容时自动退回传统模式。 |  | `app/src/lib/config.ts:58` |
| `auto.frontend.x.4e504ca0d3` | 转为可管理音色 |  | `app/src/pages/ModelsPage.tsx:714` |
| `auto.frontend.x.4eea655d6f` | 音色名 |  | `app/src/components/TrainPanel.tsx:208` |
| `auto.frontend.x.4fe38132a0` | 正在启动… |  | `app/src/pages/MorePage.tsx:76` |
| `auto.frontend.x.502c5adda6` | 正在连接服务器，稍后显示进度… |  | `app/src/components/ProvisionGate.tsx:406` |
| `auto.frontend.x.504a366966` | 2. 关闭输入或输出降噪中的一项（降噪较吃显卡） |  | `app/src/pages/HelpPage.tsx:34` |
| `auto.frontend.x.5258b304cc` | 解决卡死 |  | `app/src/pages/MorePage.tsx:368` |
| `auto.frontend.x.52c469558c` | 2. 监听设备选真实耳机或音箱，不要选 CABLE 等虚拟声卡 |  | `app/src/pages/HelpPage.tsx:26` |
| `auto.frontend.x.531e3e438f` | 待下载 |  | `app/src/components/StoreSection.tsx:587` |
| `auto.frontend.x.53e2db7016` | 未选择 |  | `app/src/components/SeparatePanel.tsx:145` +2 |
| `auto.frontend.x.542c5b925f` | 有新版本 ${updateOffer.remote}，是否立即更新？ |  | `app/src/App.tsx:797` |
| `auto.frontend.x.5488b0c4b0` | 对变声后的声音再降一次噪。通常开输入降噪就够，仅在底噪明显时开启。 |  | `app/src/lib/config.ts:60` |
| `auto.frontend.x.54b3625b92` | 导入音色… |  | `app/src/pages/ModelsPage.tsx:248` |
| `auto.frontend.x.550c08627b` | 监听设备 |  | `app/src/pages/SettingsPage.tsx:290` |
| `auto.frontend.x.55adfb8c3f` | 噪声门阈值 |  | `app/src/pages/SettingsPage.tsx:605` |
| `auto.frontend.x.55e39bd8d0` | 把软件放到纯英文路径再试 |  | `app/src/pages/HelpPage.tsx:70` |
| `auto.frontend.x.561d709070` | 5. 确认安装的是与显卡匹配的运行时版本 |  | `app/src/pages/HelpPage.tsx:37` |
| `auto.frontend.x.5695956a42` | 想让游戏 / 语音 里的人听到变声，必须先装虚拟声卡（VB-Cable）。 装完重启一次电脑，设备列表里才会出现 CABLE Input / CABLE Output。 |  | `app/src/pages/HelpPage.tsx:205` |
| `auto.frontend.x.56ce781723` | 生成诊断包… |  | `app/src/pages/MorePage.tsx:117` |
| `auto.frontend.x.579ea14ab7` | 5 段参数均衡器（EQ）：微调变声后的各频段响度。不确定怎么调，先套用下方预设。 |  | `app/src/lib/config.ts:64` |
| `auto.frontend.x.57c737fbad` | 确认删除预设「${p.name}」？该操作不可撤销。 |  | `app/src/pages/ModelsPage.tsx:570` |
| `auto.frontend.x.57da23c608` | 旧版单文件音色：转为「可管理音色」后，即可绑定检索库与预设。 |  | `app/src/pages/ModelsPage.tsx:214` |
| `auto.frontend.x.58b4af2771` | 已刷新 |  | `app/src/pages/ModelsPage.tsx:254` |
| `auto.frontend.x.594eba5310` | 选你实际使用的耳机或音箱。<br>选到虚拟声卡会听不到声音，还可能回环啸叫。 |  | `app/src/lib/config.ts:34` |
| `auto.frontend.x.59aa9016ba` | 完成 ${r.files?.length ?? 0} 个文件${r.output ? |  | `app/src/components/TtsPanel.tsx:155` |
| `auto.frontend.x.59f6a509e7` | 压缩或均衡处理后整体音量偏小的话，在这里补回来。 |  | `app/src/lib/config.ts:74` |
| `auto.frontend.x.5abed96e7d` | 未就绪（需补全） |  | `app/src/pages/MorePage.tsx:170` |
| `auto.frontend.x.5acba95590` | 预置的调音曲线：选一个直接套用，也能选完再拖下面的推子微调。<br>手动拖动后会显示「自定义」。 |  | `app/src/lib/config.ts:66` |
| `auto.frontend.x.5b254c438b` | 返回广场 |  | `app/src/pages/PlazaPage.tsx:92` |
| `auto.frontend.x.5b422f44dd` | 按采样率下一套底模即可（三选一）。先补全上方的引擎资源（hubert / rmvpe），再下底模。 |  | `app/src/components/ExtrasDialog.tsx:82` |
| `auto.frontend.x.5b6259b315` | 下一个音色 |  | `app/src/pages/SettingsPage.tsx:895` |
| `auto.frontend.x.5b833d9334` | CUDA Graph 加速（仅 N 卡） |  | `app/src/pages/SettingsPage.tsx:498` |
| `auto.frontend.x.5d5815647c` | 收起 |  | `app/src/components/StoreSection.tsx:422` +1 |
| `auto.frontend.x.5ec6f626c3` | 配置档案 |  | `app/src/pages/ModelsPage.tsx:494` |
| `auto.frontend.x.5ecc71c141` | 额外推理时长 |  | `app/src/pages/SettingsPage.tsx:469` |
| `auto.frontend.x.5ece668b53` | 3. 取消勾选：只在软件窗口处于前台时生效。 |  | `app/src/pages/SettingsPage.tsx:843` |
| `auto.frontend.x.5fc65af5b3` | 检查中… |  | `app/src/pages/SettingsPage.tsx:873` +1 |
| `auto.frontend.x.5fe7a5211b` | 每次启动时自动检查新版本，查到会在底栏询问是否安装，不会自己下载。 |  | `app/src/pages/SettingsPage.tsx:877` |
| `auto.frontend.x.6053ffffee` | 上一个音色 |  | `app/src/pages/SettingsPage.tsx:894` |
| `auto.frontend.x.60a21a8105` | 训练失败 |  | `app/src/components/TrainPanel.tsx:90` |
| `auto.frontend.x.60d612146d` | 3. 监听：耳机插在声卡上，监听设备选实体声卡的播放通道 |  | `app/src/pages/HelpPage.tsx:47` |
| `auto.frontend.x.60e69dd480` | 输出增益 |  | `app/src/pages/SettingsPage.tsx:659` |
| `auto.frontend.x.60f0f911ec` | 还没读到设备列表，暂时没法判断你装没装声卡。 引擎启动后（或在「设置 → 设备与音频」点一次「重载设备列表」）再回来看。 |  | `app/src/pages/HelpPage.tsx:214` |
| `auto.frontend.x.61f43bf584` | 界面出错了 |  | `app/src/components/ErrorBoundary.tsx:52` |
| `auto.frontend.x.61fdf63b84` | 训练轮数 |  | `app/src/components/TrainPanel.tsx:238` |
| `auto.frontend.x.6238bf9ad5` | （无） |  | `app/src/components/SeparatePanel.tsx:165` +1 |
| `auto.frontend.x.62b46f24ae` | 推荐 |  | `app/src/components/ExtrasDialog.tsx:458` +1 |
| `auto.frontend.x.63a937a39e` | 继续安装即表示您已了解并同意上述内容。 |  | `app/src/components/StoreSection.tsx:279` |
| `auto.frontend.x.63bb17a9d2` | 设备与性能设置已改动，重新「开启变声」后生效。 |  | `app/src/pages/SettingsPage.tsx:203` |
| `auto.frontend.x.63d89cdb5c` | 多块 N 卡时指定用哪一块计算。不指定就用排在第一的那块，不一定是最快的 |  | `app/src/pages/MorePage.tsx:231` |
| `auto.frontend.x.63e829016e` | 请用启动器补全 |  | `app/src/pages/MorePage.tsx:249` |
| `auto.frontend.x.63fa37071e` | 训练前清理素材优先下「人声提取」。其余按场景按需下载；标「进阶」的体积大，日常一般用不到。 |  | `app/src/components/ExtrasDialog.tsx:80` |
| `auto.frontend.x.6482fd1cfe` | 变声前先对麦克风声音降噪：输出更干净，但延迟略增。 |  | `app/src/lib/config.ts:59` |
| `auto.frontend.x.64ca1ffc2e` | 平直 |  | `app/src/pages/SettingsPage.tsx:60` |
| `auto.frontend.x.65188d08a2` | 下载中… |  | `app/src/components/StoreSection.tsx:587` +3 |
| `auto.frontend.x.65c66af000` | 已启动官方安装程序，请在弹窗中确认（需要管理员权限） |  | `app/src/pages/HelpPage.tsx:183` +1 |
| `auto.frontend.x.65d7aca5f1` | 均衡预设 |  | `app/src/pages/SettingsPage.tsx:553` |
| `auto.frontend.x.65fc81e161` | 打开 |  | `app/src/pages/MorePage.tsx:284` |
| `auto.frontend.x.672c1db9d8` | 特征 |  | `app/src/components/TrainPanel.tsx:43` |
| `auto.frontend.x.67a246a344` | 下一页 |  | `app/src/pages/ModelsPage.tsx:399` +3 |
| `auto.frontend.x.68458a0d6c` | 可尝试调低响应阈值，或调大采样块时长 |  | `app/src/pages/HelpPage.tsx:31` |
| `auto.frontend.x.68cf604e87` | 缺少推理脚本，安装可能不完整 |  | `app/src/components/TtsPanel.tsx:353` |
| `auto.frontend.x.69f4bc1200` | 软件输入 |  | `app/src/pages/HelpPage.tsx:264` |
| `auto.frontend.x.69f5974b47` | 重装… |  | `app/src/pages/MorePage.tsx:258` |
| `auto.frontend.x.6a6564705b` | 运行时版本 |  | `app/src/components/ProvisionGate.tsx:309` |
| `auto.frontend.x.6a71c2fde0` | 用一个人的干声素材训一个新音色。需要 N 卡，可能需要几小时，由硬件配置决定。 |  | `app/src/pages/MorePage.tsx:288` |
| `auto.frontend.x.6aa0d5bedd` | 运行时未就绪，请先补全运行时 |  | `app/src/hooks/useEngine.ts:153` |
| `auto.frontend.x.6aa652ccb5` | 以后再说 |  | `app/src/App.tsx:842` |
| `auto.frontend.x.6b26feecc1` | 主显卡 |  | `app/src/pages/MorePage.tsx:227` +1 |
| `auto.frontend.x.6b863e8f98` | 档案名称 |  | `app/src/pages/ModelsPage.tsx:591` |
| `auto.frontend.x.6bbeb14e4d` | ${s} 秒 |  | `app/src/components/ProvisionGate.tsx:38` |
| `auto.frontend.x.6c26ecbfb3` | 点「立即检查」则查到就直接下载安装，重启后生效。 |  | `app/src/pages/SettingsPage.tsx:878` |
| `auto.frontend.x.6c4698ee82` | 想实时听到自己的变声效果，勾选「变声时监听自己」并选择耳机。 |  | `app/src/pages/SettingsPage.tsx:228` |
| `auto.frontend.x.6c488bda4d` | 压缩强度，4:1 是常用值。比例越大越「平」，过大会发闷、失去起伏。 |  | `app/src/lib/config.ts:73` |
| `auto.frontend.x.6c908a4301` | 继续安装即表示您知晓并愿意承担相关风险。 |  | `app/src/components/StoreSection.tsx:289` |
| `auto.frontend.x.6d2e92e04d` | 失败：${String(e)} |  | `app/src/pages/HelpPage.tsx:185` |
| `auto.frontend.x.6deda26aeb` | 生成诊断包完成：${r?.path ?? ""}${note} |  | `app/src/pages/MorePage.tsx:125` |
| `auto.frontend.x.6e2aba9d02` | 背景图的显示透明度，越低越淡。 |  | `app/src/lib/config.ts:79` |
| `auto.frontend.x.6e382d3bef` | 开启后，即使软件在后台或最小化，也能用快捷键控制变声。 |  | `app/src/lib/config.ts:82` |
| `auto.frontend.x.6eb438dd5b` | 监听自己 开 / 关 |  | `app/src/pages/SettingsPage.tsx:898` |
| `auto.frontend.x.6f63f33852` | 监听（可选） |  | `app/src/pages/HelpPage.tsx:274` |
| `auto.frontend.x.703e6f531a` | 这一步不报进度，通常是在解压或校验文件，请耐心等待。 |  | `app/src/components/ProvisionGate.tsx:426` |
| `auto.frontend.x.70927369db` | 请先下载引擎资源，完成后即可选择下方的人声分离模型或训练底模。 |  | `app/src/components/ExtrasDialog.tsx:352` |
| `auto.frontend.x.70b208202c` | 选择 |  | `app/src/components/SeparatePanel.tsx:146` +2 |
| `auto.frontend.x.71031cc3ad` | CNB 发布与制品 |  | `app/src/lib/links.ts:26` |
| `auto.frontend.x.7115f2e29d` | 取消下载 |  | `app/src/components/StoreSection.tsx:386` +1 |
| `auto.frontend.x.713782084c` | 检索特征库 (.index) |  | `app/src/pages/ModelsPage.tsx:407` |
| `auto.frontend.x.71c000a0a8` | 安装包已就绪，点右侧开始安装（会弹管理员确认） |  | `app/src/pages/HelpPage.tsx:249` |
| `auto.frontend.x.71ea75cd1f` | 跟随设备 |  | `app/src/pages/SettingsPage.tsx:316` |
| `auto.frontend.x.7213716bfe` | 导出当前预设文件… |  | `app/src/pages/ModelsPage.tsx:622` |
| `auto.frontend.x.72523c6421` | 立即检查 |  | `app/src/pages/SettingsPage.tsx:873` |
| `auto.frontend.x.72527e2f0e` | 维护 |  | `app/src/pages/MorePage.tsx:311` |
| `auto.frontend.x.730b9b9abb` | 更新失败：${String(e)} |  | `app/src/App.tsx:192` |
| `auto.frontend.x.730dcfbdae` | 无可用操作 |  | `app/src/pages/ModelsPage.tsx:727` |
| `auto.frontend.x.7328deebb5` | 连接 |  | `app/src/components/ProvisionGate.tsx:291` |
| `auto.frontend.x.73996ce817` | 对方说听不到我 |  | `app/src/pages/HelpPage.tsx:13` |
| `auto.frontend.x.73b37da828` | 引擎资源未补全（缺 ${(st.engine_core_missing \|\| []).join("、") \|\| "hubert/rmvpe"}）。请先在主界面完成引擎资源下载。 |  | `app/src/components/TtsPanel.tsx:133` |
| `auto.frontend.x.746fcbb99c` | 往返延迟 |  | `app/src/pages/MorePage.tsx:274` |
| `auto.frontend.x.747374775d` | 语速 |  | `app/src/components/TtsPanel.tsx:433` |
| `auto.frontend.x.74982a8e00` | 自动（不指定） |  | `app/src/components/MainGpuPicker.tsx:35` |
| `auto.frontend.x.74a000b7ac` | 开始合成 |  | `app/src/components/TtsPanel.tsx:502` |
| `auto.frontend.x.75c3713402` | 已就绪 · ${provision.installed_variant} |  | `app/src/pages/MorePage.tsx:168` |
| `auto.frontend.x.75d7d8809a` | ${delay} ms（推理 ${infer} ms） |  | `app/src/pages/MorePage.tsx:158` |
| `auto.frontend.x.75df86cca5` | 立体声混音 |  | `app/src/pages/HelpPage.tsx:108` |
| `auto.frontend.x.76b9880829` | 结束 |  | `app/src/pages/MorePage.tsx:374` |
| `auto.frontend.x.778fc8f994` | 全部 |  | `app/src/components/StoreSection.tsx:333` |
| `auto.frontend.x.78ff5d65e5` | 多块 N 卡时指定用哪一块计算。 |  | `app/src/components/MainGpuPicker.tsx:7` |
| `auto.frontend.x.796e01d5af` | 训练 |  | `app/src/components/TrainPanel.tsx:44` |
| `auto.frontend.x.79f9110607` | 索引 |  | `app/src/components/TrainPanel.tsx:45` |
| `auto.frontend.x.7a218555fd` | 下载分离模型 |  | `app/src/components/SeparatePanel.tsx:208` |
| `auto.frontend.x.7a24f480cf` | 你实际说话用的麦克风。<br>不要选 CABLE Output。 |  | `app/src/lib/config.ts:26` |
| `auto.frontend.x.7b0909323d` | 约需一分钟，结果会打进诊断包，便于排查卡顿与延迟。 |  | `app/src/pages/MorePage.tsx:110` |
| `auto.frontend.x.7b470c4e5f` | 清晰明亮 |  | `app/src/pages/SettingsPage.tsx:63` |
| `auto.frontend.x.7bcf18641f` | 置顶 |  | `app/src/pages/PlazaPage.tsx:154` |
| `auto.frontend.x.7be46937d4` | 尚未下载安装包，点右侧会先下载再安装 |  | `app/src/pages/HelpPage.tsx:250` |
| `auto.frontend.x.7c134b6e64` | 图灵镜 |  | `app/src/components/StoreSection.tsx:559` |
| `auto.frontend.x.7cdb0a7622` | 正常，冷启动需要加载模型和运行时 |  | `app/src/pages/HelpPage.tsx:65` |
| `auto.frontend.x.7d2fe2ae0a` | 可能是网络波动或服务器无响应，不是软件卡死。 |  | `app/src/components/ProvisionGate.tsx:425` |
| `auto.frontend.x.7d4cfa5986` | 完成后会准备 VB-Cable 虚拟声卡安装包。引擎资源（hubert / rmvpe / ffmpeg）改在「其他 → 下载模型」里按需补全。 |  | `app/src/components/ProvisionGate.tsx:305` |
| `auto.frontend.x.7e9782377b` | 暂时没有可下载的分离模型。 |  | `app/src/components/ExtrasDialog.tsx:245` |
| `auto.frontend.x.7f3ebfb67b` | 不知不觉您已经变声 10 次啦！本软件完全免费，持续更新离不开大家的支持—— 只需一键即可直达，关不关注随您心意，且本提示仅出现这一次。 |  | `app/src/App.tsx:856` |
| `auto.frontend.x.7fe9bcf336` | 第三方音色未经图灵镜官方审核，请自行甄别来源可靠性，切勿盲目安装来路不明的音色。 |  | `app/src/components/StoreSection.tsx:364` |
| `auto.frontend.x.80241a56d3` | 已是最新版本 ${String(r.local)}（${clockNow()} 检查） |  | `app/src/App.tsx:107` |
| `auto.frontend.x.80d341c40a` | 温暖饱满 |  | `app/src/pages/SettingsPage.tsx:62` |
| `auto.frontend.x.80d59b5959` | 解绑 |  | `app/src/pages/ModelsPage.tsx:481` |
| `auto.frontend.x.8152d450a3` | 检查游戏/语音里的麦克风是否选成了 CABLE Output |  | `app/src/pages/HelpPage.tsx:14` |
| `auto.frontend.x.83bc4b2a5f` | 暂无音色条目。检查网络后点右上角「刷新」。 |  | `app/src/components/StoreSection.tsx:493` |
| `auto.frontend.x.83d8ae170a` | 「其他」页点「强制结束变声引擎」，再重新开启变声即可。该操作只结束残留的引擎进程，不会关闭主界面。 |  | `app/src/pages/HelpPage.tsx:61` |
| `auto.frontend.x.8425860e9d` | 共 ${models.length} 个 · 匹配 ${view.length} 个 |  | `app/src/pages/ModelsPage.tsx:89` |
| `auto.frontend.x.84a1eb0c44` | 生成诊断包前，是否先跑一次性能测试？ |  | `app/src/pages/MorePage.tsx:109` |
| `auto.frontend.x.84b7d7b6b0` | 缺少转换脚本，安装可能不完整 |  | `app/src/components/TtsPanel.tsx:135` |
| `auto.frontend.x.84ccf9394c` | 小红书号 TuringMirror |  | `app/src/lib/links.ts:48` |
| `auto.frontend.x.859b483004` | 音频变声把已有录音换成目标音色；文字合成用系统语音念字后再换音色。 二者都使用首页当前选中的 RVC 模型。 |  | `app/src/components/TtsPanel.tsx:65` |
| `auto.frontend.x.85b3f0512b` | 只看未安装 |  | `app/src/components/StoreSection.tsx:358` |
| `auto.frontend.x.87c1bc6fe6` | 正在更新 |  | `app/src/App.tsx:796` |
| `auto.frontend.x.87eb0743be` | 搜索音色 / 标签 / 作者… |  | `app/src/components/StoreSection.tsx:323` |
| `auto.frontend.x.881ebae122` | 抖音号 TuringMirror |  | `app/src/lib/links.ts:42` |
| `auto.frontend.x.893ad3c090` | 保存失败：${String(e)} |  | `app/src/pages/MorePage.tsx:69` |
| `auto.frontend.x.89a2336b6b` | （约 ${selectedSizeLabel}） |  | `app/src/components/ProvisionGate.tsx:482` |
| `auto.frontend.x.89dd7d9dec` | 消除鼻音 |  | `app/src/pages/SettingsPage.tsx:64` |
| `auto.frontend.x.8a5ef195d6` | 训练过程可能需要数小时。中断后进度将保留（含已处理的切片与已完成的轮次）， 下次使用相同名称即可恢复训练。 |  | `app/src/components/TrainPanel.tsx:296` |
| `auto.frontend.x.8b720e5330` | 生成诊断包 |  | `app/src/pages/MorePage.tsx:314` |
| `auto.frontend.x.8ba72769d6` | 选「确定」跑测试；选「取消」跳过测试，只打包日志与设置。 |  | `app/src/pages/MorePage.tsx:112` |
| `auto.frontend.x.8c57156c9d` | 开始分离 |  | `app/src/components/SeparatePanel.tsx:197` |
| `auto.frontend.x.8ce665a041` | 请仅从您信任的来源进行下载。 |  | `app/src/components/StoreSection.tsx:288` |
| `auto.frontend.x.8d5976502c` | 硬件声卡、USB 直播声卡及调音台的路由接法 |  | `app/src/pages/HelpPage.tsx:42` |
| `auto.frontend.x.8d93847089` | GitHub 源码 |  | `app/src/lib/links.ts:20` |
| `auto.frontend.x.8e6b1ba01b` | 中文路径报错 |  | `app/src/pages/HelpPage.tsx:69` |
| `auto.frontend.x.8ef23e2698` | 启用全局快捷键 |  | `app/src/pages/SettingsPage.tsx:818` |
| `auto.frontend.x.8f5fdb1c8a` | 训练仅支持 NVIDIA 显卡。当前系统的 DirectML 环境暂不支持相关训练算子。 |  | `app/src/components/TrainPanel.tsx:122` |
| `auto.frontend.x.8f61254fa2` | 这个音色的模型文件缺失或不完整，请重新下载或修复，先修好或删除后再绑定。 |  | `app/src/pages/ModelsPage.tsx:212` |
| `auto.frontend.x.8f84a93f91` | 绑定 index 文件… |  | `app/src/pages/ModelsPage.tsx:422` |
| `auto.frontend.x.8fb0cafc4d` | 作者 : ${current.author} |  | `app/src/pages/HomePage.tsx:159` |
| `auto.frontend.x.8fbb40595a` | 当前缺少：${assets.engine_core_missing.join("、")} |  | `app/src/components/ExtrasDialog.tsx:314` |
| `auto.frontend.x.9035f9b6d1` | 音频变声 |  | `app/src/components/TtsPanel.tsx:74` |
| `auto.frontend.x.90872a6528` | 文字合成 |  | `app/src/components/TtsPanel.tsx:75` |
| `auto.frontend.x.90b74980e4` | 未检测 |  | `app/src/pages/MorePage.tsx:165` |
| `auto.frontend.x.91910f2b7b` | 决定用哪个采样率工作：<br>• 跟随设备：使用声卡采样率（推荐）；<br>• 跟随模型：使用音色模型自带的采样率。<br>不确定就保持「跟随设备」。 |  | `app/src/lib/config.ts:38` |
| `auto.frontend.x.91e6c9b862` | 打开旧版控制面板 |  | `app/src/pages/MorePage.tsx:342` |
| `auto.frontend.x.9249d39bac` | 已保存，重新「开启变声」后生效 |  | `app/src/pages/MorePage.tsx:68` |
| `auto.frontend.x.92ba5de60f` | 缺少分离脚本，安装可能不完整 |  | `app/src/components/SeparatePanel.tsx:110` |
| `auto.frontend.x.93ccffa7cc` | 导入档案… |  | `app/src/pages/ModelsPage.tsx:610` |
| `auto.frontend.x.946a92f5a2` | 训练组件不全，安装可能不完整 |  | `app/src/components/TrainPanel.tsx:117` |
| `auto.frontend.x.95344bde41` | 下载图灵镜源与第三方源的音色 |  | `app/src/pages/PlazaPage.tsx:159` |
| `auto.frontend.x.9546e0b7e2` | 每天检查更新时，附带发送随机匿名编号、软件版本、显卡加速方式。 这不包含账号、音色、录音或任何定位信息。 这类规模数据主要用于向赞助商证明活跃度，是我们维持开发的方式之一。随时可在「设置 → 常规」关闭。 |  | `app/src/App.tsx:832` |
| `auto.frontend.x.95af7bd399` | 引擎正在启动，设备列表稍后出现 |  | `app/src/pages/SettingsPage.tsx:183` |
| `auto.frontend.x.966b701690` | 重载设备列表 |  | `app/src/pages/SettingsPage.tsx:322` |
| `auto.frontend.x.983328d89b` | 1. 先关掉声卡驱动自带的降噪/混响/变声，避免与本软件冲突 |  | `app/src/pages/HelpPage.tsx:54` |
| `auto.frontend.x.9a79ee8bcd` | 支持断点续传，中断后重新开始即可。请保持网络畅通。 |  | `app/src/components/ProvisionGate.tsx:487` |
| `auto.frontend.x.9ad8c4b79c` | 改后需重新「开启变声」 |  | `app/src/pages/SettingsPage.tsx:436` |
| `auto.frontend.x.9c74c2a45e` | 音高 −1 |  | `app/src/pages/SettingsPage.tsx:897` |
| `auto.frontend.x.9dd2d476cb` | 选完如果引擎用的还不是你要的那块，换一个序号再试 —— |  | `app/src/components/MainGpuPicker.tsx:10` |
| `auto.frontend.x.9f97186ee0` | 音高 +1 |  | `app/src/pages/SettingsPage.tsx:896` |
| `auto.frontend.x.a056bc39f4` | 已参与 |  | `app/src/pages/SettingsPage.tsx:804` |
| `auto.frontend.x.a0bc984876` | 输出到 |  | `app/src/components/SeparatePanel.tsx:149` +1 |
| `auto.frontend.x.a11c1a6602` | 哔哩哔哩 @图灵镜 |  | `app/src/lib/links.ts:35` |
| `auto.frontend.x.a1fdfdae84` | 已在你的设备列表里找到： |  | `app/src/pages/HelpPage.tsx:224` |
| `auto.frontend.x.a22a5eeab1` | 点击标题栏 X 或 Alt+F4 时：<br>• 每次询问：弹窗选择「最小化到托盘 / 直接关闭」；<br>• 最小化到托盘：隐藏到托盘，变声继续；<br>• 直接退出：停止变声并退出。 |  | `app/src/lib/config.ts:81` |
| `auto.frontend.x.a3480a2554` | 抖音 @图灵镜 |  | `app/src/lib/links.ts:40` |
| `auto.frontend.x.a46919fc8e` | 使用变声 |  | `app/src/components/TtsPanel.tsx:458` |
| `auto.frontend.x.a5644f4bbf` | 全局 |  | `app/src/pages/SettingsPage.tsx:978` |
| `auto.frontend.x.a5f158e6bc` | 打开性能报告文件夹 |  | `app/src/pages/MorePage.tsx:325` |
| `auto.frontend.x.a5ffdc95ee` | 已取消 |  | `app/src/pages/ModelsPage.tsx:243` +2 |
| `auto.frontend.x.a636b86646` | 打开网页版控制台 |  | `app/src/pages/MorePage.tsx:349` |
| `auto.frontend.x.a6df38586d` | 检查更新 |  | `app/src/pages/SettingsPage.tsx:868` |
| `auto.frontend.x.a821a59e88` | 启动失败：${String(e)} |  | `app/src/pages/MorePage.tsx:90` |
| `auto.frontend.x.a8bd2d876d` | VB-Cable 已经装好了，不用再装一遍。直接照下面「虚拟声卡怎么连」接线就行。 |  | `app/src/pages/HelpPage.tsx:230` |
| `auto.frontend.x.a8f48b775b` | RVC Fabric 版本 |  | `app/src/pages/MorePage.tsx:178` |
| `auto.frontend.x.a97cbce3c5` | 匿名用户数量统计（用于寻求赞助、维持免费开发）：<br>只发送随机设备编号、软件版本与显卡加速类型，不收集账号、音色、录音或任何个人信息。<br>可在「设置 → 常规」随时关闭。 |  | `app/src/lib/config.ts:84` |
| `auto.frontend.x.a9e4eb7a51` | 这里的调整会随当前音色自动保存，下次选回就是上次的状态。底栏也能快速调音高和共鸣。 |  | `app/src/pages/SettingsPage.tsx:335` |
| `auto.frontend.x.aac4f88e84` | 下载底模 |  | `app/src/components/TrainPanel.tsx:189` |
| `auto.frontend.x.ab4550db36` | 3. 确认已「开启变声」，且模式是「实时变声」而非「旁路原声」 |  | `app/src/pages/HelpPage.tsx:18` |
| `auto.frontend.x.abd52d0c37` | 正在读取设备… |  | `app/src/pages/SettingsPage.tsx:178` |
| `auto.frontend.x.ac66eb660d` | 2. 本软件的输出设备设为 CABLE Input |  | `app/src/pages/HelpPage.tsx:17` |
| `auto.frontend.x.ad0e3472be` | 在设置里开启「变声时监听自己」，监听设备选真实耳机 |  | `app/src/pages/HelpPage.tsx:23` |
| `auto.frontend.x.ae27797e12` | 输入噪声门：低于此响度的环境杂音（键盘、风扇声）会被过滤，不触发变声。<br>正常说话时，底栏电平条应明显越过竖线。 |  | `app/src/lib/config.ts:40` |
| `auto.frontend.x.ae500fb6ab` | 生成诊断包失败：${String(e)} |  | `app/src/pages/MorePage.tsx:127` |
| `auto.frontend.x.aec25def6b` | 正在下载界面更新 ${String(r.remote)}… |  | `app/src/App.tsx:129` |
| `auto.frontend.x.aff47c7f69` | 安装包没准备好：${vbcableMsg}。可以稍后在「说明」页重试。 |  | `app/src/components/ProvisionGate.tsx:448` |
| `auto.frontend.x.aff4b0df8a` | 投放 |  | `app/src/pages/PlazaPage.tsx:163` |
| `auto.frontend.x.b0106e06e7` | 当前版本 ${updateOffer.local}。${<br>                updateOffer.notes \|\|<br>                "更新会在后台下载，不影响变声使用；下载完成后重启软件即可生效。"<br>              } |  | `app/src/App.tsx:816` |
| `auto.frontend.x.b02cb49ebf` | 改变音频块的拼接方式，部分音色衔接更自然。开着试听对比即可。 |  | `app/src/lib/config.ts:61` |
| `auto.frontend.x.b052ea8cb8` | 系统语音负责吐字，可选再经 RVC 换成目标音色。结果在 User_Data\tts。 |  | `app/src/components/TtsPanel.tsx:381` |
| `auto.frontend.x.b0bef96a4b` | 我的档案 |  | `app/src/pages/ModelsPage.tsx:591` |
| `auto.frontend.x.b0e24833f7` | 展开 |  | `app/src/components/StoreSection.tsx:422` +1 |
| `auto.frontend.x.b0ec903b3f` | ${m} 分 ${s % 60} 秒 |  | `app/src/components/ProvisionGate.tsx:40` |
| `auto.frontend.x.b1bb04c308` | 使用「${TITLES[kind]}」前，需要先下载引擎资源（hubert / rmvpe / ffmpeg，约 720 MB）。下载完成后即可打开工具。 |  | `app/src/components/ToolWindow.tsx:36` |
| `auto.frontend.x.b27dd877b1` | 训完就是这个名字 |  | `app/src/components/TrainPanel.tsx:212` |
| `auto.frontend.x.b2be174f0f` | 社区音色 |  | `app/src/pages/ModelsPage.tsx:229` +1 |
| `auto.frontend.x.b2c6913616` | 安装中… |  | `app/src/components/StoreSection.tsx:580` |
| `auto.frontend.x.b3009f6985` | 关闭后仅输出系统原声 |  | `app/src/components/TtsPanel.tsx:467` |
| `auto.frontend.x.b386a7fb53` | 安装虚拟声卡 |  | `app/src/pages/HelpPage.tsx:204` |
| `auto.frontend.x.b41561d807` | 上一页 |  | `app/src/pages/ModelsPage.tsx:382` +3 |
| `auto.frontend.x.b4ac696046` | 共 0 个音色 |  | `app/src/pages/ModelsPage.tsx:87` |
| `auto.frontend.x.b4b5016e9f` | 软件输出 |  | `app/src/pages/HelpPage.tsx:269` |
| `auto.frontend.x.b584d38db8` | 共鸣/共振峰（Formant）：微调声音的粗细感，配合音高一起调，让声音更贴近目标角色。 |  | `app/src/lib/config.ts:44` |
| `auto.frontend.x.b5b981b099` | 输出降噪 |  | `app/src/pages/SettingsPage.tsx:517` |
| `auto.frontend.x.b5fba7b794` | **模式 A：麦克风走实体声卡** |  | `app/src/pages/HelpPage.tsx:44` |
| `auto.frontend.x.b643e629ae` | 共 ${changelog.length} 个版本 |  | `app/src/pages/PlazaPage.tsx:85` |
| `auto.frontend.x.b8659855b0` | 新名称 |  | `app/src/pages/ModelsPage.tsx:671` |
| `auto.frontend.x.b8d74a5e97` | 1. 点击按键框，再按下新的组合键（支持 Ctrl / Alt / Shift）； |  | `app/src/pages/SettingsPage.tsx:841` |
| `auto.frontend.x.b9d060e4f5` | 相邻音频块的过渡时长：过小接缝处会咔哒响，过大会发糊。保持默认即可。 |  | `app/src/lib/config.ts:53` |
| `auto.frontend.x.b9feeeb3a8` | 参与用户统计（可选） |  | `app/src/App.tsx:823` |
| `auto.frontend.x.ba7bd6e071` | 音频变声（官方推理）或文字合成：把录音/文本换成当前音色。 |  | `app/src/pages/MorePage.tsx:293` |
| `auto.frontend.x.bb1d8d1da8` | 未选择目标音色。请到首页选择一个音色，或关闭下方的「使用变声」。 |  | `app/src/components/TtsPanel.tsx:349` |
| `auto.frontend.x.bc19958103` | 最小化到托盘可保持后台运行；直接关闭将停止变声并退出程序。 |  | `app/src/App.tsx:757` |
| `auto.frontend.x.bc20b5032f` | 打开日志 |  | `app/src/pages/MorePage.tsx:333` |
| `auto.frontend.x.bc45fc14b1` | 运行时未就绪，先到「其他」页补全运行时 |  | `app/src/components/SeparatePanel.tsx:108` +2 |
| `auto.frontend.x.bc94a9c280` | 高级功能，一般不用 |  | `app/src/pages/MorePage.tsx:343` |
| `auto.frontend.x.bd52e3bc24` | 内录 |  | `app/src/pages/HelpPage.tsx:108` |
| `auto.frontend.x.be24590d21` | 开始训练 |  | `app/src/components/TrainPanel.tsx:291` |
| `auto.frontend.x.be70b437af` | 把歌曲拆成人声和伴奏，训练音色前用它清掉背景音乐或噪音 |  | `app/src/pages/MorePage.tsx:283` |
| `auto.frontend.x.bea562b0a7` | 浏览器预览无法联网拉取广场内容 |  | `app/src/lib/plaza.ts:60` |
| `auto.frontend.x.bfdefad36e` | 后期音效 开 / 关 |  | `app/src/pages/SettingsPage.tsx:899` |
| `auto.frontend.x.c11227b2d4` | 已更新至 ${String(b.version ?? r.remote)}，重启程序后生效 |  | `app/src/App.tsx:124` |
| `auto.frontend.x.c15e33676a` | 输入设备 |  | `app/src/pages/SettingsPage.tsx:246` |
| `auto.frontend.x.c1614d68d8` | 开启后延迟更低，但会独占声卡，其他程序可能无声。<br>一般保持关闭。 |  | `app/src/lib/config.ts:36` |
| `auto.frontend.x.c193661369` | 音色均衡 |  | `app/src/pages/SettingsPage.tsx:541` |
| `auto.frontend.x.c2352d1e60` | ${label}失败：${String(e)} |  | `app/src/pages/MorePage.tsx:101` |
| `auto.frontend.x.c2b9d351f6` | 开启后，变声声音除送往「输出设备」外，还会在「监听设备」再放一份给你听。<br>监听设备选真实耳机或音箱，不要选 CABLE 等虚拟声卡。<br>若开启后听不到声音，重新开启一次变声，并检查系统默认播放设备。 |  | `app/src/lib/config.ts:32` |
| `auto.frontend.x.c493338e8c` | 自定义 |  | `app/src/pages/SettingsPage.tsx:567` |
| `auto.frontend.x.c777a891cf` | **模式 B：走声卡内录 / 立体声混音** |  | `app/src/pages/HelpPage.tsx:49` |
| `auto.frontend.x.c7acce2c4c` | 通常设为 200。轮数越多还原度越高，但过高可能产生电音或杂音。 |  | `app/src/components/TrainPanel.tsx:247` |
| `auto.frontend.x.c7ea0cf156` | 准备下载引擎资源… |  | `app/src/components/ExtrasDialog.tsx:194` |
| `auto.frontend.x.c7f8a449e0` | 该音色来自第三方社区，图灵镜不对其安全性与质量做任何保证。 |  | `app/src/components/StoreSection.tsx:287` |
| `auto.frontend.x.c8d09cf955` | 默认 |  | `app/src/pages/ModelsPage.tsx:289` |
| `auto.frontend.x.c8e3bafbb7` | 低沉厚实 |  | `app/src/pages/SettingsPage.tsx:65` |
| `auto.frontend.x.c946d45a63` | 没有它，游戏和语音软件里的人听不到变声后的你。点「安装」会弹出官方安装程序和管理员确认。 |  | `app/src/components/ProvisionGate.tsx:451` |
| `auto.frontend.x.c96a64f150` | 实体声卡怎么连 |  | `app/src/pages/HelpPage.tsx:41` |
| `auto.frontend.x.c9efc20514` | 还没有音色~ 点「社区音色」去广场下载，或点「导入音色」添加本地音色。 |  | `app/src/pages/ModelsPage.tsx:305` |
| `auto.frontend.x.ca872f619e` | 跟随模型 |  | `app/src/pages/SettingsPage.tsx:317` |
| `auto.frontend.x.ca98fe8db7` | 声音断断续续 |  | `app/src/pages/HelpPage.tsx:30` |
| `auto.frontend.x.cad046a475` | 选 CABLE Output |  | `app/src/pages/HelpPage.tsx:280` |
| `auto.frontend.x.cb63c62e50` | 知道了 |  | `app/src/pages/SettingsPage.tsx:206` +1 |
| `auto.frontend.x.cbf7f4dada` | 下载引擎资源 |  | `app/src/components/ExtrasDialog.tsx:340` |
| `auto.frontend.x.cbff2004b0` | 请勿用于冒充他人、欺诈、造谣或其他侵害他人权益的用途； |  | `app/src/components/StoreSection.tsx:277` |
| `auto.frontend.x.cc46f7484f` | 第三方音色免责声明 |  | `app/src/components/StoreSection.tsx:286` |
| `auto.frontend.x.cd178d24a2` | 正在读取清单… |  | `app/src/components/ExtrasDialog.tsx:358` |
| `auto.frontend.x.cd8301f295` | 到「其他」页用「强制结束变声引擎」 |  | `app/src/pages/HelpPage.tsx:60` |
| `auto.frontend.x.d02e026f75` | 1. 设置 → 设备与音频 → 勾选「变声时监听自己」 |  | `app/src/pages/HelpPage.tsx:25` |
| `auto.frontend.x.d077c504cc` | 图灵镜推荐 |  | `app/src/pages/PlazaPage.tsx:252` |
| `auto.frontend.x.d0a420e1ca` | 游戏 / 语音 麦克风 |  | `app/src/pages/HelpPage.tsx:279` |
| `auto.frontend.x.d0b65d2fd2` | 状态与维护 |  | `app/src/pages/MorePage.tsx:174` |
| `auto.frontend.x.d0cb2f3a1b` | 把忽大忽小的音量压平，听感更稳。 |  | `app/src/lib/config.ts:70` |
| `auto.frontend.x.d15328af87` | 快捷键说明 |  | `app/src/pages/SettingsPage.tsx:841` |
| `auto.frontend.x.d15a7a3da1` | 浏览器预览无法拉清单 |  | `app/src/lib/voices.ts:247` |
| `auto.frontend.x.d291f67ac8` | 用于 Harvest 等 CPU 算法的线程数；用 RMVPE 等 GPU 算法时基本无影响。 |  | `app/src/lib/config.ts:56` |
| `auto.frontend.x.d359cf1384` | 觉得 RVC Fabric 好用吗？关注我们呗 |  | `app/src/App.tsx:839` |
| `auto.frontend.x.d38983b5dd` | 音色切换失败：${String(e)} |  | `app/src/pages/HomePage.tsx:119` |
| `auto.frontend.x.d3ba94b98a` | 缺 ${sr} 的训练底模。只需下载与采样率对应的那一套（与 RVC 原版 pretrained_v2 一致）。 |  | `app/src/components/TrainPanel.tsx:127` |
| `auto.frontend.x.d47379f917` | 刷新中 |  | `app/src/pages/PlazaPage.tsx:139` |
| `auto.frontend.x.d48a0bf3c8` | 运行中可热更新 · 按音色自动保存 |  | `app/src/pages/SettingsPage.tsx:334` |
| `auto.frontend.x.d4b9d6c80f` | 输入选真实麦克风，输出选 CABLE Input（游戏内的麦克风设为 CABLE Output）。 |  | `app/src/pages/SettingsPage.tsx:226` |
| `auto.frontend.x.d5c27cb2ba` | 补全… |  | `app/src/pages/MorePage.tsx:258` |
| `auto.frontend.x.d5ca969dc3` | 耳机 |  | `app/src/pages/HelpPage.tsx:276` |
| `auto.frontend.x.d69e96920e` | 部分底层依赖对中文/非 ASCII 路径兼容性较差。把安装目录移到纯英文路径（如 `D:\RVCFabric`）后重试。 |  | `app/src/pages/HelpPage.tsx:71` |
| `auto.frontend.x.d725011356` | 需补全运行时 |  | `app/src/hooks/useEngine.ts:280` |
| `auto.frontend.x.d7278f3458` | 2. 勾选「全局」：在任何软件中都生效，但该组合会被本软件独占； |  | `app/src/pages/SettingsPage.tsx:842` |
| `auto.frontend.x.d7ae8f757e` | 生成诊断包：性能测试进行中（约一分钟）… |  | `app/src/pages/MorePage.tsx:116` |
| `auto.frontend.x.d7f3306fcc` | 音高（Pitch）：男声变女声通常 +12，女声变男声通常 −12。<br>变声中可实时拖动试听。 |  | `app/src/lib/config.ts:42` |
| `auto.frontend.x.d851b62cf4` | 后台变声不受影响，可从系统托盘右键菜单继续控制。 请将「其他 → 运行状态」生成的诊断包发给我们，以便排查。 |  | `app/src/components/ErrorBoundary.tsx:53` |
| `auto.frontend.x.d8e4f74b8b` | 1. 游戏/语音的麦克风设为 CABLE Output |  | `app/src/pages/HelpPage.tsx:16` |
| `auto.frontend.x.d9702f047c` | 参与 |  | `app/src/App.tsx:827` |
| `auto.frontend.x.d9cb071850` | 1. 适当调大「采样块时长」（越大越稳，延迟也越高） |  | `app/src/pages/HelpPage.tsx:33` |
| `auto.frontend.x.da1fd957dc` | 哔哩哔哩 |  | `app/src/lib/links.ts:36` |
| `auto.frontend.x.dae828fe4f` | 第 |  | `app/src/components/StoreSection.tsx:473` |
| `auto.frontend.x.db1fdebf6f` | 打包当前音色的配置与档案，我们做针对性调参（不含模型文件） |  | `app/src/pages/MorePage.tsx:358` |
| `auto.frontend.x.dc3f6fc6fd` | 只发送随机匿名编号、软件版本、显卡加速方式；不发送账号、音色、录音或任何能定位到你的信息 |  | `app/src/pages/SettingsPage.tsx:801` |
| `auto.frontend.x.dcf690b953` | 变声时监听自己 |  | `app/src/pages/SettingsPage.tsx:284` |
| `auto.frontend.x.dd41f552d6` | 申请专业优化 |  | `app/src/pages/MorePage.tsx:357` |
| `auto.frontend.x.de5de9e783` | 可以继续等；也可以点「取消」再重来一次 —— 已经下好的部分留在本地，重开会接着下，不会白下。 |  | `app/src/components/ProvisionGate.tsx:427` |
| `auto.frontend.x.df51787548` | 可选先跑约一分钟的性能测试，再打包日志、机型信息与当前设置 |  | `app/src/pages/MorePage.tsx:318` |
| `auto.frontend.x.e0dab22b1a` | 下载失败 |  | `app/src/components/ExtrasDialog.tsx:149` |
| `auto.frontend.x.e137006ffd` | 虚拟声卡连接、常见情况与专有名词 |  | `app/src/pages/HelpPage.tsx:202` |
| `auto.frontend.x.e197a257da` | 引擎资源（hubert/rmvpe）+ 训练底模 / 人声分离模型 |  | `app/src/pages/MorePage.tsx:298` |
| `auto.frontend.x.e1e6297b67` | 读到 ${inputs.length} 个录音设备、${outputs.length} 个播放设备 |  | `app/src/pages/SettingsPage.tsx:243` |
| `auto.frontend.x.e2866d0815` | 小红书 |  | `app/src/lib/links.ts:47` |
| `auto.frontend.x.e327258774` | 强制结束变声引擎 |  | `app/src/pages/MorePage.tsx:367` |
| `auto.frontend.x.e410af7f1f` | 我自己听不到变声 |  | `app/src/pages/HelpPage.tsx:22` |
| `auto.frontend.x.e5e9953e15` | 保存当前参数为新预设 |  | `app/src/pages/ModelsPage.tsx:597` |
| `auto.frontend.x.e60febee30` | 商用前请自行确认授权。 |  | `app/src/components/StoreSection.tsx:278` |
| `auto.frontend.x.e6408f03f4` | 4. 关闭其他占用麦克风的软件 |  | `app/src/pages/HelpPage.tsx:36` |
| `auto.frontend.x.e6b7c3d266` | （无可用项） |  | `app/src/components/controls.tsx:104` |
| `auto.frontend.x.e6eed3ec41` | 组合键被其他软件占用时会注册失败，换一个即可。 |  | `app/src/pages/SettingsPage.tsx:844` |
| `auto.frontend.x.e700c7ba47` | 缺 Hubert 模型，先补全引擎资源 |  | `app/src/components/TrainPanel.tsx:119` |
| `auto.frontend.x.e7181ea0d6` | 2. 输出设备：仍选 CABLE Input，对面听到变声仍靠虚拟声卡 |  | `app/src/pages/HelpPage.tsx:46` |
| `auto.frontend.x.e78c480b93` | · 已绑定检索库 |  | `app/src/components/TtsPanel.tsx:174` |
| `auto.frontend.x.e7a64d4aaf` | NVIDIA 50 系（RTX 50xx） |  | `app/src/components/ProvisionGate.tsx:168` |
| `auto.frontend.x.e7aaa18a23` | 读取音色目录失败：${loadError} |  | `app/src/pages/HomePage.tsx:132` |
| `auto.frontend.x.e8850440f2` | 输入 |  | `app/src/components/SeparatePanel.tsx:144` +1 |
| `auto.frontend.x.e8a77f003d` | 请先下载引擎资源，再下载具体模型。 |  | `app/src/components/ExtrasDialog.tsx:212` |
| `auto.frontend.x.ea5083770c` | **注意** |  | `app/src/pages/HelpPage.tsx:53` |
| `auto.frontend.x.eb033e6340` | 可在软件内下载补全 |  | `app/src/pages/MorePage.tsx:247` |
| `auto.frontend.x.eb434c8c24` | 变声后 · 可选 |  | `app/src/pages/SettingsPage.tsx:508` |
| `auto.frontend.x.eb88ff57c9` | 已安装 |  | `app/src/components/StoreSection.tsx:554` +1 |
| `auto.frontend.x.ec35cdf525` | 合成中… |  | `app/src/components/TtsPanel.tsx:502` |
| `auto.frontend.x.ecf753d9da` | 压缩阈值 |  | `app/src/pages/SettingsPage.tsx:631` |
| `auto.frontend.x.ed2172fd78` | 查看全部 |  | `app/src/pages/PlazaPage.tsx:189` |
| `auto.frontend.x.ef00eb8f3b` | 图灵镜源 |  | `app/src/components/StoreSection.tsx:334` |
| `auto.frontend.x.ef8cc2df41` | 变声后的声音送到这里。<br>让游戏/语音里的人听到：输出选 CABLE Input，再把游戏里的麦克风设为 CABLE Output。 |  | `app/src/lib/config.ts:30` |
| `auto.frontend.x.ef92935b07` | 未参与 |  | `app/src/pages/SettingsPage.tsx:804` |
| `auto.frontend.x.efbfd16623` | 小红书 @图灵镜 |  | `app/src/lib/links.ts:46` |
| `auto.frontend.x.efc83ad78c` | 2. 游戏/语音麦克风：声卡的内录通道（叫法以声卡说明书为准） |  | `app/src/pages/HelpPage.tsx:51` |
| `auto.frontend.x.f0027cb639` | 需要已选中音色且 Runtime 已就绪。 |  | `app/src/pages/MorePage.tsx:111` |
| `auto.frontend.x.f069ff33fd` | 背景图的模糊（高斯模糊）强度。 |  | `app/src/lib/config.ts:78` |
| `auto.frontend.x.f06f8d2041` | 本地 PNG/JPG 静态图片。没有大小限制，但图片越大加载越慢，建议别超过 4K 分辨率。 |  | `app/src/lib/config.ts:77` |
| `auto.frontend.x.f0bab98244` | 已更新至 ${String(r.remote)}，重启程序后生效 |  | `app/src/App.tsx:134` |
| `auto.frontend.x.f2afde8960` | 已就绪 |  | `app/src/pages/MorePage.tsx:169` +1 |
| `auto.frontend.x.f2f07193b8` | 请输入需要合成的文本… |  | `app/src/components/TtsPanel.tsx:395` |
| `auto.frontend.x.f41830a38d` | 显卡（系统枚举） |  | `app/src/pages/MorePage.tsx:217` |
| `auto.frontend.x.f4df9977ea` | 下载并安装 |  | `app/src/App.tsx:807` |
| `auto.frontend.x.f5b3cef9e1` | 超过此响度才开始压缩，越低压得越多。 |  | `app/src/lib/config.ts:71` |
| `auto.frontend.x.f5d5101a11` | 当前版本 ${String(r.local)}，需先更新至 ${String(<br>          r.min_app_version,<br>        )} 才能继续 |  | `app/src/App.tsx:98` |
| `auto.frontend.x.f75c86ad46` | 记住选择（可在「设置 → 常规」中修改） |  | `app/src/App.tsx:766` |
| `auto.frontend.x.f7acefd2d4` | 查看 |  | `app/src/components/StoreSection.tsx:582` +1 |
| `auto.frontend.x.f7b2a6ee68` | 个 |  | `app/src/components/StoreSection.tsx:476` |
| `auto.frontend.x.f8893054c2` | 还没装分离模型。优先下载「人声提取」，清训练素材用它就够了。 |  | `app/src/components/SeparatePanel.tsx:112` |
| `auto.frontend.x.f950213ab7` | 读取中… |  | `app/src/components/StoreSection.tsx:493` +2 |
| `auto.frontend.x.f9786f5b73` | 48k 音质最佳，但显存占用更高 |  | `app/src/components/TrainPanel.tsx:233` |
| `auto.frontend.x.f9cbb1e0c6` | 未安装 · 约 720 MB |  | `app/src/components/ExtrasDialog.tsx:301` |
| `auto.frontend.x.f9ef10d27a` | 正在下载程序更新 ${String(r.remote)}… |  | `app/src/App.tsx:120` |
| `auto.frontend.x.f9f2a78f9f` | 暂无投放内容。 |  | `app/src/pages/PlazaPage.tsx:172` |
| `auto.frontend.x.fbb8ddd570` | 引擎状态 |  | `app/src/pages/MorePage.tsx:265` |
| `auto.frontend.x.fc3bad4cea` | 搜索音色名称或标签… |  | `app/src/pages/ModelsPage.tsx:281` |
| `auto.frontend.x.fc70c44b85` | 档案已导出 |  | `app/src/pages/ModelsPage.tsx:617` |
| `auto.frontend.x.fcfdac1801` | 引擎默认永远用排在第一的那块：一块 5060 一块 5090，很可能整场都在用 5060。 |  | `app/src/components/MainGpuPicker.tsx:8` |
| `auto.frontend.x.fe0eb943d7` | 界面来源 |  | `app/src/pages/MorePage.tsx:195` |
| `auto.frontend.x.ff175008d6` | 音高提取算法（F0）：<br>• RMVPE：效果最好也最快，一般不用改；<br>• Harvest：更稳但较慢；<br>• PM：最快但容易破音；<br>• FCPE / Crepe：可选的高精度算法。 |  | `app/src/lib/config.ts:49` |
| `auto.frontend.x.ffa02ab8a7` | 跟随系统，或固定浅色 / 深色。 |  | `app/src/lib/config.ts:75` |
| `auto.python.dsp_eq.0df76209a8` | 人声前倾 |  | `tools/dsp_fx.py:40` |
| `auto.python.dsp_eq.64ca1ffc2e` | 平直 |  | `tools/dsp_fx.py:39` |
| `auto.python.dsp_eq.7b470c4e5f` | 清晰明亮 |  | `tools/dsp_fx.py:42` |
| `auto.python.dsp_eq.80d341c40a` | 温暖饱满 |  | `tools/dsp_fx.py:41` |
| `auto.python.dsp_eq.89dd7d9dec` | 消除鼻音 |  | `tools/dsp_fx.py:43` |
| `auto.python.dsp_eq.c8e3bafbb7` | 低沉厚实 |  | `tools/dsp_fx.py:44` |
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
| `auto.python.webui.796e01d5af` | 训练 |  | `infer-web.py:1186` |
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
| `auto.python.webui.f7acefd2d4` | 查看 |  | `infer-web.py:1542` |
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
| `auto.python.worker.796e01d5af` | 训练 |  | `tools/train_worker.py:379` |
| `auto.python.worker.7d63558436` | 人声分离 worker：跑一次 PyMSS，把进度按行吐给 Rust 侧。<br><br>为什么不直接调 `python -m tools.pymss.cli infer`：它的进度是 tqdm 画在<br>stderr 上的进度条，要靠正则去刮，格式一变就瞎。PyMSS 的 separator 本来就收<br>`progress_callback(done, total, message)`，接上它按行输出 JSON 干净得多。<br><br>用法（Rust 侧这么调）::<br><br>    pythonw tools/separate_worker.py <请求文件.json><br><br>请求文件::<br><br>    {"model": "...", "model_dir": "...", "input": "...", "output": "...",<br>     "device": "auto", "format": "wav"}<br><br>stdout 每行一条 JSON：<br>    {"phase":"start"}                          开始<br>    {"phase":"run","done":3,"total"… |  | `tools/separate_worker.py:2` |
| `auto.python.worker.8101838a6a` | 没有特征文件，建不了索引。 |  | `tools/train_worker.py:395` |
| `auto.python.worker.828c25e1aa` | 缺少 hubert_base.pt（引擎资源未补全）。期望路径：{hubert} |  | `tools/sts_worker.py:106` |
| `auto.python.worker.8cdc6762da` | 特征提取没有产出。多半是 assets/hubert/hubert_base.pt 缺失或损坏。 |  | `tools/train_worker.py:284` |
| `auto.python.worker.90e1d19bc3` | 需要几十小时和上百小时素材，不是这个界面的用法。 |  | `tools/train_worker.py:356` |
| `auto.python.worker.992dc973f5` | 离线语音转换 worker（Speech-to-Speech / 音频 → 目标音色）。<br><br>对应官方 RVC WebUI「推理 / 批量推理」：用当前选中的 .pth 把人声音频换成<br>目标音色。不是 TTS——输入必须是声音文件。<br><br>用法::<br><br>    Runtime\python.exe tools/sts_worker.py <请求.json><br><br>请求::<br><br>    {<br>      "input": "文件或文件夹",<br>      "output": "输出目录",<br>      "model": "绝对路径.pth",<br>      "index": "可选.index",<br>      "pitch": 0,<br>      "f0method": "rmvpe",<br>      "index_rate": 0.75,<br>      "filter_radius": 3,<br>      "resample_sr": 0,<br>      "rms_mix_rate": 1.0,<br>      "protect": 0.33<br>    }<br><br>stdout 每行一条 JSON（与 separate_wor… |  | `tools/sts_worker.py:2` |
| `auto.python.worker.9b0f5b8f01` | 训练索引（%d 条特征）… |  | `tools/train_worker.py:428` |
| `auto.python.worker.9dd7399a6b` | 准备训练（%d 条样本）… |  | `tools/train_worker.py:349` |
| `auto.python.worker.9fad49fb4a` | 音高提取没有产出。换一种音高算法再试。 |  | `tools/train_worker.py:265` |
| `auto.python.worker.a5ffdc95ee` | 已取消 |  | `tools/train_worker.py:532` |
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
| `auto.python.x.18b35795d9` | 输入降噪 |  | `gui_v1.py:655` |
| `auto.python.x.19a6463690` | 音频处理 |  | `gui_v1.py:1761` |
| `auto.python.x.214c8ab7c6` | 录了几张图、重放了多少次、退回 eager 多少次。<br><br>            没有这个就没法判断加速到底有没有生效：CUDA Graph 抓不住的时候是<br>            静默退回普通调用的，延迟数字看起来只是「没变快」，和没开一模一样。 |  | `gui_v1.py:2174` |
| `auto.python.x.24c4c5929f` | 正在加载音色模型… |  | `gui_v1.py:2592` |
| `auto.python.x.25cc9d4f2c` | Main app sets TM_AUTO_START_VC=1 when user clicks 开启变声. |  | `gui_v1.py:710` |
| `auto.python.x.2ab6e66ef2` | 推理时间(ms): |  | `gui_v1.py:701` |
| `auto.python.x.2d4e0a7a97` | 换模型失败：%s |  | `gui_v1.py:2544` |
| `auto.python.x.2d9711a949` | 获取设备列表 — must fully stop stream before re-init sounddevice. |  | `gui_v1.py:2038` |
| `auto.python.x.3204d2727f` | 主声音驱动 |  | `gui_v1.py:1397` |
| `auto.python.x.36ae8ccfcf` | 采样长度 |  | `gui_v1.py:597` |
| `auto.python.x.3aa83c304c` | 输出设备 |  | `gui_v1.py:463` |
| `auto.python.x.3ca74120fd` | 换模型：文件不存在 %s |  | `gui_v1.py:2476` |
| `auto.python.x.46cf156c68` | 设备无效: {e} |  | `gui_v1.py:958` |
| `auto.python.x.47a991d18c` | 设备类型 |  | `gui_v1.py:437` |
| `auto.python.x.49dd8efdab` | 自动开始音频转换失败 |  | `gui_v1.py:739` |
| `auto.python.x.560e5fe4cf` | 需要 requests 库：pip install requests |  | `tools/download_models.py:83` |
| `auto.python.x.56173ef22a` | 输出设备不在列表中: {output_device!r} |  | `gui_v1.py:2099` |
| `auto.python.x.5655f44bf7` | 网易云 |  | `gui_v1.py:1385` |
| `auto.python.x.5ecc71c141` | 额外推理时长 |  | `gui_v1.py:643` |
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
| `auto.python.x.966b701690` | 重载设备列表 |  | `gui_v1.py:473` |
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
| `auto.python.x.b5b981b099` | 输出降噪 |  | `gui_v1.py:660` |
| `auto.python.x.b6290a6793` | 启动音频转换失败 |  | `gui_v1.py:788` |
| `auto.python.x.bff05a83cd` | 已退出 |  | `gui_v1.py:2787` |
| `auto.python.x.c155ef2300` | 网易虚拟 |  | `gui_v1.py:1384` |
| `auto.python.x.c15e33676a` | 输入设备 |  | `gui_v1.py:453` |
| `auto.python.x.c292968290` | 独占 WASAPI 设备 |  | `gui_v1.py:446` |
| `auto.python.x.c44eda71a0` | 采样率: |  | `gui_v1.py:488` |
| `auto.python.x.c88bc536f3` | 输出变声 |  | `gui_v1.py:693` |
| `auto.python.x.c8ff6b08eb` | 设备列表已刷新 |  | `gui_v1.py:2334` |
| `auto.python.x.c9b6411daa` | 设置输入输出设备（允许截断的设备名）。 |  | `gui_v1.py:2093` |
| `auto.python.x.cb2e797a0c` | 读不出 %s 的采样率：%s |  | `gui_v1.py:2455` |
| `auto.python.x.cd1e117c70` | 输入设备不在列表中: {input_device!r} |  | `gui_v1.py:2097` |
| `auto.python.x.d11aaac275` | 音频设备 |  | `gui_v1.py:492` |
| `auto.python.x.d5ca969dc3` | 耳机 |  | `gui_v1.py:1499` |
| `auto.python.x.d8c0ea3065` | 无 index 文件时可把 Index Rate 设为 0。 |  | `gui_v1.py:792` |
| `auto.python.x.dc9a2c7058` | harvest进程数 |  | `gui_v1.py:619` |
| `auto.python.x.df752e7aa9` | 音色文件不在了，仍在用上一个音色 |  | `gui_v1.py:2475` |
| `auto.python.x.f4e5f5707b` | 常规设置 |  | `gui_v1.py:592` |
| `auto.python.x.f726adc0fe` | 请选择pth文件 |  | `gui_v1.py:910` |
| `auto.python.x.f9bd877ab3` | 启用相位声码器 |  | `gui_v1.py:665` |
| `auto.python.x.f9d166976a` | 响度因子 |  | `gui_v1.py:543` |
| `auto.python.x.fbe37298bc` | 开始音频转换 |  | `gui_v1.py:683` |
| `auto.rust.feed.04be9e513a` | 留优先级最高的五个 |  | `app/src-tauri/src/plaza.rs:514` |
| `auto.rust.feed.062e5e670f` | 未开始 |  | `app/src-tauri/src/plaza.rs:474` |
| `auto.rust.feed.0881863106` | 广场广告不可关闭 |  | `app/src-tauri/src/plaza.rs:466` |
| `auto.rust.feed.15ada3dd1b` | 没另写就退回原标题 |  | `app/src-tauri/src/plaza.rs:523` |
| `auto.rust.feed.1937f75369` | 启动自动检查更新 |  | `app/src-tauri/src/plaza.rs:549` |
| `auto.rust.feed.39cb51599c` | 只有一段正文 |  | `app/src-tauri/src/plaza.rs:560` |
| `auto.rust.feed.4f35061e6d` | 短标题 |  | `app/src-tauri/src/plaza.rs:522` |
| `auto.rust.feed.5515dc7709` | 模型页横幅必须可关闭 |  | `app/src-tauri/src/plaza.rs:467` |
| `auto.rust.feed.5ba1f75537` | 整段正文 |  | `app/src-tauri/src/plaza.rs:550` |
| `auto.rust.feed.754db380c0` | 修复诊断包无反馈 |  | `app/src-tauri/src/plaza.rs:549` |
| `auto.rust.feed.772fad9699` | RVC Fabric v1.2.4 发布 |  | `app/src-tauri/src/plaza.rs:570` |
| `auto.rust.feed.7cf7bfff3c` | 过期 |  | `app/src-tauri/src/plaza.rs:473` |
| `auto.rust.feed.800d82ff2e` | 广场广告 |  | `app/src-tauri/src/plaza.rs:459` |
| `auto.rust.feed.9528c02056` | 空串 = 界面退回 title |  | `app/src-tauri/src/plaza.rs:528` |
| `auto.rust.feed.9e361609ec` | 一条都不能少，只是不再置顶 |  | `app/src-tauri/src/plaza.rs:508` |
| `auto.rust.feed.a005e42321` | 广场内容：{e} |  | `app/src-tauri/src/plaza.rs:386` |
| `auto.rust.feed.a3af639cfd` | 旧客户端 |  | `app/src-tauri/src/plaza.rs:475` |
| `auto.rust.feed.b4ce6178be` | 某声卡品牌 |  | `app/src-tauri/src/plaza.rs:423` |
| `auto.rust.feed.c7f1de0914` | 一条很长的投放标题，排一整行都嫌挤 |  | `app/src-tauri/src/plaza.rs:521` |
| `auto.rust.feed.ca8050f45e` | 真·投放 |  | `app/src-tauri/src/plaza.rs:571` |
| `auto.rust.feed.d06eb20450` | 模型页横幅 |  | `app/src-tauri/src/plaza.rs:460` |
| `auto.rust.feed.d2620f4b90` | 更新日志：{e} |  | `app/src-tauri/src/plaza.rs:396` |
| `auto.rust.feed.fcafc66aea` | 可见 |  | `app/src-tauri/src/plaza.rs:476` |
| `auto.rust.i18n_rs.3363f3729b` | 加载 |  | `app/src-tauri/src/i18n.rs:235` |
| `auto.rust.vb_cable.04c4e3b2b3` | 下载失败：{e} |  | `app/src-tauri/src/engine_assets.rs:149` |
| `auto.rust.vb_cable.0707e8af4e` | 解压失败：{e} |  | `app/src-tauri/src/engine_assets.rs:152` |
| `auto.rust.webui.2bd41b71bb` | 原版实时面板启动中，冷启动约 20–40 秒（要加载 torch/CUDA）。 |  | `app/src-tauri/src/legacy.rs:108` |
| `auto.rust.webui.324ed94533` | 实时面板启动前同步 inuse 失败：{e} |  | `app/src-tauri/src/legacy.rs:95` |
| `auto.rust.webui.4f09ae24cf` | Runtime 未就绪，请先在首次运行向导里补全运行时 |  | `app/src-tauri/src/legacy.rs:29` |
| `auto.rust.webui.552325722d` | 找不到实时面板脚本：{} |  | `app/src-tauri/src/legacy.rs:88` |
| `auto.rust.webui.abad006573` | 找不到 WebUI 脚本：{} |  | `app/src-tauri/src/legacy.rs:116` |
| `auto.rust.webui.c75f611a0a` | WebUI 正在后台启动，约 20–40 秒后浏览器可以打开。 |  | `app/src-tauri/src/legacy.rs:146` |
| `auto.rust.webui.d89630eacd` | 启动 {}（pid {pid}），日志 {} |  | `app/src-tauri/src/legacy.rs:78` |
| `auto.rust.webui.f1f3d2302b` | 启动失败：{e} |  | `app/src-tauri/src/legacy.rs:76` |
| `auto.rust.worker.034038e6e3` | kill_tree pid={pid} (我们记录的 pid，镜像路径没匹配上) |  | `app/src-tauri/src/worker.rs:414` |
| `auto.rust.worker.1f7bc7e185` | 找不到实时 worker: {} |  | `app/src-tauri/src/worker.rs:456` |
| `auto.rust.worker.46a6a2f91c` | 找不到 Runtime\pythonw.exe（根目录 {}）。请先补全 Runtime。 |  | `app/src-tauri/src/worker.rs:460` |
| `auto.rust.worker.496951c554` | 变声引擎进程意外退出（常见：显存不足、声卡被占用）。已清理残留，请再试。 |  | `app/src-tauri/src/worker.rs:699` |
| `auto.rust.worker.7764d6bdd2` | worker 未运行 |  | `app/src-tauri/src/worker.rs:755` |
| `auto.rust.worker.7da520ca1f` | 启动超时且引擎已退出，请查看 User_Data/logs/realtime_worker.log |  | `app/src-tauri/src/worker.rs:710` |
| `auto.rust.worker.b3b2c06973` | 还没有选中的音色 |  | `app/src-tauri/src/worker.rs:777` |
| `auto.rust.worker.ec821fd87a` | 无法启动 worker: {e} |  | `app/src-tauri/src/worker.rs:517` |
| `auto.rust.worker.fe67b1d716` | skip kill pid={pid} (不是 python 进程，可能是复用的 pid) |  | `app/src-tauri/src/worker.rs:420` |
| `auto.rust.x.007e8f085e` | 音色包{e} |  | `app/src-tauri/src/store.rs:326` |
| `auto.rust.x.0196cf51cf` | 已跑性能测试：{} |  | `app/src-tauri/src/shell_extras.rs:423` |
| `auto.rust.x.01eba6e7b6` | 音色文件缺失或不完整 |  | `app/src-tauri/src/voices.rs:605` |
| `auto.rust.x.0350fdf3a0` | 解压更新失败：{e} |  | `app/src-tauri/src/update.rs:242` |
| `auto.rust.x.03b08ed8b0` | 警告：主线程 10 秒没有响应，窗口此刻是卡住的 |  | `app/src-tauri/src/lib.rs:1424` |
| `auto.rust.x.07bbf0331b` | 正在加载分离模型… |  | `app/src-tauri/src/separate.rs:213` |
| `auto.rust.x.083e3aad12` | NVIDIA 50 系 CUDA Runtime |  | `app/src-tauri/src/provision.rs:253` |
| `auto.rust.x.090840132b` | 转换中… |  | `app/src-tauri/src/sts.rs:261` |
| `auto.rust.x.090dc6f57d` | 全路径对得上时不能被同名文件抢走 |  | `app/src-tauri/src/voices.rs:1706` |
| `auto.rust.x.099b3eb863` | 更新地址为空 |  | `app/src-tauri/src/update.rs:222` |
| `auto.rust.x.099b711760` | 含盘符路径：{name} |  | `app/src-tauri/src/extract.rs:47` |
| `auto.rust.x.09d3c05d6b` | 音色名不能以点开头 |  | `app/src-tauri/src/train.rs:204` |
| `auto.rust.x.09dfaea8c0` | 运行时清单缺少有效的 sha256，已拒绝下载。 |  | `app/src-tauri/src/provision.rs:479` |
| `auto.rust.x.0b2b13c141` | 系统语音没有生成声音文件。请到「设置 → 时间和语言 → 语音」里确认装了语音包。 |  | `app/src-tauri/src/tts.rs:167` |
| `auto.rust.x.0c6c58c683` | 这个音色还没有下载好的文件 |  | `app/src-tauri/src/store.rs:945` |
| `auto.rust.x.0d53652ff2` | {bad:?} 应当被拒绝 |  | `app/src-tauri/src/store.rs:1132` |
| `auto.rust.x.0dabaf60ef` | 音色名不能为空 |  | `app/src-tauri/src/train.rs:192` |
| `auto.rust.x.101fd24d34` | 解压后未找到 Runtime\python.exe。 |  | `app/src-tauri/src/extract.rs:217` |
| `auto.rust.x.1029edff5a` | （主） |  | `app/src-tauri/src/window_watch.rs:123` |
| `auto.rust.x.104ec2bbf7` | 分离完成 |  | `app/src-tauri/src/separate.rs:244` |
| `auto.rust.x.1090b966ea` | 复制 .pth 失败: {e} |  | `app/src-tauri/src/voices.rs:1515` |
| `auto.rust.x.1245a7db42` | 已下载，待你确认后安装 |  | `app/src-tauri/src/store.rs:703` |
| `auto.rust.x.128dff0d7b` | 连接中… · 准备下载引擎资源约 {} |  | `app/src-tauri/src/lib.rs:84` |
| `auto.rust.x.137f731bc3` | 换音色失败（{}）。详情见 User_Data/logs/tts.log |  | `app/src-tauri/src/tts.rs:340` |
| `auto.rust.x.13b868078a` | 还原：已恢复 WS_THICKFRAME（仍无系统描边） |  | `app/src-tauri/src/window_watch.rs:318` |
| `auto.rust.x.1455f353e7` | 保存失败：{e} |  | `app/src-tauri/src/config.rs:411` |
| `auto.rust.x.17d2e9d328` | 窗口状态（{phase}）：可见={} 最小化={} 位置={} 尺寸={} 缩放={} |  | `app/src-tauri/src/window_watch.rs:97` |
| `auto.rust.x.17fada585f` | 光标位置：{:.0},{:.0} |  | `app/src-tauri/src/window_watch.rs:141` |
| `auto.rust.x.18755acbbb` | 根目录 |  | `app/src-tauri/src/voices.rs:1737` |
| `auto.rust.x.1a66c860cd` | 拿不到分离进程的输出 |  | `app/src-tauri/src/separate.rs:198` |
| `auto.rust.x.1b85dd8d61` | 甲 |  | `app/src-tauri/src/voices.rs:1712` |
| `auto.rust.x.1bedd33b11` | 一次最多 {MAX_CHARS} 字，先分几段 |  | `app/src-tauri/src/tts.rs:239` |
| `auto.rust.x.1bf4a01d78` | 御姐音 |  | `app/src-tauri/src/voices.rs:90` |
| `auto.rust.x.1cf582864a` | 开始下载 {name}… |  | `app/src-tauri/src/store.rs:652` |
| `auto.rust.x.1cfc5eb379` | 空目录没有可安装的东西 |  | `app/src-tauri/src/store.rs:1141` |
| `auto.rust.x.1de5ef2b1d` | sha256 不匹配<br>期望 {exp}<br>实际 {got} |  | `app/src-tauri/src/download.rs:83` |
| `auto.rust.x.20ac2e2a0c` | 空目录不该显示成「待安装」 |  | `app/src-tauri/src/store.rs:1168` |
| `auto.rust.x.217047672d` | 起不来训练进程：{e} |  | `app/src-tauri/src/train.rs:317` |
| `auto.rust.x.217b12a5cb` | 导出当前档案（可分享） |  | `app/src-tauri/src/voices.rs:1398` |
| `auto.rust.x.21ce93c732` | 打开文件失败: {e} |  | `app/src-tauri/src/download.rs:70` |
| `auto.rust.x.227d108a35` | Runtime 已就绪，跳过下载。 |  | `app/src-tauri/src/provision.rs:455` |
| `auto.rust.x.2282c91c77` | 分离中… |  | `app/src-tauri/src/separate.rs:219` |
| `auto.rust.x.22a95f37e3` | 没有这个工具窗口：{kind} |  | `app/src-tauri/src/tool_window.rs:83` |
| `auto.rust.x.22d9b9afb9` | 少女 |  | `app/src-tauri/src/voices.rs:77` |
| `auto.rust.x.242a3a8640` | 压缩包{e} |  | `app/src-tauri/src/extract.rs:232` |
| `auto.rust.x.24fa3373ec` | 找不到推理脚本：{} |  | `app/src-tauri/src/tts.rs:277` |
| `auto.rust.x.25865a0d91` | 正在换成你的音色… |  | `app/src-tauri/src/tts.rs:280` |
| `auto.rust.x.2633fe7d2f` | 音色名不能含 \ / : * ? " < > \| 这些字符 |  | `app/src-tauri/src/train.rs:198` |
| `auto.rust.x.26afc09bec` | main_gpu 不该被写进 inuse |  | `app/src-tauri/src/config.rs:634` |
| `auto.rust.x.26bc84961c` | 女 |  | `app/src-tauri/src/voices.rs:77` |
| `auto.rust.x.2778835623` | 下载引擎资源 {} / {}（{:.1}%） |  | `app/src-tauri/src/lib.rs:87` |
| `auto.rust.x.27ecfba771` | 警告：系统报告 0 个显示器，窗口位置无法校正 |  | `app/src-tauri/src/window_watch.rs:113` |
| `auto.rust.x.281cb87781` | 下载的模型文件过小，可能不是有效 .pth |  | `app/src-tauri/src/store.rs:768` |
| `auto.rust.x.291eab062c` | 官方优化 |  | `app/src-tauri/src/voices.rs:996` |
| `auto.rust.x.298dd55e6d` | force_kill: 重写音色配置失败：{e} |  | `app/src-tauri/src/lib.rs:773` |
| `auto.rust.x.2a330f81d4` | mute 是保留名字，换一个 |  | `app/src-tauri/src/train.rs:201` |
| `auto.rust.x.2ae4c43ac6` | 未检测到完整 Runtime（需含 torch）。可在本页下载补全。 |  | `app/src-tauri/src/provision.rs:368` |
| `auto.rust.x.2b50a39fbb` | 找不到转换脚本：{} |  | `app/src-tauri/src/sts.rs:158` |
| `auto.rust.x.2d0c1739e0` | 圆角：DWM 不支持（Win10 正常，HRESULT={hr:#x}），改用窗口区域裁切 |  | `app/src-tauri/src/window_watch.rs:373` |
| `auto.rust.x.2e33db9056` | 合成完成 |  | `app/src-tauri/src/tts.rs:258` |
| `auto.rust.x.2eb8caf80a` | 萝莉 |  | `app/src-tauri/src/voices.rs:77` |
| `auto.rust.x.30858683aa` | 最大化：已摘厚框并钳到工作区（不碰 DWM NC 策略） |  | `app/src-tauri/src/window_watch.rs:303` |
| `auto.rust.x.309e44c96e` | {bad} 不该出现在主显卡候选里 |  | `app/src-tauri/src/provision.rs:688` |
| `auto.rust.x.33d04e20c0` | 清单中没有可用的 Runtime 下载地址。 |  | `app/src-tauri/src/provision.rs:472` |
| `auto.rust.x.3458316756` | 乙 |  | `app/src-tauri/src/voices.rs:1713` |
| `auto.rust.x.34e863a12e` | 校验引擎资源… |  | `app/src-tauri/src/lib.rs:82` |
| `auto.rust.x.361cb27e7b` | 暂存目录里没有可安装的文件 |  | `app/src-tauri/src/store.rs:973` |
| `auto.rust.x.36c2e47b48` | 非字母数字 |  | `app/src-tauri/src/shell_extras.rs:718` |
| `auto.rust.x.38ad9afc9b` | 路径非法：{name} |  | `app/src-tauri/src/extract.rs:54` |
| `auto.rust.x.38d4c44c83` | 已经有一个分离任务在跑了 |  | `app/src-tauri/src/separate.rs:113` |
| `auto.rust.x.3967a4b124` | 检测到 NVIDIA：{}，推荐 nvidia（CUDA）运行时 |  | `app/src-tauri/src/provision.rs:56` |
| `auto.rust.x.3a05d4d51e` | 连接中… · 准备下载声卡安装包 |  | `app/src-tauri/src/lib.rs:122` |
| `auto.rust.x.3b227dfa30` | 校验声卡安装包… |  | `app/src-tauri/src/lib.rs:118` |
| `auto.rust.x.3ba595eced` | models 目录不存在 |  | `app/src-tauri/src/voices.rs:832` |
| `auto.rust.x.3c07b16355` | 音色目录不存在 |  | `app/src-tauri/src/voices.rs:829` |
| `auto.rust.x.3c689400b4` | 男声 |  | `app/src-tauri/src/voices.rs:83` |
| `auto.rust.x.3ca928cd40` | 档案 |  | `app/src-tauri/src/voices.rs:1034` |
| `auto.rust.x.3d9fe9e5d0` | 别人家的音色 |  | `app/src-tauri/src/voices.rs:1697` |
| `auto.rust.x.3db536a84d` | 圆角：DWM 已生效（无系统描边） |  | `app/src-tauri/src/window_watch.rs:362` |
| `auto.rust.x.3e8d6d909c` | 引擎资源不完整（缺 {miss}）。请先在主界面完成「引擎资源」下载（hubert / rmvpe / ffmpeg）。 |  | `app/src-tauri/src/sts.rs:153` |
| `auto.rust.x.3eb4761a2e` | 界面已挂载（共 {} 个资源请求） |  | `app/src-tauri/src/ui_assets.rs:104` |
| `auto.rust.x.40018c2fe1` | 没有可热更新的参数 |  | `app/src-tauri/src/lib.rs:817` |
| `auto.rust.x.40019094c0` | 没有可用的音色模型，请先在首页选一个音色再跑性能测试 |  | `app/src-tauri/src/shell_extras.rs:290` |
| `auto.rust.x.407187444b` | 正在下载 {label} |  | `app/src-tauri/src/extra_assets.rs:432` |
| `auto.rust.x.40dc667415` | 音色 {id} 缺少有效的 sha256，已拒绝安装 |  | `app/src-tauri/src/store.rs:635` |
| `auto.rust.x.41e7454584` | 音色包内没有 .pth 文件 |  | `app/src-tauri/src/store.rs:454` |
| `auto.rust.x.42b898eb36` | 已经有一个下载在跑了 |  | `app/src-tauri/src/extra_assets.rs:380` |
| `auto.rust.x.4401758653` | 窗口是隐藏的，显示出来 |  | `app/src-tauri/src/window_watch.rs:148` |
| `auto.rust.x.4500b5dfc7` | 第三方 |  | `app/src-tauri/src/store.rs:281` |
| `auto.rust.x.45254e302b` | connecting:{} · {} 连接 · 建立连接… |  | `app/src-tauri/src/download.rs:250` |
| `auto.rust.x.45309ba4c5` | Runtime 未就绪，无法开启变声 |  | `app/src-tauri/src/lib.rs:525` |
| `auto.rust.x.4546433411` | 训练后 |  | `app/src-tauri/src/train.rs:364` |
| `auto.rust.x.461189f186` | 音频 |  | `app/src-tauri/src/sts.rs:97` +1 |
| `auto.rust.x.46ffa5479e` | 选择待转换音频所在文件夹 |  | `app/src-tauri/src/sts.rs:89` |
| `auto.rust.x.47a27ebb17` | 保存设置失败：{e} |  | `app/src-tauri/src/config.rs:345` |
| `auto.rust.x.47baa6fbb7` | 已经有一个合成任务在跑了 |  | `app/src-tauri/src/tts.rs:209` |
| `auto.rust.x.47c37d6efa` | 未检测到显卡，请手动选择运行时版本 |  | `app/src-tauri/src/provision.rs:33` |
| `auto.rust.x.494f3ed5a0` | 请先选好输入文件和输出目录 |  | `app/src-tauri/src/separate.rs:144` |
| `auto.rust.x.4a02ebe151` | 压缩包路径不安全：{name} |  | `app/src-tauri/src/extract.rs:237` |
| `auto.rust.x.4ad9fdccd9` | 写入 inuse 配置失败：{e} |  | `app/src-tauri/src/config.rs:306` |
| `auto.rust.x.4bbcf94739` | 下载完成 |  | `app/src-tauri/src/extra_assets.rs:451` |
| `auto.rust.x.4c65a5e25e` | NVIDIA（推荐大多数 N 卡） |  | `app/src-tauri/src/provision.rs:312` |
| `auto.rust.x.4d568e3db9` | 空串不能拿去注册 |  | `app/src-tauri/src/shell_extras.rs:714` |
| `auto.rust.x.4dae253817` | 动作名有重复 |  | `app/src-tauri/src/shell_extras.rs:793` |
| `auto.rust.x.4de146c235` | 解压 Runtime… {} / {} |  | `app/src-tauri/src/provision.rs:614` |
| `auto.rust.x.4df93f64ef` | 主线程已恢复 |  | `app/src-tauri/src/lib.rs:1427` |
| `auto.rust.x.4e723e58f7` | 先写点要念的字 |  | `app/src-tauri/src/tts.rs:236` |
| `auto.rust.x.4f592d4fc2` | 起不来转换进程：{e} |  | `app/src-tauri/src/sts.rs:232` |
| `auto.rust.x.501fdcd3ef` | 选择背景图 |  | `app/src-tauri/src/lib.rs:200` |
| `auto.rust.x.5067245760` | 解压失败 {path}: {e} |  | `app/src-tauri/src/extract.rs:177` |
| `auto.rust.x.50b4ac5f07` | 等推理进程失败：{e} |  | `app/src-tauri/src/tts.rs:336` |
| `auto.rust.x.5122640939` | 改主显卡必须提示重开变声，实际 needs_restart = {restart:?} |  | `app/src-tauri/src/config.rs:647` |
| `auto.rust.x.51625d909c` | 男 |  | `app/src-tauri/src/voices.rs:83` |
| `auto.rust.x.5164f3e0db` | 缺少 tools/train_worker.py，安装不完整 |  | `app/src-tauri/src/train.rs:215` |
| `auto.rust.x.54a91d1fae` | 转换进程异常退出（{}）。详情见 User_Data/logs/sts.log |  | `app/src-tauri/src/sts.rs:283` |
| `auto.rust.x.54b3625b92` | 导入音色… |  | `app/src-tauri/src/voices.rs:1413` |
| `auto.rust.x.5584cc4752` | 不能删除默认档案 |  | `app/src-tauri/src/voices.rs:1296` |
| `auto.rust.x.56a4192e84` | 连接中… · 准备下载声卡安装包约 {} |  | `app/src-tauri/src/lib.rs:120` |
| `auto.rust.x.575b2cd0cf` | 别的采样率不该跟着变就绪 |  | `app/src-tauri/src/train.rs:401` |
| `auto.rust.x.57e96406c7` | 界面资源读取失败 {}：{e} |  | `app/src-tauri/src/ui_assets.rs:210` |
| `auto.rust.x.582c50066c` | 字 |  | `app/src-tauri/src/tts.rs:383` |
| `auto.rust.x.58a0882f6f` | 解压完成 |  | `app/src-tauri/src/provision.rs:618` |
| `auto.rust.x.59a7e5447e` | {} 下载失败：{e} |  | `app/src-tauri/src/extra_assets.rs:440` |
| `auto.rust.x.5a7c8b5a25` | 启动前同步 inuse 失败: {e} |  | `app/src-tauri/src/lib.rs:537` |
| `auto.rust.x.5b06a8fa54` | 只有 G 没有 D 训不起来 |  | `app/src-tauri/src/train.rs:397` |
| `auto.rust.x.5c2f330361` | 连接中… · 约 {} |  | `app/src-tauri/src/provision.rs:573` |
| `auto.rust.x.5c5f9ed8e4` | 补全后预热 worker：读到 {n} 个输入设备 |  | `app/src-tauri/src/provision.rs:639` |
| `auto.rust.x.5ca337dd03` | sha256 格式无效 |  | `app/src-tauri/src/download.rs:68` |
| `auto.rust.x.5ca65185f2` | 音色未配置下载地址 |  | `app/src-tauri/src/store.rs:718` |
| `auto.rust.x.5ec6f626c3` | 配置档案 |  | `app/src-tauri/src/voices.rs:1314` |
| `auto.rust.x.5ee0565f28` | 写请求文件失败：{e} |  | `app/src-tauri/src/separate.rs:167` +2 |
| `auto.rust.x.5ff8d648a8` | 中间空段 |  | `app/src-tauri/src/shell_extras.rs:716` |
| `auto.rust.x.60a21a8105` | 训练失败 |  | `app/src-tauri/src/train.rs:337` |
| `auto.rust.x.60e2bcad85` | 导入 |  | `app/src-tauri/src/voices.rs:995` |
| `auto.rust.x.612dddefc4` | 选择数据集目录（里面放这个人的干声音频） |  | `app/src-tauri/src/lib.rs:735` |
| `auto.rust.x.61ddc8a3bf` | 找不到分离脚本：{} |  | `app/src-tauri/src/separate.rs:141` |
| `auto.rust.x.625da2c547` | 缺少 logs/mute 静音样本，安装不完整 |  | `app/src-tauri/src/train.rs:235` |
| `auto.rust.x.6462f5c407` | 找不到可替换的 frontend 目录，本次安装无法热更界面 |  | `app/src-tauri/src/update.rs:232` |
| `auto.rust.x.65cc9d198a` | === RVC Fabric {} 启动（pid {}）=== |  | `app/src-tauri/src/lib.rs:1213` |
| `auto.rust.x.6619dda8e2` | 写不了文本文件：{e} |  | `app/src-tauri/src/tts.rs:134` |
| `auto.rust.x.66cf378dad` | 内置（随程序打包） |  | `app/src-tauri/src/ui_assets.rs:236` |
| `auto.rust.x.6832505652` | 选择特征索引文件 (.index) |  | `app/src-tauri/src/voices.rs:958` |
| `auto.rust.x.68759edc4b` | 拿不到转换进程的输出 |  | `app/src-tauri/src/sts.rs:233` |
| `auto.rust.x.6a025ac81b` | 已经有一个转换任务在跑了 |  | `app/src-tauri/src/sts.rs:125` |
| `auto.rust.x.6a3b354477` | 尚未配置更新签名密钥，请到发布页手动下载新版本 |  | `app/src-tauri/src/update.rs:426` |
| `auto.rust.x.6aaa2fc9a9` | {label} · 音高 {sign}{pitch} 共鸣 {formant:.2} |  | `app/src-tauri/src/voices.rs:736` |
| `auto.rust.x.6b25a5378d` | 尾巴上挂个空段 |  | `app/src-tauri/src/shell_extras.rs:715` |
| `auto.rust.x.6b3e0028b8` | 正在加载音色… |  | `app/src-tauri/src/sts.rs:251` |
| `auto.rust.x.6b42cff431` | 正在解压安装… |  | `app/src-tauri/src/store.rs:711` |
| `auto.rust.x.6bde20da46` | 连接中… · 准备下载引擎资源 |  | `app/src-tauri/src/lib.rs:86` |
| `auto.rust.x.6c0434f6f2` | 启动 12 秒后 |  | `app/src-tauri/src/lib.rs:1393` |
| `auto.rust.x.6c203db8e2` | 窗口落在所有显示器之外，拉回 {},{} |  | `app/src-tauri/src/window_watch.rs:171` |
| `auto.rust.x.6c4b38602a` | 请先选好数据集目录 |  | `app/src-tauri/src/train.rs:240` |
| `auto.rust.x.6ca6738e54` | 小明 |  | `app/src-tauri/src/train.rs:382` |
| `auto.rust.x.6cdd7fc584` | 未命名档案 |  | `app/src-tauri/src/voices.rs:1229` |
| `auto.rust.x.6ec08cc8d9` | 竖带修复：渲染器 15 秒内未就绪，放弃动框架 |  | `app/src-tauri/src/window_watch.rs:417` |
| `auto.rust.x.6f0a06a10f` | 源 .pth 不存在 |  | `app/src-tauri/src/voices.rs:1609` |
| `auto.rust.x.6fe5607f45` | 起不来 PowerShell：{e} |  | `app/src-tauri/src/tts.rs:107` |
| `auto.rust.x.70f6a74f68` | 压缩包含空路径 |  | `app/src-tauri/src/extract.rs:44` |
| `auto.rust.x.713173a2d7` | 音色包内 .pth 过小，可能损坏 |  | `app/src-tauri/src/store.rs:457` |
| `auto.rust.x.733f7e7b3f` | 用户跳过了性能测试 |  | `app/src-tauri/src/shell_extras.rs:432` |
| `auto.rust.x.735eb4e9fd` | config::defaults() 里没有 {k} |  | `app/src-tauri/src/shell_extras.rs:766` |
| `auto.rust.x.74aef4af02` | 解压完成但未检测到 torch，Runtime 可能不完整。 |  | `app/src-tauri/src/provision.rs:623` |
| `auto.rust.x.74d5d45130` | 系统里没有这把嗓子：{voice} |  | `app/src-tauri/src/tts.rs:125` |
| `auto.rust.x.75af179e2d` | 圆角：拿不到 HWND，跳过 |  | `app/src-tauri/src/window_watch.rs:341` |
| `auto.rust.x.75b84a31d6` | Runtime 未就绪，请先补全运行时 |  | `app/src-tauri/src/separate.rs:137` +3 |
| `auto.rust.x.76bf90ae3e` | 不用检索库（仅 .pth） |  | `app/src-tauri/src/voices.rs:792` |
| `auto.rust.x.770c23276d` | 校验 sha256…（{}） |  | `app/src-tauri/src/provision.rs:560` |
| `auto.rust.x.778fc8f994` | 全部 |  | `app/src-tauri/src/voices.rs:957` |
| `auto.rust.x.779462b7f2` | {} 落地失败：{e} |  | `app/src-tauri/src/extra_assets.rs:444` |
| `auto.rust.x.7801d82550` | 路径越界：{name} |  | `app/src-tauri/src/extract.rs:53` |
| `auto.rust.x.787332269e` | PowerShell 执行失败 |  | `app/src-tauri/src/tts.rs:109` |
| `auto.rust.x.7935e3dd3e` | 替换界面失败：{e} |  | `app/src-tauri/src/update.rs:261` |
| `auto.rust.x.79a3d2ebab` | 读取 tar 失败: {e} |  | `app/src-tauri/src/extract.rs:162` |
| `auto.rust.x.79a71841b6` | 建不了工具窗口：{e} |  | `app/src-tauri/src/tool_window.rs:112` |
| `auto.rust.x.79ab43af97` | 下载中 {} / {}（{:.1}%）· {} |  | `app/src-tauri/src/provision.rs:575` |
| `auto.rust.x.79b552d700` | 选择待转换的音频 |  | `app/src-tauri/src/sts.rs:91` |
| `auto.rust.x.7a048346cb` | 移除旧 Runtime… |  | `app/src-tauri/src/provision.rs:463` |
| `auto.rust.x.7ba52d2bf3` | 选择要分离的音频 |  | `app/src-tauri/src/lib.rs:575` |
| `auto.rust.x.7c134b6e64` | 图灵镜 |  | `app/src-tauri/src/store.rs:286` |
| `auto.rust.x.7c8951a7c3` | 找不到音色包：{} |  | `app/src-tauri/src/store.rs:442` |
| `auto.rust.x.7d1c1ee831` | 警告：12 秒内界面没有挂载（白屏）。UI 来源 {} · 已处理 {} 个资源请求 · 404 {} 次 |  | `app/src-tauri/src/lib.rs:1385` |
| `auto.rust.x.7dc4ea39fd` | 训练进程结束了但没报告结果 |  | `app/src-tauri/src/train.rs:361` |
| `auto.rust.x.7fdbc694cb` | provision_status 用了 {ms} ms |  | `app/src-tauri/src/lib.rs:894` |
| `auto.rust.x.80760b3090` | 分离进程异常退出（{}）。详情见 User_Data/logs/separate.log |  | `app/src-tauri/src/separate.rs:240` |
| `auto.rust.x.80b25fdbcd` | 删除失败：{e} |  | `app/src-tauri/src/store.rs:954` |
| `auto.rust.x.8289d5d0bc` | 检测到 NVIDIA 50 系：{}，推荐 nvidia50 运行时 |  | `app/src-tauri/src/provision.rs:45` |
| `auto.rust.x.84256012c6` | 性能测试启动失败：{e} |  | `app/src-tauri/src/shell_extras.rs:394` |
| `auto.rust.x.862abb3838` | 外部目录 {} |  | `app/src-tauri/src/ui_assets.rs:235` |
| `auto.rust.x.86cbf0fb3f` | 再删一次也不该报错 |  | `app/src-tauri/src/store.rs:1184` |
| `auto.rust.x.88d3b1cad9` | 只允许打开 http/https 链接 |  | `app/src-tauri/src/lib.rs:441` |
| `auto.rust.x.8923a00d0b` | 默认（原始参数） |  | `app/src-tauri/src/voices.rs:728` |
| `auto.rust.x.899c21edd3` | 路径不在音色库内 |  | `app/src-tauri/src/voices.rs:835` |
| `auto.rust.x.89f4473a33` | {k} 应该有窗口规格 |  | `app/src-tauri/src/tool_window.rs:139` |
| `auto.rust.x.8af26d69aa` | 活动档案文件不存在 |  | `app/src-tauri/src/voices.rs:1377` |
| `auto.rust.x.8c8dade1e1` | 复制 pth: {e} |  | `app/src-tauri/src/store.rs:522` |
| `auto.rust.x.8cdca7ff61` | 补丁装过了还提示 = 无限循环 |  | `app/src-tauri/src/update.rs:343` |
| `auto.rust.x.8cfc8f198c` | 未找到该音色 |  | `app/src-tauri/src/voices.rs:603` |
| `auto.rust.x.8d31697e4e` | {bad:?} 逃出了 downloads: {s} |  | `app/src-tauri/src/store.rs:1127` |
| `auto.rust.x.8fd94350c5` | 我选的音色 |  | `app/src-tauri/src/voices.rs:1698` |
| `auto.rust.x.90d174c86a` | 安装更新失败：{e} |  | `app/src-tauri/src/update.rs:434` |
| `auto.rust.x.90e6bba99d` | 移动 Runtime 失败: {e} |  | `app/src-tauri/src/extract.rs:212` |
| `auto.rust.x.9273991f94` | 建不了缓存目录：{e} |  | `app/src-tauri/src/tts.rs:128` |
| `auto.rust.x.93b36c5670` | {k} 的初始尺寸比最小尺寸还小 |  | `app/src-tauri/src/tool_window.rs:164` |
| `auto.rust.x.9450dbe674` | 音高 {pitch:+} · 共鸣 {formant:.2} |  | `app/src-tauri/src/voices.rs:1115` |
| `auto.rust.x.950d0895e7` | 音色名太长了 |  | `app/src-tauri/src/train.rs:195` |
| `auto.rust.x.9a4f5cc442` | 窗口开在了非当前显示器上（{},{}），挪到光标所在屏 {},{} |  | `app/src-tauri/src/window_watch.rs:575` |
| `auto.rust.x.9f39847f54` | Runtime 未就绪 |  | `app/src-tauri/src/lib.rs:851` |
| `auto.rust.x.9f44b201ee` | 打开 tar 失败: {e} |  | `app/src-tauri/src/extract.rs:83` |
| `auto.rust.x.9f8084f7cb` | 写不了输出文件：{e} |  | `app/src-tauri/src/tts.rs:257` |
| `auto.rust.x.a0c5fa2d9f` | 青年 |  | `app/src-tauri/src/voices.rs:83` |
| `auto.rust.x.a24d69a01d` | 网络重试… |  | `app/src-tauri/src/provision.rs:563` |
| `auto.rust.x.a36cb645c2` | Runtime 未就绪（缺少 torch） |  | `app/src-tauri/src/lib.rs:509` |
| `auto.rust.x.a49f8d4a05` | 导入配置档案 |  | `app/src-tauri/src/voices.rs:1315` |
| `auto.rust.x.a4abecd0fe` | 等分离进程失败：{e} |  | `app/src-tauri/src/separate.rs:234` |
| `auto.rust.x.a55afe4b5f` | 原始 |  | `app/src-tauri/src/voices.rs:993` |
| `auto.rust.x.a593781b23` | 耳机 (Realtek) |  | `app/src-tauri/src/config.rs:522` |
| `auto.rust.x.a5a2f91ea1` | 无效档案: {e} |  | `app/src-tauri/src/voices.rs:1319` |
| `auto.rust.x.a5ffdc95ee` | 已取消 |  | `app/src-tauri/src/provision.rs:600` +7 |
| `auto.rust.x.a64a986f63` | Runtime 补全完成 |  | `app/src-tauri/src/provision.rs:643` |
| `auto.rust.x.a6af760282` | 更新包缺少有效的 sha256，已拒绝应用 |  | `app/src-tauri/src/update.rs:229` |
| `auto.rust.x.a7018f695e` | 当前音色目录 |  | `app/src-tauri/src/voices.rs:804` |
| `auto.rust.x.a7423a8137` | 下载声卡安装包 {} / {}（{:.1}%） |  | `app/src-tauri/src/lib.rs:123` |
| `auto.rust.x.a76352090e` | {key} 两处默认组合不一致 |  | `app/src-tauri/src/shell_extras.rs:750` |
| `auto.rust.x.a785432b30` | connecting:{} · 请求服务器… |  | `app/src-tauri/src/download.rs:284` |
| `auto.rust.x.a9fa441818` | 备份旧界面失败：{e} |  | `app/src-tauri/src/update.rs:255` |
| `auto.rust.x.ab16acefd8` | 应当被清洗而不是报错 |  | `app/src-tauri/src/store.rs:1124` |
| `auto.rust.x.ab31cc9ebb` | 官方 A/I 卡路径：DirectML Runtime |  | `app/src-tauri/src/provision.rs:248` |
| `auto.rust.x.ab63502dd7` | 还没有选中的音色。先在「首页」选一个，或者关掉「换成我的音色」。 |  | `app/src-tauri/src/tts.rs:270` |
| `auto.rust.x.acaebc442f` | 导入 .index 需要先选中一个可管理音色 |  | `app/src-tauri/src/voices.rs:1464` |
| `auto.rust.x.acc7dfe816` | 下载更新失败：{e} |  | `app/src-tauri/src/update.rs:238` |
| `auto.rust.x.ad667e5e16` | 创建后 |  | `app/src-tauri/src/lib.rs:1368` |
| `auto.rust.x.ae3f0d2168` | 清单里没有 {key} 这条资源 |  | `app/src-tauri/src/extra_assets.rs:404` |
| `auto.rust.x.afcf23635f` | 复制模型失败：{e} |  | `app/src-tauri/src/store.rs:1027` |
| `auto.rust.x.b0684a167c` | 御姐 |  | `app/src-tauri/src/voices.rs:89` |
| `auto.rust.x.b0cf745781` | 分离后 |  | `app/src-tauri/src/separate.rs:247` |
| `auto.rust.x.b238cb38ec` | {desc} · 相似度 {s:.2} |  | `app/src-tauri/src/voices.rs:1117` |
| `auto.rust.x.b2ba9634d9` | 未运行 |  | `app/src-tauri/src/lib.rs:825` |
| `auto.rust.x.b33b9fb751` | 连接中… · 准备下载约 {} |  | `app/src-tauri/src/provision.rs:565` |
| `auto.rust.x.b43921940c` | 不能操作音色库根目录 |  | `app/src-tauri/src/voices.rs:842` |
| `auto.rust.x.b4817b7fdf` | 解压后未找到 Runtime\python.exe。请检查 tar 是否完整或重试。 |  | `app/src-tauri/src/extract.rs:203` |
| `auto.rust.x.b5e27d4505` | 竖带修复：已关闭无装饰投影内缩，客户区铺满全窗 |  | `app/src-tauri/src/window_watch.rs:444` |
| `auto.rust.x.b5f0bfe1d8` | 自建 |  | `app/src-tauri/src/voices.rs:994` |
| `auto.rust.x.b76d1399ec` | [ui] 前端日志过快（10 秒内超过 {PER_WINDOW} 条），本轮后续省略 |  | `app/src-tauri/src/lib.rs:369` |
| `auto.rust.x.b78ead0b6a` | 段数超上限 |  | `app/src-tauri/src/shell_extras.rs:717` |
| `auto.rust.x.b803534208` | 使用本地缓存：{} |  | `app/src-tauri/src/provision.rs:519` |
| `auto.rust.x.b99cbcbcd3` | 系统语音正在朗读… |  | `app/src-tauri/src/tts.rs:242` |
| `auto.rust.x.bacc87084d` | 少女音 |  | `app/src-tauri/src/voices.rs:81` |
| `auto.rust.x.bd45f9d523` | 解析 CNB 运行时清单… |  | `app/src-tauri/src/provision.rs:468` |
| `auto.rust.x.be8da62ea1` | 图片 |  | `app/src-tauri/src/lib.rs:199` |
| `auto.rust.x.bf312fa098` | NVIDIA 50 系 CUDA |  | `app/src-tauri/src/catalog.rs:88` |
| `auto.rust.x.bff4bc6067` | 训练进程异常退出（{}）。详情见 logs/{}/train.log |  | `app/src-tauri/src/train.rs:356` |
| `auto.rust.x.c0b4d5c2f4` | 检测到 AMD/Intel：{}，推荐 amd（DirectML）运行时 |  | `app/src-tauri/src/provision.rs:69` |
| `auto.rust.x.c1285d786b` | 界面资源被拒绝（路径不安全）：{:?} |  | `app/src-tauri/src/ui_assets.rs:196` |
| `auto.rust.x.c1c11dd8f6` | 工具窗口地址不合法：{e} |  | `app/src-tauri/src/tool_window.rs:99` |
| `auto.rust.x.c2b2787278` | 缺少 hubert_base.pt，请先补全引擎资源 |  | `app/src-tauri/src/train.rs:232` |
| `auto.rust.x.c41c6ca117` | 找不到 benchmark_realtime.py |  | `app/src-tauri/src/shell_extras.rs:269` |
| `auto.rust.x.c5be4a3312` | 中文.js |  | `app/src-tauri/src/ui_assets.rs:287` |
| `auto.rust.x.c5fcd5c0a9` | 关闭前 |  | `app/src-tauri/src/shell_extras.rs:681` |
| `auto.rust.x.c688bc7974` | download:{} · {} 连接 · 已连接 |  | `app/src-tauri/src/download.rs:162` |
| `auto.rust.x.c727da1f5b` | 起不来分离进程：{e} |  | `app/src-tauri/src/separate.rs:197` |
| `auto.rust.x.c72e61fc70` | 丙 |  | `app/src-tauri/src/voices.rs:1720` |
| `auto.rust.x.c73d43b29b` | 拿不到训练进程的输出 |  | `app/src-tauri/src/train.rs:319` |
| `auto.rust.x.c8c05e7db7` | Runtime 未就绪，无法跑性能测试 |  | `app/src-tauri/src/shell_extras.rs:266` |
| `auto.rust.x.c9aafa74d7` | 读取压缩包失败：{e} |  | `app/src-tauri/src/extract.rs:226` |
| `auto.rust.x.ca898456b2` | 名称不能为空 |  | `app/src-tauri/src/voices.rs:1598` |
| `auto.rust.x.cb12ce77e7` | 选择输出目录 |  | `app/src-tauri/src/sts.rs:107` +1 |
| `auto.rust.x.cd18dfdaf4` | 不支持的采样率：{} |  | `app/src-tauri/src/train.rs:218` |
| `auto.rust.x.cd80589090` | 界面资源缺失 404 rel={rel:?} uri={:?} 外部目录={:?} |  | `app/src-tauri/src/ui_assets.rs:224` |
| `auto.rust.x.cdad0c927d` | 等转换进程失败：{e} |  | `app/src-tauri/src/sts.rs:277` |
| `auto.rust.x.cf11ccd6a9` | 性能测试失败（退出码 {:?}），详见 User_Data/logs/perf_bench.log |  | `app/src-tauri/src/shell_extras.rs:397` |
| `auto.rust.x.cf270c9163` | {} Runtime 已安装 |  | `app/src-tauri/src/provision.rs:646` |
| `auto.rust.x.d03c6cb553` | 第三方 · {origin} |  | `app/src-tauri/src/store.rs:283` |
| `auto.rust.x.d08e45e275` | 没有下载地址 |  | `app/src-tauri/src/download.rs:215` |
| `auto.rust.x.d21a4981b7` | 等训练进程失败：{e} |  | `app/src-tauri/src/train.rs:347` |
| `auto.rust.x.d4efcb94da` | {k} 默认必须是 true，否则等于悄悄关掉全局快捷键 |  | `app/src-tauri/src/shell_extras.rs:767` |
| `auto.rust.x.d50071676d` | {key} 的默认组合 {default} 形状不合法 |  | `app/src-tauri/src/shell_extras.rs:777` |
| `auto.rust.x.d8b16dedea` | 下载中 {} / {} · {} |  | `app/src-tauri/src/provision.rs:568` |
| `auto.rust.x.da544f6e8b` | 配置键名有重复 |  | `app/src-tauri/src/shell_extras.rs:788` |
| `auto.rust.x.daad8455c2` | 临时清理（{phase}）root={}：删文件 {} 个、目录 {} 个，失败 {}，约 {:.1} MB |  | `app/src-tauri/src/paths.rs:265` |
| `auto.rust.x.dab1a19c29` | 档案格式无效 |  | `app/src-tauri/src/voices.rs:1321` |
| `auto.rust.x.dc66c55a2e` | 特征索引 |  | `app/src-tauri/src/voices.rs:956` |
| `auto.rust.x.dc92f52f68` | Runtime 未就绪，请先补全运行环境 |  | `app/src-tauri/src/train.rs:212` |
| `auto.rust.x.dca24a94ac` | (无名) |  | `app/src-tauri/src/window_watch.rs:121` |
| `auto.rust.x.dd5660b4da` | 起不来推理进程：{e} |  | `app/src-tauri/src/tts.rs:330` |
| `auto.rust.x.e0ce99ef5b` | 正在安装… |  | `app/src-tauri/src/store.rs:982` |
| `auto.rust.x.e0d516d012` | 写入 {} 失败：{e} |  | `app/src-tauri/src/extract.rs:247` |
| `auto.rust.x.e0dab22b1a` | 下载失败 |  | `app/src-tauri/src/download.rs:326` |
| `auto.rust.x.e110cd6caf` | 长度超上限 |  | `app/src-tauri/src/shell_extras.rs:719` |
| `auto.rust.x.e12d8322af` | 未能识别显卡类型：{}，请手动选择 |  | `app/src-tauri/src/provision.rs:76` |
| `auto.rust.x.e178207ec7` | 档案名不合法：{profile_id:?} |  | `app/src-tauri/src/voices.rs:986` |
| `auto.rust.x.e1b39abf92` | Runtime 已就绪，跳过下载 |  | `app/src-tauri/src/provision.rs:452` |
| `auto.rust.x.e1e2bc3a99` | 工具窗口（{kind}）已建好，开始处理圆角 |  | `app/src-tauri/src/tool_window.rs:113` |
| `auto.rust.x.e246e3bafa` | 语音转换后 |  | `app/src-tauri/src/sts.rs:289` |
| `auto.rust.x.e32a4f9295` | 打开压缩包失败：{e} |  | `app/src-tauri/src/extract.rs:225` |
| `auto.rust.x.e38da2e4e6` | 缺分离模型，请先下载 |  | `app/src-tauri/src/separate.rs:148` |
| `auto.rust.x.e43ef3d56a` | 转换完成 |  | `app/src-tauri/src/sts.rs:287` |
| `auto.rust.x.e4476ca669` | 竖带修复：关投影标志失败（{e}） |  | `app/src-tauri/src/window_watch.rs:423` |
| `auto.rust.x.e4fcdc8759` | 下载 {} Runtime v{}（约 {} · {} 连接） |  | `app/src-tauri/src/provision.rs:490` |
| `auto.rust.x.e56c3aa66a` | 只改主显卡不该重写 inuse |  | `app/src-tauri/src/config.rs:654` |
| `auto.rust.x.e5d3918de2` | 解压 Runtime… |  | `app/src-tauri/src/provision.rs:605` |
| `auto.rust.x.e64959c277` | config::defaults() 里没有 {key} |  | `app/src-tauri/src/shell_extras.rs:749` |
| `auto.rust.x.e7a64d4aaf` | NVIDIA 50 系（RTX 50xx） |  | `app/src-tauri/src/provision.rs:313` |
| `auto.rust.x.e84378f99a` | 还没有选中的音色。先在「首页」或「模型」页选一个。 |  | `app/src-tauri/src/sts.rs:178` |
| `auto.rust.x.e9c01e81cb` | 请先选好输入文件或文件夹 |  | `app/src-tauri/src/sts.rs:161` |
| `auto.rust.x.e9ddef6eab` | 建不了输出目录：{e} |  | `app/src-tauri/src/separate.rs:150` +2 |
| `auto.rust.x.ebd26da421` | 启动 |  | `app/src-tauri/src/lib.rs:1231` |
| `auto.rust.x.ec982d9c98` | 建不了目录：{e} |  | `app/src-tauri/src/extra_assets.rs:407` |
| `auto.rust.x.eca157a71e` | 已有补全任务在进行 |  | `app/src-tauri/src/provision.rs:438` |
| `auto.rust.x.ed552016e9` | 清单给的落地路径不安全：{} |  | `app/src-tauri/src/extra_assets.rs:406` |
| `auto.rust.x.ee1fb6f221` | {good} 应该算 N 卡 |  | `app/src-tauri/src/provision.rs:679` |
| `auto.rust.x.ee7e83d91d` | Runtime 就绪，但缺少 tools/realtime_worker.py |  | `app/src-tauri/src/provision.rs:370` |
| `auto.rust.x.eea9655c7b` | 性能测试未完成：{e} |  | `app/src-tauri/src/shell_extras.rs:428` |
| `auto.rust.x.f0098a67e2` | 更新包里没有 index.html，已放弃应用 |  | `app/src-tauri/src/update.rs:248` |
| `auto.rust.x.f204de859a` | 带 \\?\ 前缀的本机路径不该被清空 |  | `app/src-tauri/src/config.rs:563` |
| `auto.rust.x.f2ce2432c3` | 显示器 {}{}：位置 {},{} 尺寸 {}x{} 工作区 {},{} {}x{} 缩放 {:.2} |  | `app/src-tauri/src/window_watch.rs:120` |
| `auto.rust.x.f2e88c071e` | Runtime 就绪 |  | `app/src-tauri/src/provision.rs:372` |
| `auto.rust.x.f423573349` | 安装完成 |  | `app/src-tauri/src/store.rs:713` |
| `auto.rust.x.f456299616` | tar 条目错误: {e} |  | `app/src-tauri/src/extract.rs:165` |
| `auto.rust.x.f5c9f3fce5` | 只有 index 装不了 |  | `app/src-tauri/src/store.rs:1145` |
| `auto.rust.x.f6bccbff47` | 人声分离模型 |  | `app/src-tauri/src/extra_assets.rs:534` |
| `auto.rust.x.f7271a7905` | 换音色跑完了但没有产出文件，详情见 User_Data/logs/tts.log |  | `app/src-tauri/src/tts.rs:350` |
| `auto.rust.x.f7b505e766` | 空目录不该算就绪 |  | `app/src-tauri/src/train.rs:393` |
| `auto.rust.x.f8624e774e` | 缺少 {} 的训练底模，请先下载 |  | `app/src-tauri/src/train.rs:222` |
| `auto.rust.x.f9e62f8c38` | 性能测试跑完了但没有写出报告文件 |  | `app/src-tauri/src/shell_extras.rs:402` |
| `auto.rust.x.fce4b463c1` | 已经有一个训练在跑了 |  | `app/src-tauri/src/train.rs:250` |
| `auto.rust.x.fe9e98a65c` | 完成重命名失败: {e} |  | `app/src-tauri/src/download.rs:312` |
| `auto.rust.x.ffcf0a1eb0` | 文件不存在 |  | `app/src-tauri/src/voices.rs:1436` |
| `auto.rust.x.fffda47f1e` | 当前是默认参数，没有可导出的档案。请先「另存当前为档案」。 |  | `app/src-tauri/src/voices.rs:1373` |
