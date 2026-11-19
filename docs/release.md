# RVC Fabric 发版

你决定什么时候构建、什么时候公开。推送到 `tm-release` 后，先准备安装包，再开放软件内更新。

## 1. 构建安装包

打开 [Build RVC Fabric](https://github.com/Turing-Mirror/RVC-Fabric/actions/workflows/windows-release.yml)，点 **Run workflow**，选择 `tm-release`。准备发版时勾选 **Prepare release**。只想试装时可以取消勾选，在本次运行的 **Artifacts** 下载 **RVC Fabric Setup x64**。

正式发版时，Actions 用项目的私钥签名，并用客户端内置的公钥验证。完成后到 [Releases](https://github.com/Turing-Mirror/RVC-Fabric/releases) 打开本版草稿。以 1.8.0 为例，附件应有 `RVC-Fabric-Setup-1.8.0.exe`、同名的 `.sig`、`.sha256` 和 `updater.json`。草稿里的安装包就是随后发给用户的文件。

在 Windows 测试机上安装一份 1.7.2，保留一个本地音色和原有设置，再用草稿里的 Setup 覆盖原目录。检查版本号、音色、设置和运行环境，试一次变声。也可以在空目录测试首次安装。

## 2. 公开并开放更新

1. 确认试装结果和更新日志，在 GitHub 草稿里点 **Publish release**。
2. 打开官网仓库的 [Update RVC Fabric](https://github.com/Turing-Mirror/Turing-Mirror-Page/actions/workflows/rvc-release.yml)，点 **Run workflow**，选 `main`，输入 `1.8.0`。以后填当次版本号。流程从刚公开的 Release 读取安装包和签名，同时更新官网下载、更新提示和更新日志，并检查线上版本。
3. 访问[固定下载地址](https://www.turingmirror.com/releases/rvc-fabric/setup.exe)，确认它下载当次版本。发布后保留该版本附件。如需修复安装包，递增版本号重新发版。

## 3. 让旧版收到 1.8.0

这一步只在迁移时做一次。1.7.2 从 CNB 查找更新。安装 1.8.0 后，客户端会向图灵镜官网检查后续版本。

先完成上面的官网发布。在 RVC Fabric 源码根目录运行以下命令。使用 Python 3.11 或更高版本、PyYAML、Node.js、Git、GitHub CLI 和 CNB CLI。GitHub CLI 需要能读取公共 Release，CNB 账号需要能推送发布仓，并具备 `repo-release:rw` 权限。脚本先读 `CNB_TOKEN`，这台电脑也可沿用 `~/.cnb/agent-token`。

```powershell
python scripts/legacy_update.py --publish
```

脚本读取 GitHub 上签过名的 1.8.0，核对签名与 SHA-256，将同一份 Setup 放到 CNB。以前分享的固定下载链接也会提供这份 1.8.0。两个地址的文件都通过校验后，脚本才提交旧版读取的清单。中途断线可以重复运行。省略 `--publish` 可以先在本机演练。

最后用一份仍在运行的 1.7.2 点「检查更新」，确认能下载、安装并重新启动到 1.8.0。保留这份 CNB 安装包、签名清单和旧索引，晚几个月打开软件的用户仍能升级。更早版本若无法使用内置更新，可以从官网下载 Setup，覆盖原安装目录。运行环境、底模和工具仍从原资源地址按需下载。

## 社区公告和图片

在官网仓库编辑 `public/releases/rvc-fabric/plaza.json`，将配图放在同目录的 `images/` 下。公告里填 `images/文件名.webp` 即可。运行 `npm run build` 后，把改过的源文件和对应的 `dist/` 文件一起推送到 `main`，1.8.0 客户端刷新后即可看到。

## 下次发版

将 `app/package.json`、`app/src-tauri/Cargo.toml`、`app/src-tauri/tauri.conf.json`、`scripts/installer/RVC_Fabric_Setup.iss` 及 `scripts/shell_version.py` 同步到新版本，同时更新 npm 和 Cargo 锁文件中的应用版本，在 `docs/releases/X.Y.Z.md` 写用户能看到的变化。运行 `python -m unittest tests.test_version_sync` 后推送发版分支，重复第 1、2 步。保管好私钥及其密码，签名用的 GitHub Secrets 在 RVC Fabric 仓库的 `release` 环境中。
