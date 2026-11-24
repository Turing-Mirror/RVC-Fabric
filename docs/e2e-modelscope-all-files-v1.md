# ModelScope 全量下载验收 v1

日期：2026-11-24。仓库分支：`tm-release`；提交：`2357ccf9dd46a907f59b2fa0520097e0b09ef56b`。

执行任务卡 `F:\Dev\Turing-Mirror\docs\codex\e2e-modelscope-all-files.md`。本次只修改测试文件和生成报告；没有改动业务代码，没有修改线上资源，没有提交、push、checkout 或 stash。

## 执行命令

在 PowerShell 中执行：

```powershell
Set-Location F:\Dev\Turing-Mirror\RVC-Fabric\app\src-tauri
& 'F:\VS 2026\Common7\Tools\Launch-VsDevShell.ps1' -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
cargo test --locked --lib live_dependency_catalog_urls -- --ignored --nocapture 2>&1 | Tee-Object -FilePath '../../TEMP/e2e-ms-all-dependency.log'
cargo test --locked --lib live_modelscope_all_files_downloads -- --ignored --nocapture 2>&1 | Tee-Object -FilePath '../../TEMP/e2e-ms-all-rvc-downloads.log'

Set-Location F:\Dev\Turing-Mirror\RVC-Fabric
$env:PYTHONUTF8='1'
python -u app/src-tauri/tests/support/e2e_modelscope_all_files.py 2>&1 | Tee-Object -FilePath TEMP/e2e-ms-all-python.log
```

两次 Rust 线上测试退出码均为 0。Python 验收退出码为 1，原因是下述两次 Range 响应状态为 200。

## 清单读取

Python 验收开始时间为 `2026-11-24T12:58:56.836033+00:00`，结束时间为 `2026-11-24T12:59:15.262165+00:00`，均为 UTC。

| 清单 | HTTP | JSON 字节数 | ModelScope 文件引用数 | Range 请求数 |
| --- | --- | --- | --- | --- |
| RVC CNB | 200 | 1098149 | 76 | 71 |
| GSV CNB | 200 | 37072 | 51 | 50 |
| GSV 官网 | 200 | 37072 | 51 | 50 |

清单地址：

- RVC CNB：https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/index.json
- GSV CNB：https://cnb.cool/Turing-Mirror/GPT-SoVITS-Fabric-Releases/-/git/raw/main/index.json
- GSV 官网：https://www.turingmirror.com/releases/gpt-sovits-fabric/index.json

GSV 官网与 CNB 两份清单的字节数和 SHA-256 相同：`f117c1e184b353a90c72823d06ce446515e43c7f7fa7c528f767131880c91438`。

## 1. RVC 引擎核心与 VB-Cable 地址

现有 `live_dependency_catalog_urls` 测试通过。实际读取 CNB `index.json`，两个条目的首地址均为 ModelScope。原始结果：

```text
CATALOG_URL_RESULT {"catalog_first":"https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/ebdaa2fb6e4ea357e5bd27bee9078cf45b20887e/fabric/engine-core/engine-core-260722.zip","catalog_sha256":"ecb3231c7d26ad553e902ac24d40daf3d3fbe5786a7d8e78af8038fc389cab47","key":"engine_core","pass":true,"sha256":"ecb3231c7d26ad553e902ac24d40daf3d3fbe5786a7d8e78af8038fc389cab47","urls":["https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/ebdaa2fb6e4ea357e5bd27bee9078cf45b20887e/fabric/engine-core/engine-core-260722.zip","https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/engine-core/engine-core-260722.zip","https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/ecb3231c7d26ad553e902ac24d40daf3d3fbe5786a7d8e78af8038fc389cab47"]}
CATALOG_URL_RESULT {"catalog_first":"https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/ebdaa2fb6e4ea357e5bd27bee9078cf45b20887e/fabric/vbcable/vbcable-setup.zip","catalog_sha256":"0518435a76264856e4e2733ac22143ff16595c763cbf58106ed04d6895c6ddf5","key":"vbcable","pass":true,"sha256":"0518435a76264856e4e2733ac22143ff16595c763cbf58106ed04d6895c6ddf5","urls":["https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/ebdaa2fb6e4ea357e5bd27bee9078cf45b20887e/fabric/vbcable/vbcable-setup.zip","https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/vbcable/vbcable-setup.zip","https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/lfs/0518435a76264856e4e2733ac22143ff16595c763cbf58106ed04d6895c6ddf5"]}
```

输出末尾：

```text
test engine_assets::tests::live_dependency_catalog_urls ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 527 filtered out; finished in 1.18s
```

## 2. RVC 完整下载

