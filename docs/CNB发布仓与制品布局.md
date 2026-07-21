# CNB 发布仓与制品布局（前置）

> 产品源码仓 ≠ 大文件发布仓。  
> 大文件走 **腾讯 CNB + Git LFS**：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases  

本地暂存目录：`CNB-GIT-RELEASE/`（已在产品仓 **`.gitignore`**，勿提交进源码 GitHub）。

---

## 1. 已定用户动线

```text
下载 Setup 安装（装软件 + 启动器，写注册表/卸载项）
  → 启动器自动下载补全所需文件与环境（Runtime 分版等）
  → 进入软件
  → 新手指引
  → 模型社区下载 pth / index
  → 开始变声
  → 调整参数
  → 免费优化 → 付费优化
  → 收集完资料 → 进群
```

制品分发：**CNB Git LFS**（配额按当前规划足够）。托管不依赖自建 CDN；catalog 与音色也在 CNB。

---

## 2. 双仓分工

| 仓库 | URL / 路径 | 内容 |
|------|------------|------|
| 产品源码 | GitHub `Turing-Mirror/RVC-Fabric` 等 | `launcher/`、`infer/`、脚本、文档 |
| **制品发布** | `https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases` | Runtime 7z、音色 zip、将来 setup.exe、catalog 片段 |
| 本机暂存 | 产品仓内 `CNB-GIT-RELEASE/` | 打包输出；`git push` 到 CNB 前的工作区 |

---

## 3. `CNB-GIT-RELEASE` 目录约定

```text
CNB-GIT-RELEASE/
  README.md
  SYNC_COMMANDS.txt      # 推送 CNB / LFS 命令
  .gitattributes         # LFS track 规则
  manifest.json          # 本仓制品索引（脚本生成）
  catalog/
    online_catalog.snippet.json   # 可合并进产品 online_catalog
  runtime/
    nvidia/   runtime-nvidia-<ver>.tar  (+ .sha256)
    amd/      runtime-amd-<ver>.tar
    nvidia50/ runtime-nvidia50-<ver>.tar
  voices/
    <id>/     <id>-v<ver>.zip  (+ .sha256)
  assets/core/           # 预留 hubert/rmvpe 等
  setup/                 # 预留 setup.exe
```

- **Runtime**：整包绿色环境，按 `nvidia` / `amd` / `nvidia50` 分目录。  
  - 默认 **`tar`**（Windows 自带 tar，长路径更稳；本机部分 7-Zip-Zstandard 对大目录会 System ERROR）。  
  - 解压：`tar xf runtime-nvidia-….tar` → 得到 `Runtime/`。  
  - 可选 `--format 7z`；可选 `--volume-mib 1536` 按字节切分卷（`.tar.001` …）。  
- **音色**：独立 `voices/<id>/`，格式与产品 `voice_pack` 一致（`tm_package.json` + `config.json` + `.pth` + 可选 index/cover）。

---

## 4. 从产品仓打包

在**产品仓库根目录**（需本机有参考 Runtime，如 `RVCMAX/.../Runtime` 或已 `sync_from_rvcmax`）：

```bat
python scripts/pack_cnb_release.py --init-layout
python scripts/pack_cnb_release.py --runtime all --voices --write-manifest
```

常用参数：

| 参数 | 含义 |
|------|------|
| `--runtime nvidia\|amd\|nvidia50\|all` | 打绿色 Runtime 7z |
| `--voices` | 打包 `User_Data/models` 与 RVCMAX 参考包内模型 |
| `--version 2026.07.21` | 版本号（默认当天日期） |
| `--format tar\|7z` | 默认 `tar`（推荐） |
| `--volume-mib 1536` | 分卷（MiB）；`0` 为单文件 |
| `--mx 3` | 仅 7z 压缩等级 |
| `--out PATH` | 默认 `CNB-GIT-RELEASE` |

依赖：系统 `tar`（Windows 10+ 自带）。可选 `7z.exe`（`--format 7z`）。

磁盘：三套 Runtime 原始约 **13GB+**，请保证 `CNB-GIT-RELEASE` 所在盘有足够空间。

---

## 5. 推到 CNB（Git LFS）

在 `CNB-GIT-RELEASE` 目录执行（详见该目录 `SYNC_COMMANDS.txt`）：

```bat
git init
git lfs install
git lfs track "*.7z"
git lfs track "*.7z.*"
git lfs track "*.zip"
git add .gitattributes
git add .
git commit -m "chore: initial runtime and voice artifacts"
git remote add origin https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases.git
git branch -M main
git push -u origin main
```

裸库整仓迁移示例（CNB 文档风格）亦写在 `SYNC_COMMANDS.txt`。

推送后：按 CNB 实际 **raw/release 直链** 校正 `catalog/online_catalog.snippet.json` 中的 `urls` / `pack_url`，再接到产品 `configs/online_catalog.json` 或远程 catalog。

---

## 6. 与后续开发的衔接（尚未实现的代码）

| 阶段 | 状态 |
|------|------|
| 制品目录 + 打包脚本 + gitignore | **本前置** |
| Setup.exe（注册表/卸载） | 后续 |
| 启动器按 catalog 拉 Runtime 分版并解压 | 后续 |
| 模型社区 UI 拉 CNB 音色 | 已有 online 骨架，改 URL/清单即可 |

原则不变：Runtime 只由**启动器/环境编排**写入 `Runtime/`；禁止当 `gui_patch` 静默覆盖。
"""
