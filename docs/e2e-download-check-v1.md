# 下载验收记录 v1

## 2026-11-24：RVC 运行环境 ModelScope 下载验收（只读）

任务卡：工作区 `docs/codex/e2e-rvc-modelscope.md`。客户端基线为 `tm-release` / `e3c890c`，版本 `1.8.2`。实测时间为 2026-11-24 03:29:12 至 03:33:15（Asia/Taipei）。

本次只读取线上资源，没有修改 CNB、ModelScope、R2、D1、线上清单或网站，没有发版、checkout、stash、提交或推送。

### 执行方式与证据

新增 [忽略的真实客户端验收测试](../app/src-tauri/tests/support/e2e_modelscope_runtime.rs)，由 `lib.rs` 的 `#[cfg(test)]` 模块引入，以直接调用私有下载器。清单使用 `catalog::fetch_remote_catalog` 和 `catalog::parse_spec`；下载使用安装流程同一入口 `download::download_request`、`DownloadKind::Runtime`，保留清单中的大小和 SHA-256。`root: None` 关闭本地选源偏好写入和下载遥测。`catalog.rs` 新增的来源日志仅在测试构建中启用。

实际执行命令（PowerShell）：

```powershell
Set-Location F:\Dev\Turing-Mirror\RVC-Fabric\app\src-tauri
& 'F:\VS 2026\Common7\Tools\Launch-VsDevShell.ps1' -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
cargo test --locked --lib e2e_modelscope_runtime::live_modelscope_runtime_downloads -- --ignored --nocapture 2>&1 | Tee-Object -FilePath '../../TEMP/e2e-rvc-modelscope.log'
```

逐项机器结果保存在 [e2e-rvc-modelscope-v1.json](e2e-rvc-modelscope-v1.json)。原始控制台输出为 `TEMP/e2e-rvc-modelscope.log`；清单快照、原始 JSON 和客户端日志保留在 `User_Data/e2e/modelscope-20261123T192912Z-23768/`。`User_Data/` 和 `TEMP/` 均已由 `.gitignore` 排除。

### 逐项结果

| 项目 | 结果 | 实测证据 |
| --- | --- | --- |
| 1. 读取并解析线上清单 | 通过 | 客户端实际命中指定的 CNB `main/index.json`。AMD、NVIDIA、NVIDIA 50 三个原始 part 与客户端解析结果一致，`urls[0]` 均为 `Kara251/kara-rvc-model`，`urls[1]` 均为 CNB。 |
| 2. AMD 完整下载与 SHA-256 | 通过 | `runtime-amd-2026.07.21.tar` 完整下载 1,801,268,224 字节；下载器校验通过后重新读取文件计算 SHA-256，结果一致。实际选用 ModelScope，下载及两次哈希校验合计 240.38 秒。 |
| 3. 首地址失败后自动回退 | 通过 | 首地址 `not-exist.tar` 返回 404，客户端自动尝试第二个 ModelScope 地址。NVIDIA 下载 4,209,408 字节后按测试要求取消；`.part.src` 确认来源为 ModelScope，正式目标文件未生成。 |
| 4a. NVIDIA Range | 通过 | 一次 `Range: bytes=0-1023` 请求返回 206，`Content-Range: bytes 0-1023/6077133824`，读取 1,024 字节。 |
| 4b. NVIDIA 50 Range | 通过 | 一次 `Range: bytes=0-1023` 请求返回 206，`Content-Range: bytes 0-1023/6698774016`，读取 1,024 字节。 |
| 5. 清理测试大文件 | 通过 | 删除 AMD 完整包、NVIDIA 半截文件及来源标记。独立检查本次目录的 `.tar`、`.part`、`.src` 文件数为 0。 |

AMD 实测 SHA-256：

```text
5d5e4437c70ac1cf368232829381170d5a88f457eed20d14d35b1ef155dd0274
```

下载器实际选用的 AMD 地址（来源标记与客户端日志一致）：