使用客户端 `download::download_request`。VB-Cable 使用 `Dependency`，音色包使用 `VoicePack`，扩展文件使用 `Generic`；连接数使用下载器默认值。`root: None`，不写选源偏好或下载遥测。

从当前线上 `voices` 中按非零 `size_bytes` 选择最小的音色包，结果为 `guanguan` / `guanguan-v2.zip`，51,006,395 字节；从 `extras.*.files` 中选择最小文件，结果为 `UVR-DeNoise-Lite.pth`，17,922,277 字节。下载器完成后再次读取文件计算 SHA-256，并核对实际成功来源日志。

## 3. GSV 两份清单的 pymss 完整下载

分别从 CNB 和官网清单选择 `extras` 中最小的 pymss 文件，均为 `pymss-denoise` 下的 `UVR-DeNoise-Lite.pth`。两份清单分别发起完整下载，均使用各自清单中的首位 URL。

五次完整下载的大小结果：

| 下载项 | 清单文件名 | 实际字节数 | 清单字节数 | 大小与 SHA-256 |
| --- | --- | --- | --- | --- |
| RVC vbcable | vbcable-setup.zip | 1299644 | 1299644 | 通过 |
| RVC voice | guanguanV1 | 51006395 | 51006395 | 通过 |
| RVC extra | legacy_vr/vr_denoise/UVR-DeNoise-Lite.pth | 17922277 | 17922277 | 通过 |
| GSV CNB pymss | legacy_vr/vr_denoise/UVR-DeNoise-Lite.pth | 17922277 | 17922277 | 通过 |
| GSV 官网 pymss | legacy_vr/vr_denoise/UVR-DeNoise-Lite.pth | 17922277 | 17922277 | 通过 |

RVC 三项结果原文，包括实际 URL、实际 SHA-256 和预期 SHA-256：

```text
RESULT {"check":"vbcable","evidence":{"actual_url":"https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/ebdaa2fb6e4ea357e5bd27bee9078cf45b20887e/fabric/vbcable/vbcable-setup.zip","bytes":1299644,"expected_bytes":1299644,"expected_sha256":"0518435a76264856e4e2733ac22143ff16595c763cbf58106ed04d6895c6ddf5","id":null,"kind":"file","name":"vbcable-setup.zip","sha256":"0518435a76264856e4e2733ac22143ff16595c763cbf58106ed04d6895c6ddf5","urls":["https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/ebdaa2fb6e4ea357e5bd27bee9078cf45b20887e/fabric/vbcable/vbcable-setup.zip","https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/vbcable/vbcable-setup.zip"]},"pass":true}
RESULT {"check":"voice","evidence":{"actual_url":"https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/bd6eb6155af4eabbe100e3fbd4ace25c9d936b81/reposts/guanguan-v2.zip","bytes":51006395,"expected_bytes":51006395,"expected_sha256":"dfb9a54afe78a95b32f1742090bd55541c28a205f3f958884247e4a454e2aeb3","id":"guanguan","kind":"voice_pack","name":"guanguanV1","sha256":"dfb9a54afe78a95b32f1742090bd55541c28a205f3f958884247e4a454e2aeb3","urls":["https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/bd6eb6155af4eabbe100e3fbd4ace25c9d936b81/reposts/guanguan-v2.zip"]},"pass":true}
RESULT {"check":"extra","evidence":{"actual_url":"https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/ebdaa2fb6e4ea357e5bd27bee9078cf45b20887e/fabric/extras/pymss-denoise/UVR-DeNoise-Lite.pth","bytes":17922277,"expected_bytes":17922277,"expected_sha256":"0023492fe98c406817b5253965de19ede65d1c147db015a3a428f07602e99571","id":null,"kind":"file","name":"legacy_vr/vr_denoise/UVR-DeNoise-Lite.pth","sha256":"0023492fe98c406817b5253965de19ede65d1c147db015a3a428f07602e99571","urls":["https://modelscope.cn/models/Kara251/kara-rvc-model/resolve/ebdaa2fb6e4ea357e5bd27bee9078cf45b20887e/fabric/extras/pymss-denoise/UVR-DeNoise-Lite.pth","https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/pymss/UVR-DeNoise-Lite.pth"]},"pass":true}
```

GSV 两项结果原文：

