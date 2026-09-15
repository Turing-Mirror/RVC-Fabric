# Clownfish Voice Changer 逆向与 RVC Fabric DSP 对比报告

研究性质：只研究、不落代码。分析对象为 `ClownfshAPO64.dll`（约 380KB，Clownfish 2.05）与 `ClownfishVoiceChanger.exe`（约 1MB），方法为 PE 静态分析 + Capstone 反汇编（APO 的 `RT_CODE` 段 + EXE 的管道写线程与 UI→id 查找表）+ 注册表/安装目录检查。命名管道抓包因权限受阻，包格式由 APO 解析函数 `0x2D70` 与 EXE 组包线程（0x19E40–0x1A110，包长 0x16=22 字节）双侧静态还原并互相印证。

## 一、Clownfish 的真实架构

### 1. 挂载方式

Windows **APO（Audio Processing Object）**：`ClownfshAPO64.dll` 注册为系统音频效果对象，挂在捕获/渲染端点上，由 Windows 音频引擎在每个 10ms 周期回调 `APOProcess`。主程序 `ClownfishVoiceChanger.exe` 只做 UI 和配置下发，**不做**实时音频处理——全部 DSP 都在 APO DLL 里，跑在系统音频线程上。

进程间用两条命名管道：

- `\\.\pipe\myclownfishforskypepipe_in`：APO → EXE（回传处理后的音频给主程序做电平表/监听）
- `\\.\pipe\myclownfishforskypepipe_out`：EXE → APO（下发配置包 + 音频流）

`_out` 管道的读线程（`0x3270`）按消息类型分派：`0x64 'd'` = int16 音频进缓冲 A（音乐注入），`0x66 'f'` = float32 音频进缓冲 B（EXE 端流回的成品音频，直接盖输出），其余进 20 字节定长配置解析器 `0x2D70`。

### 2. APOProcess 完整信号链（`RT_CODE` 段 `0x2D000`，顺序已确认）

```
旁路检查（byte15 总开关，0=直通拷贝）
  → 声码器模式（byte14：Robot/Vocoder，通道对象 fn 0x79D0）
  → 干声快照（byte13 overlap 时先存一份原声）
  → 音乐前置注入（byte8=1 时把 'd' 音乐流 ×(byte5/100) 混进输入）
  → 噪声门（峰值 < byte7/1000 连续 10 块 → 整块清零，只看声道0）
  → 4 路并行的变声效果循环（bpl=0..3，跑在 4 个 SoundTouch 实例上）：
      主效果 id（byte0）≠0x14 时四路同参数（冗余，最后一个写赢）；
      =0x14（Chainer）时四路分别取链槽 byte9..12 的效果 id，
      且每路输出拷回输入 → 4 个效果**串联**
  → 空间效果级（byte6，buf=rate×ch/4 采样环形延迟线）：
      1=Cave（62.5ms 回声，反馈 0.5）
      2=TownHall（250ms 回声，反馈 0.25）
      3=Chorus（400 帧 ≈8.3ms 梳状，(in+delayed)×0.5）
      4=Ghost（双指针反向读延迟线 = 反向回声）
  → 电平回传（byte18 时把处理后音频以 'd' 消息推给 EXE）
  → 音乐后置叠加（byte8=0 时 'd' 音乐 ×(byte5/100) 加进输出，带 ±1 硬限幅）
  → 'f' float 流覆盖输出（若 EXE 侧在流成品音频则直接盖掉）
  → 高低音 EQ（byte16/17 ×0.5 dB ≠0 时跑 EffectBassTreble，双精度双二阶×2）
  → 干声叠加（byte13：输出 += 原声×0.5）
  → 输出增益（byte19 → 1.0+0.05×百分比 = 1.0~6.0 倍，±1 硬限幅）
```

### 3. 配置包格式（20 字节，parser `0x2D70`）

| 偏移 | 还原 | 含义 |
| --- | --- | --- |
| 0 | uint8 | 变声效果 id（内部编号，见下） |
| 1–4 | int32 | 仅 id=0x0E/0x14；0x0E 时是 **float 位型**的自定义半音数 |
| 5 | /100 | 音乐注入增益 0..1（默认 0.5） |
| 6 | int | 空间效果 id（0 关 / 1 Cave / 2 TownHall / 3 Chorus / 4 Ghost） |
| 7 | /1000 | 噪声门阈值 0..0.255 |
| 8 | bool | 音乐走效果链（1=前置注入，0=后置叠加） |
| 9–12 | 4×uint8 | Chainer 四槽的效果 id |
| 13 | bool | 干声叠加回原声×0.5 |
| 14 | bool | 声码器模式（切变时清内部计数器） |
| 15 | bool | 总开关（0=直通） |
| 16 | int8×0.5 | 低音 dB（-63.5..+63.5） |
| 17 | int8×0.5 | 高音 dB |
| 18 | bool | 把处理结果回传 EXE（电平表/监听） |
| 19 | %→1.0+0.05x | 输出增益 1.0~6.0 |

