# CNB `index.json` 索引与 `ch-banner` 封面

仓库：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases  
本机暂存：`CNB-GIT-RELEASE/`（产品仓 gitignore）

## 目录

```text
CNB-GIT-RELEASE/
  index.json          # 软件自动读取的主索引（优先）
  ch-banner/          # 角色封面图 <id>.jpg
  voices/<id>/        # 音色 zip + .sha256（LFS）
  runtime/<variant>/  # Runtime（Release 或 LFS）
  setup/              # Setup 安装器
  catalog/            # 旧 snippet（可选兼容）
```

## index.json 字段（音色）

| 字段 | 说明 |
|------|------|
| `name` | 音色名称 |
| `author` | 作者 |
| `author_url` | 作者链接 |
| `released` | 发布日 **YYMMDD**（如 `260722`） |
| `cover` | 仓内相对路径 `ch-banner/<id>.jpg` |
| `cover_url` | 完整 raw URL，社区下载列表展示用 |
| `pack_url` / `sha256` | LFS 音色包 |

## packages（安装/更新包）

按 **发布时间 YYMMDD** 命名 id，例如：

- `setup-260722` — Inno Setup  
- `gui-260722` — 壳层增量  
- `runtime-nvidia-260721` — Runtime  

字段：`released`、`version`、`url`、`sha256`、`kind` / `package_type`。

## 软件读取顺序

1. `https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/index.json`  
2. 本地 `configs/online_catalog.json` 的 `manifest_urls`  
3. 缓存 / 内置清单  

实现：`launcher/online/catalog.py`（`VoiceEntry.author` / `released` / `cover_url`）。

## 运维

推送封面与 index（小文件，非 LFS）：

```powershell
cd CNB-GIT-RELEASE
git add index.json ch-banner/
git commit -m "chore: index.json + ch-banner covers"
git push origin main
```

生成/刷新索引也可用产品仓脚本（若已提供）：

```bat
python scripts\write_cnb_index.py
```
