# ModelScope 运行环境镜像 v1

发布仓可提供 `catalog/modelscope.json`，格式如下：

```json
{
  "repo": "Kara251/kara-rvc-model",
  "files": {
    "<小写 SHA-256>": "https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/<commit>/<path>"
  }
}
```

`scripts/build_catalog.py` 只将匹配的镜像加入 runtimes 各 part 的 `urls` 首位，保留已有 URL、SHA-256 和大小。文件不存在或哈希未匹配时保持原输出。音色、安装包、引擎资源与 extras 不应用此映射。

发布仓路径依次取 `--cnb`、`RVCF_CNB_DIR`、相邻的 `RVC-Fabric-Releases`、旧目录 `RVC-Fabric-Release`、仓内 `CNB-GIT-RELEASE`。只校验、不生成或发布文件时执行：

```powershell
python scripts/build_catalog.py --cnb ../RVC-Fabric-Releases check
```

运行环境解析器保留清单中的 ModelScope 与 CDN 地址，并把内置 CNB 地址补在末尾。运行环境下载按清单顺序尝试，不以测速或已有续传来源调整优先级；HTTP 错误、超时和校验失败后切换下一个地址。保留 SHA-256 校验，并核对清单中的非零大小。其他下载类型保持原有选源方式。

公开下载请求不携带账号凭据或 Cookie，HTTP 客户端跟随重定向。参见 [reqwest 重定向说明](https://docs.rs/reqwest/0.12.28/reqwest/redirect/index.html)。

回归测试以临时清单和本机 HTTP 服务覆盖：仅 runtimes 应用映射、各 part URL 顺序、旧目录兼容、403/404/503、首字节超时、跨主机 302、断流续传和 SHA-256/大小不匹配。测试不代表真实多 GB 制品已下载或发布。

```powershell
python -m pytest tests/test_build_catalog.py
cd app
npx vitest run
cd src-tauri
cargo test --locked -j 1
```