```text
FULL_RESULT {"catalog": "gsv_cnb", "catalog_url": "https://cnb.cool/Turing-Mirror/GPT-SoVITS-Fabric-Releases/-/git/raw/main/index.json", "key": "pymss-denoise", "name": "legacy_vr/vr_denoise/UVR-DeNoise-Lite.pth", "actual_url": "https://modelscope.cn/models/Kara251/kara-gsv-model/resolve/8a94ba4caec8574cda883886d4ddcba68dbf01ee/fabric/extras/pymss-denoise/UVR-DeNoise-Lite.pth", "expected_bytes": 17922277, "expected_sha256": "0023492fe98c406817b5253965de19ede65d1c147db015a3a428f07602e99571", "status": 200, "final_url_without_query": "https://cdn-lfs-cn-1.modelscope.cn/prod/lfs-objects/00/23/492fe98c406817b5253965de19ede65d1c147db015a3a428f07602e99571", "bytes": 17922277, "sha256": "0023492fe98c406817b5253965de19ede65d1c147db015a3a428f07602e99571", "pass": true, "download_deleted": true}
FULL_RESULT {"catalog": "gsv_web", "catalog_url": "https://www.turingmirror.com/releases/gpt-sovits-fabric/index.json", "key": "pymss-denoise", "name": "legacy_vr/vr_denoise/UVR-DeNoise-Lite.pth", "actual_url": "https://modelscope.cn/models/Kara251/kara-gsv-model/resolve/8a94ba4caec8574cda883886d4ddcba68dbf01ee/fabric/extras/pymss-denoise/UVR-DeNoise-Lite.pth", "expected_bytes": 17922277, "expected_sha256": "0023492fe98c406817b5253965de19ede65d1c147db015a3a428f07602e99571", "status": 200, "final_url_without_query": "https://cdn-lfs-cn-1.modelscope.cn/prod/lfs-objects/00/23/492fe98c406817b5253965de19ede65d1c147db015a3a428f07602e99571", "bytes": 17922277, "sha256": "0023492fe98c406817b5253965de19ede65d1c147db015a3a428f07602e99571", "pass": true, "download_deleted": true}
```

RVC 下载测试输出末尾：

```text
test e2e_modelscope_runtime::live_modelscope_all_files_downloads ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 528 filtered out; finished in 13.73s
```

## 4. 全部 ModelScope 首地址 Range 检查

请求头为 `Range: bytes=0-0` 和 `Accept-Encoding: identity`，使用 6 个并发请求。每份清单内按 URL 和声明大小去重；同一 URL 出现在不同清单时分别请求。合计 171 次请求，覆盖 121 个不同文件 URL 和 178 个文件引用。

判定条件为 HTTP 206、响应体恰好 1 字节，以及 `Content-Range: bytes 0-0/<总长>` 中的总长等于清单 `size_bytes`。

| 清单 | 请求数 | 符合条件 | 不符合条件 |
| --- | --- | --- | --- |
| RVC CNB | 71 | 71 | 0 |
| GSV CNB | 50 | 49 | 1 |
| GSV 官网 | 50 | 49 | 1 |
| 合计 | 171 | 169 | 2 |

两份 GSV 清单中的 `source_url` 另有一个 ModelScope 仓库主页地址，不是文件下载地址，未对仓库主页发 Range。清单中的其余 ModelScope 文件地址均已覆盖。

不符合条件的两项均为 `/extras/gsv-v3/files/1` 的同一个 `config.json` URL。两次均返回 HTTP 200；响应体为 1 字节 `{`，`Content-Range` 均为 `bytes 0-0/1402`，总长与清单的 1,402 字节一致。两次均按未达到 HTTP 206 条件记录。

两项原始返回记录（含各自响应头和响应体）：