```text
https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/19fad1f49c58719c3a15f78f277e9755f5732c17/fabric/runtime/runtime-amd-2026.07.21.tar
```

NVIDIA 回退与 Range 使用 `19fad1f49c58719c3a15f78f277e9755f5732c17`；NVIDIA 50 Range 使用线上清单给出的 `9a0685e5c794f2a183561dddacfd94f23cf0eef7`。完整 URL、重定向目标（移除临时签名查询参数）、请求字节数和响应范围均见机器结果。

回退关键输出（客户端日志节选）：

```text
2026-11-24 03:29:14.485 download runtime fail https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/RVC-runtime/not-exist.tar: resume: status 404
```

对应 `fallback` 结果记录 `pass: true`、`bytes: 4209408`、`cancelled: true` 和 `error: 已取消`。NVIDIA 与 NVIDIA 50 只验收了 Range / 部分下载回退，没有做完整文件 SHA-256 校验；本卡不包含解压、安装和运行环境启动验收。

主验收输出末尾：

```text
test e2e_modelscope_runtime::live_modelscope_runtime_downloads ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 521 filtered out; finished in 242.96s
```

清理后独立检查命令（在产品仓根目录运行）：

```powershell
$run = 'User_Data/e2e/modelscope-20261123T192912Z-23768'
$archives = @(Get-ChildItem -LiteralPath $run -Recurse -File | Where-Object { $_.Name -match '\.(tar|part|src)$' })
'archive_files=' + $archives.Count
```

```text
archive_files=0
```

另行遍历整个 `User_Data/e2e`，大于 16 MiB 的文件数也为 0；剩余文件为清单快照 1,090,236 字节、原始结果 5,402 字节、客户端日志 1,253 字节。

### 补充测试与首次失败记录

默认库测试确认新增验收为 `ignored`，不会自动下载大文件。首次并行执行 `cargo test --locked --lib` 时，本机 HTTP 模拟服务在 `src/download.rs:1070` 读取请求行发生 Windows `WouldBlock (10035)`，导致 `mirrors_follow_catalog_order_through_http_errors_hash_errors_and_redirects` 失败；该次结果不能记为全部通过。

```text
test e2e_modelscope_runtime::live_modelscope_runtime_downloads ... ignored, Live read-only acceptance; downloads about 1.8 GB and then removes archives
called `Result::unwrap()` on an `Err` value: Os { code: 10035, kind: WouldBlock, message: "A non-blocking socket operation could not be completed immediately." }
test result: FAILED. 519 passed; 1 failed; 2 ignored; 0 measured; 0 filtered out; finished in 75.29s
```

保留原始日志 `TEMP/e2e-rvc-modelscope-default-tests.log`。没有修改该模拟服务或客户端实现，单独复跑该用例通过：

```powershell
cargo test --locked --lib download::tests::mirrors_follow_catalog_order_through_http_errors_hash_errors_and_redirects -- --exact --nocapture
```

```text
test download::tests::mirrors_follow_catalog_order_through_http_errors_hash_errors_and_redirects ... ok
test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 521 filtered out; finished in 0.38s
```

单项复跑日志为 `TEMP/e2e-rvc-modelscope-mirror-retest.log`。

随后在完整下载和哈希校验结束后，串行复跑全部库测试，通过：

```powershell
cargo test --locked --lib -- --test-threads=1 2>&1 | Tee-Object -FilePath '../../TEMP/e2e-rvc-modelscope-default-serial.log' | Select-Object -Last 12
```

```text
test result: ok. 520 passed; 0 failed; 2 ignored; 0 measured; 0 filtered out; finished in 120.04s
```

串行通过和单项通过不抹去首次并行失败的记录，也没有据此修改下载器或扩大本次线上验收结论。

新测试文件的 `rustfmt --edition 2021 --check` 与 `git diff --check` 均通过。当前改动仅包含本地验收测试、测试构建接入、测试来源日志和本报告/结果文件。未执行 Git 提交或推送。

建议英文提交信息：`test: verify RVC runtime downloads from ModelScope`。