### 4. 变声效果 id → 内部实现（**映射表已从 EXE 静态确认**）

`ClownfishVoiceChanger.exe` `.rdata 0xD2258` 处有两张 **UI 索引 → wire id** 查找表（4 字节步长的 int32 表）：

- **表1（链槽用，`[Off] + 字符串表顺序 14 项`）**：`0,9,13,12,10,11,8,6,7,5,14,16,4,15,17`
- **表2（主效果选择器 15 项）**：`9,13,15,10,12,11,5,6,7,8,16,4,14,17,20`（Alien, Atari, Clone, Mutation, FastMut, SlowMut, Male, Female, Helium, Baby, OldRadio, Robot, Custom, Silence, Chainer）

两张表给出的 wire id ↔ 效果归属完全一致（Robot→4、Clone→15、OldRadio→16、Silence→17、Chainer→20），可信度等同于直接证据。

| UI 效果 | wire id | 内部实现（APO 反汇编确认） |
| --- | --- | --- |
| Off | 0 | 空操作 |
| **Male pitch** | 5 | SoundTouch `setPitchSemiTones(-3)` |
| **Female pitch** | 6 | `setPitchSemiTones(+4)` |
| **Helium pitch** | 7 | `setPitchSemiTones(+8)` |
| **Baby pitch** | 8 | `setPitchSemiTones(+12)` |
| **Alien** | 9 | **乒乓双缓冲分块倒放**：录进 bufA（边缘线性淡化），从 bufB **反向**读回放；读完交换两缓冲。块长 = 声道数×每块帧数×20 ≈ 几百毫秒级 |
| **Mutation** | 0x0A | 三角 LFO 扫音高 **-4 ↔ +13 半音**，步进 **0.1 半音/块** |
| **Slow Mutation** | 0x0B | 同上，步进 **0.01** |
| **Fast Mutation** | 0x0C | 同上，步进 **0.3** |
| **Atari** | 0x0D | **音高方波跳变**：LFO 累加器到 -3/+4 边界时音高在 **+6 ↔ -3 半音**间翻转（≈70ms 一切换） |
| **Custom pitch** | 0x0E | `setPitchSemiTones(float)`，参数=字节1–4 float 位型（±15） |
| **Clone** | 0x0F | **125ms 单抽头 slapback 回声**：`out = 0.5·in + 0.5·in[t-125ms]` |
| **Old Radio** | 0x10 | **半波整流** `max(0, x)` |
| **Silence** | 0x11 | `memset(out,0)` |
| **Robot** | 4 | **周期 Hann 窗门控**（AM 斩波）：窗长 = `rate/25` = 40ms → **25Hz** 断续调制 |
| **Chainer** | 0x14 | 四槽各取 byte9–12 的 id 串联执行 |
| 1 / 2 / 3 | — | 空槽（保留，未映射 UI） |

注意两处**此前推断被推翻**：Alien 不是音高跳变而是**分块倒放**；Atari 不是半波整流而是**音高方波**（半波整流实际是 Old Radio）；Clone 不是倒放而是 125ms slapback。另：**Robot ≠ 声码器**——Robot 是 25Hz Hann 门控 AM，声码器是 byte14 打开的独立支路（载波频谱由 EXE 流式推入，见下）。

### 5. 关键算法细节

