# CNB `index.json` 索引与 `ch-banner` 封面

仓库：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases  
本机暂存：`CNB-GIT-RELEASE/`（产品仓 gitignore，不进源码 Git）

## 目录

```text
CNB-GIT-RELEASE/
  catalog-src/            # ★ 唯一人工维护入口（YAML 源，见下）
  index.json              # 生成物：软件自动读取的主索引（勿手改）
  ch-banner/<id>.jpg      # 角色封面（社区下载缩略图）
  voices/<id>/            # 音色 zip + .sha256（LFS）
  setup/                  # Setup 安装器
  assets/core/            # engine-core zip（LFS）
  vbcable/                # VB-Cable 包（LFS）
  runtime/<variant>/      # Runtime tar + integrity json
  catalog/online_catalog.snippet.json  # 生成物：兼容副清单（勿手改）
```

（Runtime 制品在 CNB **Release 标签 `RVC-runtime`**，不由本索引文档维护上传流程。）

## catalog-src/ — YAML 清单源（人工只改这里）

```text
catalog-src/
  meta.yaml            # 产品名 / note / manifest_urls / runtime_release_tag
  app.yaml             # 软件版本 + gui 增量包（version/sha256/min_app_version）
  community.yaml       # QQ 群 / 完整包链接
  engine-core.yaml     # file / version / channel / 锁定 sha256
  vbcable.yaml
  setup.yaml
  runtimes/<variant>.yaml   # nvidia / amd / nvidia50
  voices/<id>.yaml     # 一色一文件：人话字段 + 制品相对路径
```

规则：

- YAML 里只写**人话字段**（名称 / series / 作者 / 描述 / 日期）与制品相对路径 `file`；
  `sha256` / `size_bytes` / `pack_url` / `cover_url` / `sha256_urls` 由
  `python scripts\build_catalog.py build` **自动补全**（顺带生成 `.sha256` 边车）。
- YAML 里手写的 `sha256`/`size_bytes` 是**已发布锁定值**：与本地制品不一致时
  以锁定值为准并警告（防止本地重打包未发布导致索引指向用户下不到的哈希）；
  发布新制品时把锁定值改成新哈希（或删掉锁定值让脚本从本地补）。
- `index.json` / `snippet` / `configs/online_catalog.json` 三份 JSON 均为生成物，
  **禁止手改**——改了也会在下次 build 被覆盖。

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
| `series` | 可选；系列包名（如 `Mygo` / `VOCALOID` / `RVC原版`），社区下载窗口按此分组展示；留空 = 单品音色 |

`series` 写在 `catalog-src/voices/<id>.yaml` 里即可（客户端也识别 `series_name` / `collection` 别名）。同 `series` 的音色在「社区下载」窗口会显示一个分组小标题（如「系列 · Mygo · 3 个音色」），未分组的单品音色合并在最前。现有归类：官方 4 色 `RVC原版`，Anon/Rana/Soyo/Taki/Tomori 5 色 `MyGO!!!!!`。

## 安装/更新包（`packages`）

按 **发布时间 YYMMDD** 命名 `id`（如 `setup-260722`、`gui-260722`）。

字段：`released`/`date`、`version`、`url`、`sha256`、`kind`/`package_type`。

## 软件如何读

1. 优先：`…/raw/main/index.json`（`configs/online_catalog.json` → `manifest_urls`）  
2. 兼容：`catalog/online_catalog.snippet.json`  
3. 本地缓存 / 内置清单  

实现：

| 模块 | 作用 |
|------|------|
| `launcher/online/catalog.py` | 解析 index；`VoiceEntry` 含 author/date/cover_url/series |
| `launcher/ui/store_page.py` | 社区下载行展示封面缩略图 + 作者 + 系列分组 |
| `scripts/build_catalog.py` | catalog-src YAML → index/snippet/内置清单三份生成物 |

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

## 运维（发布 SOP）

以「新增一个音色」为例：

```bat
:: 1. 制品入库：zip 放 CNB-GIT-RELEASE\voices\<id>\，封面放 ch-banner\<id>.jpg
:: 2. 新建 catalog-src\voices\<id>.yaml（抄一份现有的改：name/tag/series/author/date/file/cover）
:: 3. 编译（自动算 sha256/size/URL，回环校验过客户端解析器）
python scripts\build_catalog.py build --diff
:: 4. 核对 diff 输出后各自提交
```

```powershell
cd CNB-GIT-RELEASE
git add catalog-src/ index.json catalog/ ch-banner/ voices/
git commit -m "voice: <id>"
git push origin main
# 产品仓另提交 configs/online_catalog.json（内置兜底，同一次 build 生成）
```

其它子命令：`check`（只校验，出错非零退出，CI 可用）；`init`（一次性迁移用，勿重复跑）。
封面用 **git/raw**（小图，勿 LFS）。音色 zip 用 LFS。

后续自动化路线：二期 `build_catalog.py add-voice --zip x.zip --cover x.jpg --series Mygo`
一键落 YAML+拷制品；三期 CNB 仓 CI push 时自动 `check`。