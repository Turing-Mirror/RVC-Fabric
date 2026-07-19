# 会话变更摘要（2026-07-20）

## 主题

全量审查 `launcher/` 在线更新与壳层 → 安全/正确性修复 → 对标 GitHub 方法的优化 → 二次审查。

## 审查高危项与处理

| ID | 问题 | 处理 |
|----|------|------|
| H1 | 音色 zip `extractall` zip-slip | `online/safe_zip.py` + voice 改用安全解压 |
| H2 | GUI 更新无 hash | `download_and_apply_gui` 默认 **require_sha256** |
| H5 | store 忽略 pack_url | 列表 `has_download()`；下载走统一入口 |
| M1 | 进度 lambda 晚绑定 | 默认参数绑定 phase/done/total |
| M3 | GUI 写出路径越界 | `assert_path_under_root` |
| M6 | 重载设备停变声不提示 | 状态文案「变声已停止」 |

## 对标优化

| 来源思路 | 落地 |
|----------|------|
| electron-updater 校验/静默检查 | sha256 必填；启动 2.5s 后静默拉清单，「更新·新」角标 |
| w-okada 延迟权衡 | 设置「延迟预设」：低延迟 / 均衡 / 稳定 |
| 标准 zip 安全 | safe_zip 共用 |

## 文档

- `docs/在线更新与音色库.md`：sha256 必填、安全解压、pack_url 列表  
- `docs/大众版使用说明.md`：预设、更新角标  
- `launcher/ui/help_content.py`：同步要点  

## 二次审查清单

- [x] 无盲 `extractall`  
- [x] store 支持 voice_pack  
- [x] GUI 无 sha256 拒绝应用  
- [x] 无引擎算法大改  
- [x] 单测覆盖 zip-slip / sha 策略 / pack has_download  
- [x] 文档与实现一致  

## 非目标（未做）

CustomTkinter/Electron、main_app 大拆、Runtime 热更。
