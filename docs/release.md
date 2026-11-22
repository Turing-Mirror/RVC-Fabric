# RVC Fabric 发版

整体流程和两款 Fabric 共用的地址见官网仓库 `docs/fabric-release-v1.md`。本文写 RVC Fabric 的具体操作。

## 1. 准备版本

将 `app/package.json`、`app/src-tauri/Cargo.toml`、`app/src-tauri/tauri.conf.json`、`scripts/installer/RVC_Fabric_Setup.iss` 及 `scripts/shell_version.py` 同步到新版本，同时更新 npm 和 Cargo 锁文件中的应用版本。在 `docs/releases/X.Y.Z.md` 写用户能看到的变化，每行一条。运行 `python -m unittest tests.test_version_sync` 后推送 `tm-release`。

## 2. 构建安装包

打开 [Build RVC Fabric](https://github.com/Turing-Mirror/RVC-Fabric/actions/workflows/windows-release.yml)，点 **Run workflow**，选择 `tm-release`，勾选 **Prepare release**。Actions 用项目私钥签名，并用客户端内置的公钥验证，然后在 [Releases](https://github.com/Turing-Mirror/RVC-Fabric/releases) 生成本版草稿。附件应有 `RVC-Fabric-Setup-X.Y.Z.exe`、同名的 `.sig`、`.sha256` 和 `updater.json`。

只想试装时取消勾选 **Prepare release**，在本次运行的 **Artifacts** 下载 **RVC Fabric Setup x64**。

签名用的 GitHub Secrets 在 RVC Fabric 仓库的 `release` 环境中。保管好私钥及其密码。

## 3. 公开 GitHub Release

确认更新说明后，在草稿里点 **Publish release**。

## 4. 发布到 CNB

在源码根目录运行：

```powershell
python scripts/cnb_release.py --publish
```

版本号默认读取 `app/package.json`，也可以用 `--version` 指定。脚本读取 GitHub 上已公开的 Release，核对签名与 SHA-256，把同一份 Setup 以版本化文件名和固定文件名 `RVC_Fabric_Setup.exe` 上传到 CNB 的 `setup` 标签，再更新清单、更新日志和 `updater.json` 并推送 CNB 发布仓。省略 `--publish` 只在临时目录演练。

需要 Python 3.11 或更高版本、PyYAML、Node.js、Git、GitHub CLI 和 CNB CLI。CNB 令牌需要 `repo-release:rw` 权限。脚本先读 `CNB_TOKEN`，这台电脑也可沿用 `~/.cnb/agent-token`。中途断线可以重复运行。

## 5. 同步官网

在官网仓库运行 `npm run sync:releases -- rvc-fabric X.Y.Z`，构建后推送 `main`，Cloudflare Pages 自动部署。部署完成后确认 `https://www.turingmirror.com/releases/rvc-fabric/updater.json` 是新版本，下载按钮拿到的也是新版安装包。

## 社区公告和图片

在官网仓库编辑 `public/releases/rvc-fabric/plaza.json`，将配图放在同目录的 `images/` 下。公告里填 `images/文件名.webp` 即可。运行 `npm run build` 后，把改过的源文件和对应的 `dist/` 文件一起推送到 `main`。