- **SoundTouch 内嵌**（非外挂 DLL），4 个实例；参数 `QUICKSEEK=0, AA_FILTER=1, SEQUENCE=40ms, SEEKWINDOW=15ms, OVERLAP=8ms`——speech 档，保质量。`setPitchSemiTones = 2^(st/12)`（常数 ln2/12 = 0.057762265 已验证）。
- **声码器（fn `0x79D0`，byte14 支路，独立于 Robot）**：通道式声码器。**载波频谱由 EXE 端预先分析后经管道流式推入**：APO 从 `[+0x14DF8]` 环形缓冲读 20 频带×双声道的幅度帧（帧步长 0x50 字节），写进 `[+0xF4]`/`[+0x874]` 后调 `0x79D0` 把载波频带包络乘到输入频谱上。包络衰减系数 **0.6**/块。EXE 侧负责解码 `vocoders/*.mp3` → 频带分析 → 推流。
- **EffectBassTreble（fn `0x1100`）**：双精度、两段二阶 IIR 架式滤波（低架+高架），系数在采样率/增益变化时经 `0x1830` 重算。±63.5dB 量程。
- **Alien（id 9）**：两条延迟线乒乓，一条录音另一条**倒序回放**，块边缘线性淡化防咔哒——分块时间反转是 Alien 声的真正来源。
- **Old Radio（id 0x10）**：不是滤波器——是 `max(0,x)` 半波整流，丢掉所有负半周，出来是老收音机式的破音 fuzz。
- **Robot（id 4）**：重复 Hann 窗对输入做 25Hz 门控 AM（窗长 rate/25=40ms），是"斩波"而非声码器。
- **Clone（id 0x0F）**：125ms 单抽头 slapback，`out=0.5·in+0.5·in[t-125ms]`——人声加倍，不是合唱。
- **Atari（id 0x0D）**：音高在 +6/-3 半音间方波跳变（边界触发），8-bit 游戏式音高颤动。
- **噪声门**：只按声道 0 逐帧取峰值；低于阈值连续 10 个 APO 块（≈100ms）就整块清零；高于阈值立刻放行并清计数。没有平滑释放——硬切。
- **延迟/缓冲**：延迟线尺寸 = `rate×channels`（空间效果缓冲为 rate×ch/4），Clone 乒乓缓冲各 5s。

## 二、RVC Fabric 现状（对照点）

- `tools/dsp_soundtouch.py`：官方 SoundTouch DLL，**5 项 speech 参数与 APO 完全一致**——变调核选对了。
- `tools/dsp_voice.py`：固定串行链 `pitch→formant→whisper→robot→ring→tremolo→vibrato→chorus→bitcrush→drive→radio→echo→reverb`，每个效果 `mix/depth=0` 即旁路；另有独立共振峰搬移（Clownfish 没有）。
- `tools/dsp_fx.py`：门限→压缩→5 段 EQ→输出增益→tanh 软限幅。
- `tools/dsp_worker.py`：立体声取均值成单声道→voice_chain→fx_chain→`y-y³·0.15` 软削波→±0.97 限幅→复制到 N 声道。

## 三、逐项差距（为什么复刻不像）

