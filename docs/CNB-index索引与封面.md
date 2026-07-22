# CNB `index.json` 索引与 `ch-banner` 封面

仓库：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases  
本机暂存：`CNB-GIT-RELEASE/`（产品仓 gitignore，不进源码 Git）

## 目录

```text
CNB-GIT-RELEASE/
  index.json              # 软件自动读取的主索引
  ch-banner/<id>.jpg      # 角色封面（社区下载缩略图）
  voices/<id>/            # 音色 zip + .sha256（LFS）
  runtime/<variant>/      # Runtime tar（Release 或 LFS）
  setup/                  # Setup 安装器
  catalog/online_catalog.snippet.json  # 兼容副清单
```

## 音色条目（`voices[]`）

| 字段 | 说明 |
|------|------|
| `name` | 音色名称 |
| `author` | 作者 |
| `author_url` | 作者链接 |
| `date` / `released` | **YYMMDD**（如 `260722`） |
| `cover` | 仓内路径 `ch-banner/<id>.jpg` |
| `cover_url` | raw 完整 URL，社区下载列表展示 |
| `pack_url` / `sha256` | LFS 音色包 |

## 安装/更新包（`packages`）

按 **发布时间 YYMMDD** 命名 `id`：

| 键 | 示例 id | 内容 |
|----|---------|------|
| `setup` | `setup-260722` | Inno Setup |
| `gui_patch` | `gui-260722` | 壳层增量 zip |
| `runtime` | `runtime-nvidia-260721` | 分显卡 Runtime |

字段：`released`/`date`、`version`、`url`、`sha256`、`kind`/`package_type`。

## 软件如何读

1. 优先：`…/raw/main/index.json`（`configs/online_catalog.json` → `manifest_urls`）  
2. 兼容：`catalog/online_catalog.snippet.json`  
3. 本地缓存 / 内置清单  

实现：

| 模块 | 作用 |
|------|------|
| `launcher/online/catalog.py` | 解析 index；`VoiceEntry` 含 author/date/cover_url |
| `launcher/ui/store_page.py` | 社区下载行展示封面缩略图 + 作者 |
| `scripts/write_cnb_index.py` | 从产品清单生成 index + 拷贝 ch-banner |

## 本地软件 ch-banner

```text
User_Data/ch-banner/<id>.jpg   # 主位置
ch-banner/                     # 安装根可选共享
User_Data/models/<id>/cover.*  # 兼容

config.json:
  "cover": "ch-banner/kiki.jpg"
```

解析：`launcher/catalog.py` → `resolve_cover_path` / `install_cover_to_ch_banner`。  
导入与社区安装会把封面写入 `User_Data/ch-banner/` 并写回 config。

## 运维

```bat
python scripts\write_cnb_index.py
```

```powershell
cd CNB-GIT-RELEASE
git add index.json ch-banner/ catalog/
git commit -m "chore: index.json + ch-banner"
git push origin main
```

封面用 **git/raw**（小图，勿 LFS）。音色 zip / Runtime 大文件用 LFS 或 Release。