# Clownfish Voice Changer 逆向与 RVC Fabric DSP 对比报告

研究性质：只研究、不落代码。分析对象为 `ClownfishVoiceChanger\ClownfshAPO64.dll`（约 380KB，Clownfish 2.05），方法为 PE 静态分析 + Capstone 反汇编（`.text` 与可执行的 `RT_CODE` 段）+ 注册表/安装目录检查。命名管道抓包因权限受阻，包格式由解析函数 `0x2D70` 静态还原。

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
|---|---|---|
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

### 4. 变声效果 id → 内部实现（内部编号，非 UI 编号）

4 路 SoundTouch 对象基址 `state+0x14B58+i*0x60`（循环确认）。

| id | 实现 | 推断对应 UI |
|---|---|---|
| 0 / 1 / 2 / 3 | 空操作（配合其他字节字段使用，如 Robot 走 byte14 声码器） | — |
| 4 | Hann 窗调制：`out = in × window[pos]`，窗长 `+0x7c`，四路各自相位 | Clone/加倍类 |
| 5 | SoundTouch `setPitchSemiTones(-3)` | **Male = -3 半音** |
| 6 | `setPitchSemiTones(+4)` | **Female = +4 半音** |
| 7 | `setPitchSemiTones(+8)` | **Helium = +8** |
| 8 | `setPitchSemiTones(+12)` | **Baby = +12** |
| 9 | 乒乓双缓冲反向播放：录满一条 5s 延迟线→倒序回放，同时录另一条，边缘做淡入淡出 | Clone/反向类（四路错峰相位） |
| 0x0A | 三角 LFO 扫音高：**-4 ↔ +13 半音**，步进 **0.1 半音/块** | Mutation |
| 0x0B | 同上，步进 **0.01** | Slow Mutation |
| 0x0C | 同上，步进 **0.3** | Fast Mutation |
| 0x0D | LFO 累加器到 -3/+4 边界时把音高在 **+6 ↔ -3 半音**间翻转（方波调制） | Alien |
| 0x0E | `setPitchSemiTones(float)`，参数=字节1–4 的 float 位型 | **Custom pitch（±15，菜单默认 4.50）** |
| 0x0F | 125ms 单抽头回声：`out = 0.5·in + 0.5·in[t-125ms]` | —（可能映射到某 UI 档） |
| 0x10 | **半波整流** `max(0, x)` | **Atari** |
| 0x11 | `memset(out,0)` | Silence |
| 0x14 | Chainer：四槽 id 各跑一次，串接 | Custom effects |

Robot（UI 14）不在效果循环里：由 byte14 打开声码器支路。**Old Radio**（UI 12）在分派里也没有独立分支，最可能由 EXE 端用 byte16/17 高低音同时砍 + 空间效果组合实现（待动态确认）。

### 5. 关键算法细节

- **SoundTouch 内嵌**（非外挂 DLL），4 个实例；参数 `QUICKSEEK=0, AA_FILTER=1, SEQUENCE=40ms, SEEKWINDOW=15ms, OVERLAP=8ms`——speech 档，保质量。`setPitchSemiTones = 2^(st/12)`（常数 ln2/12 = 0.057762265 已验证）。
- **声码器（fn `0x79D0`）**：真·FFT 通道声码器。约 256 点 FFT，**.rdata 里的 21 频带边界表**（bin 划分 0-1,2-3,4-5,6-7,8-10,12-14,16-20,24-28,34-40,48-60,78-100…，近对数分布）；每频带做峰值保持包络（衰减系数 **0.6**/块），频带增益线性插值成逐样本增益后乘到载波上。处理时帧数减半 → 半速率声码器。
- **EffectBassTreble（fn `0x1100`）**：双精度、两段二阶 IIR 架式滤波（低架+高架），系数在采样率/增益变化时经 `0x1830` 重算。±63.5dB 量程。
- **Clone 类（id 9）**：两条 5 秒延迟线乒乓，倒序回放 + 块边缘线性淡化防咔哒；四路用不同读相位。
- **Atari（id 0x10）**：不是位深压缩——是 `max(0,x)` 半波整流，丢掉所有负半周，出来是八度感十足的 fuzz。
- **噪声门**：只按声道 0 逐帧取峰值；低于阈值连续 10 个 APO 块（≈100ms）就整块清零；高于阈值立刻放行并清计数。没有平滑释放——硬切。
- **延迟/缓冲**：延迟线尺寸 = `rate×channels`（空间效果缓冲为 rate×ch/4），Clone 乒乓缓冲各 5s。

## 二、RVC Fabric 现状（对照点）