| Clownfish | RVC Fabric | 差距 |
| --- | --- | --- |
| Male **-3** / Female **+4** / Helium +8 / Baby +12 半音（整数档，走 setPitchSemiTones） | ∓**4.5**、+8、+12 | 男女声差 **0.5~1.5 半音**；且自定义档 Clownfish 是 float 精确到分，RVC 预设写死 4.5 |
| Mutation = 音高**三角扫 -4~+13 半音**（步进 0.1/0.01/0.3 每块 ≈ 每 10ms） | fast_mutation = +5 固定 + vibrato 9.5Hz/**17 音分** + formant +2.5 + drive | **机制完全不同**：Clownfish 是 ±17 半音的大范围扫频，RVC 只抖 0.17 半音；且 Clownfish 不碰共振峰，RVC 反而搬了 formant |
| Alien = **乒乓缓冲分块倒放**（~200ms 级反转块，边缘淡化） | alien = +3 固定 + tremolo + ring + vibrato | 完全不同的机制：时间反转 babble vs 振幅/环形调制 |
| Robot = **25Hz Hann 窗门控 AM**（40ms 周期斩波） | robot = 包络×脉冲载波 + ring + 限带 | 都是"调制"但载波结构完全不同；且 Clownfish 另有独立的真声码器（byte14，20 频带，载波频谱经管道流式推入，对应 vocoders/*.mp3） |
| Atari = 音高在 **+6/-3 半音间方波跳变**（~70ms 周期） | retro8bit = 6bit 量化 + 5×采样保持 + 限带 | 一个是音高方波调制，一个是位深/采样率降级 |
| Old Radio = `max(0,x)` **半波整流** | radio = 400–2600Hz 限带 + 噪声 + tremolo + drive | Clownfish 用整流失真模拟破喇叭，RVC 用限带+噪声模拟电台——两种"老"的音色路径 |
| Clone = **125ms slapback** `out=0.5·in+0.5·d` | chorus_crowd = 2 路失谐延迟 | Clone 是固定单回声加倍，不是合唱 |
| Chorus（空间档3）= **8.3ms 梳状**，(in+d)×0.5 | chorus = 40ms 内 LFO 摆动的 2-3 路延迟 | 延迟量级差 5 倍，听感一个是金属梳状一个是真合唱 |
| Cave/TownHall/Ghost = 62.5ms/250ms 回声 + **反向读延迟线** | cave=混响+回声，ghost=气声+降调+混响 | Ghost 是"反向回声"这个特殊结构，RVC 用混响凑，不对 |
| 高低音 = 专用**架式双二阶**（±63.5dB） | 5 段峰式 EQ | 架式 vs 峰式，截止特性不同；Old Radio 疑似靠它砍两头实现 |
| 噪声门：峰值<阈值连续10块→**整块清零**（硬门） | NoiseGate：包络+hold+range_db 渐变 | RVC 更平滑，不是缺陷，但行为不同 |
| 干声叠加：wet + dry×0.5 后置 | 无对应（各效果内部 mix） | 全局干湿比在 Clownfish 是独立开关 |
| 输出增益 1~6 倍 + ±1 硬限幅 | out_gain_db + tanh 软限幅 | 硬限幅 vs 软限幅，极端增益下音色不同 |
| 音乐注入前/后两路 + 'f' 流盖输出 + 电平回传管道 | 无（音乐路径不经过 DSP worker） | 整个"音乐+监听"子系统 RVC 没有对应物 |
| 变调在 APO 内**原生跑全速率多声道**，四路 ST 并行 | 单声道化→单 ST→复制回 N 声道 | 架构不同；STFT 效果（formant/whisper）延迟 ~8ms 与 ST 串接会再叠加固有延迟 |

## 四、无法完美复刻的根因清单

1. **预设数值不对**：Male/Female 差了 0.5~1.5 半音（Clownfish 是 -3/+4，不是 ±4.5）。
2. **机制级缺失**：Mutation（±17 半音扫频）、Atari（音高 +6/-3 方波跳变）、Alien（分块倒放）、Old Radio（半波整流）、Robot（25Hz Hann 门控）、Clone（125ms slapback）、Ghost（反向回声）、20 带管道载波声码器——RVC 的效果器库里没有这些原语，拿 vibrato/混响/位深压缩去凑，形似神不似。
3. **空间效果延迟常数不同**：Clownfish 的 Chorus 是 8.3ms 梳状、Cave/TownHall 是固定 62.5/250ms 回声；RVC 是可调 LFO 合唱 + Schroeder 混响。
4. **处理顺序差异**：Clownfish 是「门限 → 单效果（或 4 槽串联）→ 空间 → EQ → 干湿 → 增益」；RVC 是 13 级全串联固定顺序。Clownfish 的效果是**单选**（id 互斥），RVC 预设是多效果叠加——同一个预设名背后的信号路径不一样。
5. **声码器是 FFT 频带式**而非包络×载波；且自带载波库（vocoders/*.mp3）。
6. **整个外围生态**：APO 挂在系统层（对所有应用生效、10ms 硬实时），音乐注入、监听回传、Chainer 串联——这些是链路位置问题，不在 DSP 算法层面。

## 五、置信度说明

- **已钉死（EXE 查找表 + APO 分派双重证据）**：wire id ↔ UI 效果映射（`ClownfishVoiceChanger.exe` `.rdata 0xD2258` 两张表互证）；音高四档 -3/+4/+8/+12；Alien=分块倒放、Atari=音高方波、OldRadio=半波整流、Clone=125ms slapback、Robot=25Hz Hann 门控、Silence=memset、Chainer=0x14 串联。
- **高置信（反汇编直接确认）**：信号链顺序、包格式字段、SoundTouch 参数、声码器载波为 EXE 流式推入的 20 频带幅度帧、EQ 结构、延迟常数。EXE 端包长 0x16（22 字节，比 APO 解析的 20 字节多 2 字节头/尾）。
- **残余未解决**：Alien 倒放块的精确时长（公式 = 声道数×每块帧数×20，依块长而定）；噪声门/音乐等字段的出厂默认值（ini 未在本机生成时无法读）；id 1/2/3 空槽疑似保留位。动态抓包仍受权限限制，但静态表已使映射不再依赖抓包验证。

## 六、若将来要落地（不在本次范围）

优先级排序：① 修预设数值（-3/+4）；② 加原语：音高三角扫频（Mutation 三档，每块调 setPitchSemiTones）、音高方波 +6/-3（Atari）、分块倒放（Alien，乒乓缓冲）、25Hz Hann 门控（Robot）、半波整流（Old Radio）、125ms slapback（Clone）；③ 反向回声（Ghost）与 8.3ms 梳状（Chorus）；④ 真声码器（20 频带，载波分析在宿主侧）；⑤ Chainer 串联语义（Clownfish 是单选+可选4槽串，RVC 全串行可模拟但需注意互斥）。