```text
RANGE_FAILURE {"catalog": "gsv_cnb", "path": "/extras/gsv-v3/files/1", "url": "https://modelscope.cn/models/Kara251/kara-gsv-model/resolve/ba30c8ae2d8a533926d664f1691e3b757a6c3902/fabric/extras/gsv-v3/models--nvidia--bigvgan_v2_24khz_100band_256x/config.json", "expected_bytes": 1402, "sha256": "d77e2c96583ca2296ac112a56ec7cc6bd5da4bf7681ceff18448bedc4fcf6512", "name": "models--nvidia--bigvgan_v2_24khz_100band_256x/config.json", "paths": ["/extras/gsv-v3/files/1"], "status": 200, "content_range": "bytes 0-0/1402", "received_bytes": 1, "final_url_without_query": "https://modelscope.cn/models/Kara251/kara-gsv-model/resolve/ba30c8ae2d8a533926d664f1691e3b757a6c3902/fabric/extras/gsv-v3/models--nvidia--bigvgan_v2_24khz_100band_256x/config.json", "pass": false, "headers": {"Date": "Tue, 24 Nov 2026 12:59:09 GMT", "Content-Type": "application/json", "Content-Length": "1", "Connection": "close", "Accept-Ranges": "bytes", "Content-Disposition": "attachment;filename=config.json", "Content-Range": "bytes 0-0/1402", "Strict-Transport-Security": "max-age=15724800; includeSubDomains", "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, PATCH, OPTIONS", "Access-Control-Allow-Headers": "DNT,Keep-Alive,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization", "Access-Control-Max-Age": "1728000"}, "body_hex": "7b", "body_text": "{"}
RANGE_FAILURE {"catalog": "gsv_web", "path": "/extras/gsv-v3/files/1", "url": "https://modelscope.cn/models/Kara251/kara-gsv-model/resolve/ba30c8ae2d8a533926d664f1691e3b757a6c3902/fabric/extras/gsv-v3/models--nvidia--bigvgan_v2_24khz_100band_256x/config.json", "expected_bytes": 1402, "sha256": "d77e2c96583ca2296ac112a56ec7cc6bd5da4bf7681ceff18448bedc4fcf6512", "name": "models--nvidia--bigvgan_v2_24khz_100band_256x/config.json", "paths": ["/extras/gsv-v3/files/1"], "status": 200, "content_range": "bytes 0-0/1402", "received_bytes": 1, "final_url_without_query": "https://modelscope.cn/models/Kara251/kara-gsv-model/resolve/ba30c8ae2d8a533926d664f1691e3b757a6c3902/fabric/extras/gsv-v3/models--nvidia--bigvgan_v2_24khz_100band_256x/config.json", "pass": false, "headers": {"Date": "Tue, 24 Nov 2026 12:59:12 GMT", "Content-Type": "application/json", "Content-Length": "1", "Connection": "close", "Accept-Ranges": "bytes", "Content-Disposition": "attachment;filename=config.json", "Content-Range": "bytes 0-0/1402", "Strict-Transport-Security": "max-age=15724800; includeSubDomains", "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, PATCH, OPTIONS", "Access-Control-Allow-Headers": "DNT,Keep-Alive,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization", "Access-Control-Max-Age": "1728000"}, "body_hex": "7b", "body_text": "{"}
```

Python 输出末尾：

```text
RANGE_PROGRESS 171/171 passed=169
RANGE_SUMMARY rvc_cnb total=71 passed=71
RANGE_SUMMARY gsv_cnb total=50 passed=49
RANGE_SUMMARY gsv_web total=50 passed=49
PYTHON_RESULT pass=False
```

逐 URL 的全部结果保存在 [JSON 附件](e2e-modelscope-all-files-v1.json)。该附件保留 URL、所属清单和路径、HTTP 状态、Content-Range、声明大小及两项不一致响应的原始内容。重定向目标 URL 中的临时签名查询参数未保存。

## 5. 下载文件清理

所有完整下载文件均写入 `F:\Dev\Turing-Mirror\RVC-Fabric\User_Data\e2e-ms-all\`，完成校验后由测试删除，未解压或安装。

剩余的 7 个清单快照、结果 JSON 和客户端日志已复制到 `TEMP/e2e-ms-all-evidence-20261124T130238Z/`，逐文件 SHA-256 比对一致后，删除了本次下载目录。清理前检查该目录仅有本次创建的文件。

清理输出原文：

```text
{"EvidencePath":"F:\\Dev\\Turing-Mirror\\RVC-Fabric\\TEMP\\e2e-ms-all-evidence-20261124T130238Z","EvidenceFiles":7,"DownloadDirectoryExists":false}
```

## 测试文件与默认运行

- 修改已有测试文件：[e2e_modelscope_runtime.rs](../app/src-tauri/tests/support/e2e_modelscope_runtime.rs)，增加 `live_modelscope_all_files_downloads`，仍由原有 `#[cfg(test)]` 模块引入，且标记 `#[ignore]`。
- 新增测试文件：[e2e_modelscope_all_files.py](../app/src-tauri/tests/support/e2e_modelscope_all_files.py)，为手动执行的 Python 验收脚本，未接入业务代码。
- 报告附件：[e2e-modelscope-all-files-v1.json](e2e-modelscope-all-files-v1.json)。

验证默认忽略的命令与输出：
```powershell
cargo test --locked --lib live_modelscope_all_files_downloads
```

```text
test e2e_modelscope_runtime::live_modelscope_all_files_downloads ... ignored, Read-only live acceptance for VB-Cable, the smallest voice pack and extra file

test result: ok. 0 passed; 0 failed; 1 ignored; 0 measured; 528 filtered out; finished in 0.00s
```

原始控制台日志为 `TEMP/e2e-ms-all-dependency.log`、`TEMP/e2e-ms-all-rvc-downloads.log`、`TEMP/e2e-ms-all-python.log`、`TEMP/e2e-ms-all-default.log`。`TEMP/` 已被 Git 忽略。