- `tools/dsp_soundtouch.py`：官方 SoundTouch DLL，**5 项 speech 参数与 APO 完全一致**——变调核选对了。
- `tools/dsp_voice.py`：固定串行链 `pitch→formant→whisper→robot→ring→tremolo→vibrato→chorus→bitcrush→drive→radio→echo→reverb`，每个效果 `mix/depth=0` 即旁路；另有独立共振峰搬移（Clownfish 没有）。
- `tools/dsp_fx.py`：门限→压缩→5 段 EQ→输出增益→tanh 软限幅。
- `tools/dsp_worker.py`：立体声取均值成单声道→voice_chain→fx_chain→`y-y³·0.15` 软削波→±0.97 限幅→复制到 N 声道。

## 三、逐项差距（为什么复刻不像）

| Clownfish | RVC Fabric | 差距 |
|---|---|---|
| Male **-3** / Female **+4** / Helium +8 / Baby +12 半音（整数档，走 setPitchSemiTones） | ∓**4.5**、+8、+12 | 男女声差 **0.5~1.5 半音**；且自定义档 Clownfish 是 float 精确到分，RVC 预设写死 4.5 |
| Mutation = 音高**三角扫 -4~+13 半音**（步进 0.1/0.01/0.3 每块 ≈ 每 10ms） | fast_mutation = +5 固定 + vibrato 9.5Hz/**17 音分** + formant +2.5 + drive | **机制完全不同**：Clownfish 是 ±17 半音的大范围扫频，RVC 只抖 0.17 半音；且 Clownfish 不碰共振峰，RVC 反而搬了 formant |
| Alien = 音高在 **+6/-3 半音间方波跳变** | alien = +3 固定 + tremolo + ring + vibrato | 完全不同的调制源（音高跳变 vs 振幅颤音） |
| Robot = **21 频带 FFT 声码器**（包络衰减 0.6），半速率 | robot = 包络×脉冲载波 + ring + 限带 | 一个是真声码器（载波+带包络），一个是单包络调制；Clownfish 另有 vocoders/*.mp3 载波生态 |
| Atari = `max(0,x)` **半波整流** | retro8bit = 6bit 量化 + 5×采样保持 + 限带 | 机制完全不同：整流 fuzz ≠ 位深压缩 |
| Clone = 5s 乒乓延迟线**倒序回放** + 边缘淡化（或 Hann 窗粒子 id4） | chorus_crowd = 2 路失谐延迟 | Clownfish 的 Clone 实际是"倒放/窗口粒子"结构，不是合唱 |
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
2. **机制级缺失**：Mutation（±17 半音扫频）、Alien（音高方波跳变）、Atari（半波整流）、Ghost（反向回声）、21 带声码器——RVC 的效果器库里没有这些原语，拿 vibrato/混响/位深压缩去凑，形似神不似。
3. **空间效果延迟常数不同**：Clownfish 的 Chorus 是 8.3ms 梳状、Cave/TownHall 是固定 62.5/250ms 回声；RVC 是可调 LFO 合唱 + Schroeder 混响。
4. **处理顺序差异**：Clownfish 是「门限 → 单效果（或 4 槽串联）→ 空间 → EQ → 干湿 → 增益」；RVC 是 13 级全串联固定顺序。Clownfish 的效果是**单选**（id 互斥），RVC 预设是多效果叠加——同一个预设名背后的信号路径不一样。
5. **声码器是 FFT 频带式**而非包络×载波；且自带载波库（vocoders/*.mp3）。
6. **整个外围生态**：APO 挂在系统层（对所有应用生效、10ms 硬实时），音乐注入、监听回传、Chainer 串联——这些是链路位置问题，不在 DSP 算法层面。

## 五、置信度说明

- **高置信（反汇编直接确认）**：信号链顺序、包格式全部字段、SoundTouch 参数、各 id 内部实现、声码器带数与衰减、EQ 结构、延迟常数。
- **中置信**：wire id ↔ UI 名的映射（由语义推断：-3/+4/+8/+12 对应 Male/Female/Helium/Baby 单调递增可信；id9 倒放↔Clone、0x0D 跳变↔Alien 为推断）。Old Radio 未见独立分支，疑为 EQ+空间组合——需动态验证。
- **未解决**：命名管道实时抓包失败（权限），无法拿到各 UI 预设实际下发的整包字节来最终钉死映射表；byte14 声码器的载波来源（内置生成 vs EXE 推流）；id 1/2/3 空槽与 0x0F 的 UI 归属。

## 六、若将来要落地（不在本次范围）

优先级排序：① 修预设数值（-3/+4）；② 加三个原语：半波整流（Atari）、音高 LFO 扫频（Mutation 三档，挂 SoundTouch setPitchSemiTones 每块更新）、音高方波（Alien）；③ 反向回声（Ghost）与 8.3ms 梳状（Chorus）；④ 真声码器；⑤ Chainer 串联语义（Clownfish 是单选+可选4槽串，RVC 全串行可模拟但需注意互斥）。
