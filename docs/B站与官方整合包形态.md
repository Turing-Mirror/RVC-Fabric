# B 站热门 RVC 与官方整合包形态调研

> 调研日期：2026-07-18  
> 目的：对齐「用户在视频里看到的 RVC」长什么样，避免做成无关产品。

## 结论（先看这个）

B 站高播放教程（花儿不哭官方、各类「2025 最强变声器」）里，**主流仍是官方系整合包**：

1. 解压 7z  
2. 双击 **`go-web.bat`**  
3. 浏览器弹出 **Gradio WebUI**（训练 + 推理 + UVR）  
4. 可选 **`go-realtime-gui.bat`** 做实时变声  

也就是说：**所谓「exe / 一键包」对外是绿色文件夹，对内还是 Python + WebUI**，并不是独立重写的商业变声器客户端。

部分 2024–2025 视频会包装成「变声器下载」营销页，但仍大量基于 RVC WebUI 或二次分发整合包。

## 官方包关键文件

| 资源 | 说明 |
|------|------|
| HuggingFace `lj1995/VoiceConversionWebUI` | 预训练、ffmpeg、整合包总入口 |
| `RVC1006Nvidia.7z` | N 卡一键包（含 runtime） |
| `RVC1006AMD_Intel.7z` | A/I 卡 DML 包 |
| `RVC-beta.7z` | 早期整合包名称 |
| 根目录 `go-web.bat` | `runtime\python.exe infer-web.py --port 7897` |
| 根目录 `go-realtime-gui.bat` | `runtime\python.exe gui_v1.py` |

## 视频里用户实际操作动线

```
下载整合包 → 解压到英文路径
    → 双击 go-web.bat（黑框 + 浏览器）
        → 推理：选模型 / 上传音频 / 变调 / 转换
        → 分离：UVR 出干声
        → 训练：丢数据集 → 一键训练
    → 或双击实时变声 + 虚拟声卡
    → 模型：网盘下 .pth 放进 weights
```

## 本仓库对齐策略

- **不**另做一套「假变声器 UI」冒充 RVC  
- **做**整合包入口：`一键启动.bat` / 启动器 / 与官方一致的 bat  
- **保留**原版 `infer-web.py` Gradio 界面（用户在 B 站看到的就是它）  
- **文档**写清：要免环境，请挂载官方 `runtime` 或下载完整 7z  

## 参考链接

- 官方仓库：https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI  
- 官方教程视频：https://www.bilibili.com/video/BV1pm4y1z7Gm/  
- HF 资源：https://huggingface.co/lj1995/VoiceConversionWebUI  
