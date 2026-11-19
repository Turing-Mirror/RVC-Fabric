# 依赖清单目录

| 文件 | 用途 |
|------|------|
| requirements.txt | NVIDIA 默认 |
| requirements-dml.txt | DirectML |
| requirements-amd.txt | ROCm |
| requirements-ipex.txt | Intel IPEX |
| requirements-py311.txt | Python 3.11 |
| requirements-win-for-realtime_vc_gui*.txt | 实时 GUI Windows |

安装示例：`pip install -r requirements/requirements.txt`

`legacy/` 保存旧版上游 WebUI 的 Poetry 配置。当前 RVC Fabric 使用上表的依赖清单。
