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

## 4. 发布到 Cloudflare、ModelScope 与 CNB 清单仓

在源码根目录运行：

```powershell
python scripts/cnb_release.py --publish
```

版本号默认读取 `app/package.json`，也可以用 `--version` 指定。脚本核对已公开 GitHub Release 的签名与 SHA-256，把版本化安装包和固定名 `RVC_Fabric_Setup.exe` 上传到 Cloudflare R2 的 `trm-releases/rvc-fabric/`。两份 CDN 下载均通过 SHA-256 与大小检查后，删除同前缀中的旧版本化安装包。安装包清单使用 `https://cdn.turingmirror.com/f/rvc-fabric/` 下的版本化地址。

随后将版本化安装包上传至 ModelScope 仓库 `Kara251/kara-rvc-model` 的 `fabric/setup/`，核对 SHA-256 与大小后，将固定提交的下载地址写入 `updater.json` 的 `urls`，置于 CDN 地址之后。1.8.2 之后的客户端在 CDN 下载失败时按 `urls` 顺序改用 ModelScope；检查更新时若无法访问官网，则改读 CNB 发布仓的 `index.json` 与 `updater.json`。

清单源、index、更新日志和 updater 仍提交并推送 CNB 发布仓。省略 `--publish` 只在临时目录演练；同版本重跑可迁移地址，不重复写入更新日志。

需要 Python 3.11 或更高版本、PyYAML、Node.js、Git、GitHub CLI、CNB CLI、Wrangler 和 ms-hub。CNB Git 推送继续使用 CNB CLI 的凭据；R2 复用 Wrangler 登录或 Cloudflare 环境变量；ModelScope 复用 `ms-hub login` 保存的登录，也可用 `TRM_MS_HUB` 指定 CLI。多个 Cloudflare 账户时设置 `CLOUDFLARE_ACCOUNT_ID`，也可用 `TRM_WRANGLER` 指定 CLI。中途断线可以重复运行。

## 5. 同步官网

在官网仓库运行 `npm run sync:releases -- rvc-fabric X.Y.Z`，构建后推送 `main`，Cloudflare Pages 自动部署。部署完成后确认 `https://www.turingmirror.com/releases/rvc-fabric/updater.json` 是新版本，下载按钮拿到的也是新版安装包。

## 社区公告和图片

在官网仓库编辑 `public/releases/rvc-fabric/plaza.json`，将配图放在同目录的 `images/` 下。公告里填 `images/文件名.webp` 即可。运行 `npm run build` 后，把改过的源文件和对应的 `dist/` 文件一起推送到 `main`。
