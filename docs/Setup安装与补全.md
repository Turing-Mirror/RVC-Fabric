# Setup 安装与环境补全

产品名：**RVC Fabric**  
制品仓：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases  

## 定稿用户动线

1. **下载 Setup**（薄包：软件壳 + 启动器 + 主界面，**不含** Runtime）  
2. **Setup 安装** → 选目录 + 显卡分版 → 写 `package_meta.json` + 桌面快捷方式  
3. **启动器**自动从 CNB **Release** 下载对应 Runtime 并解压，再补 Hubert/RMVPE  
4. **进入主界面** → 新手指引  
5. **模型社区**下载 pth / index（CNB **Git LFS**）  
6. 开始变声 → 调参 → 免费优化 → 付费优化 → 收集资料 → 进群  

## 分发约定

| 内容 | 通道 | 地址形态 |
|------|------|----------|
| Setup 薄包 | CNB Git LFS（`setup/`） | `…/-/lfs/<sha256>` |
| Runtime | CNB **Release** 附件 | `…/-/releases/download/RVC-runtime/<file>` |
| 音色 voice_pack | CNB Git LFS（`voices/`） | `…/-/lfs/<sha256>` |
| 清单 / catalog | raw 文本 | `…/-/git/raw/main/catalog/…` |

Release 不可用时，启动器会回退到同文件的 LFS 直链（需 sha256）。

运维命令见 `CNB-GIT-RELEASE/SYNC_COMMANDS.txt`（使用已安装的 **cnb CLI / skill**，勿自造路径）。

## 开发：打 Setup 包

```bat
python scripts/build_setup.py --clean
```

可选：

```bat
python scripts/build_setup.py --copy-cnb
```

会把 `dist/RVC_Fabric_Setup/` 打成 zip 放到 `CNB-GIT-RELEASE/setup/`，再按 SYNC 推到 CNB。

开发直接跑向导（需本机 Python + 已有壳层）：

```bat
python launcher/setup_app.py
```

或启动器（会检测 Runtime 并补全）：

```bat
python launcher/bootstrap.py
```

## 关键代码

| 模块 | 职责 |
|------|------|
| `launcher/setup_app.py` | Setup 安装向导 |
| `launcher/bootstrap.py` | 启动器；缺 Runtime 时自动 `ensure_runtime` |
| `launcher/cnb_sources.py` | CNB 清单 / Release·LFS URL |
| `launcher/runtime_provision.py` | 下载 tar、校验 sha256、解压、写 meta |
| `scripts/build_setup.py` | 打薄包 |

## 与全量包的关系

- **Setup 路径**（推荐新用户）：薄包 + 联网补 Runtime。  
- **全量包**（打包机）：`scripts/build_release.py --variant nvidia|amd|nvidia50` 仍可打出含 Runtime 的完整目录，适合离线场景。  
