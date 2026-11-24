# RVC 客户端清单地址 v1

日期：2026-11-24。任务卡：工作区 `docs/codex/rvc-client-catalog-urls.md`。基线：`tm-release` / `49e00e1`。

代码与单元测试已完成。当前线上清单的引擎核心与 VB-Cable 首地址仍为 CNB，线上 ModelScope 首选验收未通过；本次没有修改线上清单或上传制品，没有发版、提交、push、checkout 或 stash。

## 改动文件与行为

| 文件 | 改动 |
| --- | --- |
| [catalog.rs](../app/src-tauri/src/catalog.rs) | 新增 `file_download_urls`，按完整 SHA-256 匹配清单对象。递归支持顶层 `engine_core`、`audio_tools`、`vbcable`、`vcredist`、`setup`，以及 `packages.*` 等嵌套对象和数组。保留清单 URL 顺序，仅接受 HTTPS，并去重追加旧地址。增加 4 个单元测试。 |
| [engine_assets.rs](../app/src-tauri/src/engine_assets.rs) | 两个共用下载入口接入 `catalog_urls_for_pack`；使用现有 `fetch_remote_catalog_cached(12)`。清单读取失败时不向安装流程传播该错误，保留旧 CNB 下载地址。增加一个默认忽略的线上清单测试。 |
| [download.rs](../app/src-tauri/src/download.rs) | `Dependency` 与 `Runtime` 一样按输入顺序尝试，取消对依赖包的测速重排与续传来源优先重排。保留单连接、原始预期 SHA-256、校验和失败切源逻辑。增加本机 HTTP 测试，覆盖首源失败、错误哈希、已有备用源半截文件及最终校验成功。 |
| [本报告](rvc-client-catalog-urls-v1.md) | 保存完整排查清单、执行命令、测试结果和受保护文件校验值。 |

两个入口覆盖引擎核心、独立音频工具、VB-Cable 和 VC++ 运行库。已经校验通过的本地缓存包仍直接复用，不额外读取线上清单。文件身份以调用方原有 SHA-256 为准，不按文件名替换包或采纳不同哈希的条目。

实际代码检查发现原下载器仅对 `Runtime` 保持顺序，`Dependency` 原先仍调用测速重排。因此需要同时修改 `download.rs`，否则将 ModelScope 放在 URL 列表首位也不能保证优先尝试。

## CNB 地址构造完整排查

排查覆盖当前 Rust 客户端、前端、`launcher/` 和 `tools/`，并补查仓库内构建发布脚本。检索项包括 `lfs_urls`、`release_urls`、`cnb_release_url`、`CNB_REPO`、`cnb.cool`、`/-/lfs` 和 `/-/releases/download`。

| 位置 | 用途与处理方式 |
| --- | --- |
| `engine_assets.rs:24,221,235`：`CNB_REPO`、`lfs_urls`、`release_urls` | 构造官方及清单镜像基址下的 LFS / Release 地址。保留生成器，所得地址由新增解析器去重后放到文件清单地址之后。 |
| `engine_assets.rs:248,296`：`fetch_pack_with_fallback`、`fetch_and_extract` | 原先只使用拼出的 CNB 地址；两个入口均已接入按 SHA-256 解析的缓存清单地址。音频工具继续保持原有不构造 LFS 地址的规则。 |
| `vcredist.rs:116`：`ensure_pack` | 调用 `release_urls`，再调用 `fetch_pack_with_fallback`。通过共用入口获得新行为，无需改动此文件。 |
| `engine_assets.rs:404`：`ensure_vbcable_pack` | VB-Cable 实际下载路径为此函数 → `fetch_and_extract`；已由共用入口覆盖。安装、卸载与 UAC 逻辑未改动。 |
| `catalog.rs:68,72,77,279`：`lfs_url`、`release_url`、`fallback_blob`、`normalize_part` | 运行环境内置地址及旧条目兜底。现有解析已经将清单地址放在前、内置地址追加在后，保持现状。 |
| `extra_assets.rs:227,231,237`：`release_url`、`lfs_url`、`parse_spec` | 扩展文件已有 HTTPS 清单 URL 解析，仅在无可用 URL 时构造 CNB 备用地址，保持现状。 |
| `store.rs:51`：`voice_download_urls` | 以音色清单中的地址为起点，为 CNB 附件追加镜像仓库同路径；并非忽略文件地址后另拼主源，保持现状。 |
| `mirrors.rs:160`：`lfs_bases` | 提供官方仓库与清单配置的镜像基址，不独立决定文件主地址。保留；依赖包最终顺序由新解析器确定。 |
| `store.rs:158,832`：相对封面路径与 `ch-banner` | 构造 CNB git-raw 图片地址；不是有 SHA-256 对应条目的依赖包，保持现状。 |
| `plaza.rs:112,142`：`resolve_image_url` | 新图片使用发布网站，旧相对图片路径保留 CNB git-raw 兼容规则；没有本卡要求的文件哈希映射，保持现状。 |
| `catalog.rs:9–27`：清单来源常量 | CNB `index.json` 等元数据读取地址，不是待迁移制品地址，保持现状。 |
| `app/src/lib/links.ts:39` | 用户打开仓库页面的链接，不是文件下载器，保持现状。 |
| `update.rs` | 更新信息已读取发布网站的 `app.json`，GUI 补丁使用传入的完整 URL；没有自拼 CNB 文件地址。`setup` / `packages.*` 的哈希条目已被新增通用解析器支持，但未新增另一条安装器下载流程。 |
| `hf.rs`、`download.rs`、`lib.rs` 中其余 CNB 命中 | 注释、测试数据或域名判定，不存在额外的 CNB 制品地址构造入口。 |
| `scripts/build_setup.py`、`scripts/cnb_release.py`、`scripts/prepare_setup_release.py`、`scripts/publish_asset.py` | 构建、发布、资产查询或分发文档生成工具，不是本卡客户端下载入口，均未改动。 |

当前受检代码未找到 `cnb_release_url` 符号。`scripts/build_catalog.py` 和 `tests/test_build_catalog.py` 的用户未提交改动完整保留，不参与此次修改或测试运行。

## 单元测试

PowerShell 执行环境及命令：

```powershell
Set-Location F:\Dev\Turing-Mirror\RVC-Fabric\app\src-tauri
& 'F:\VS 2026\Common7\Tools\Launch-VsDevShell.ps1' -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
cargo test --locked --lib 2>&1 | Tee-Object -FilePath '../../TEMP/rvc-client-catalog-urls-unit.log' | Select-Object -Last 15
```

新增单元测试均通过：

```text
test catalog::tests::file_urls_accept_only_https_and_deduplicate_after_trimming ... ok
test catalog::tests::file_urls_match_hashes_in_direct_entries_and_nested_packages ... ok
test catalog::tests::file_urls_preserve_catalog_order_and_append_unique_fallbacks ... ok
test catalog::tests::missing_or_unmatched_catalog_keeps_original_file_urls ... ok
test download::tests::dependencies_keep_catalog_order_and_verify_hashes_with_a_resumed_fallback ... ok
```

输出末尾：

```text
test download::tests::first_byte_timeout_tries_the_next_catalog_url has been running for over 60 seconds
test download::tests::first_byte_timeout_tries_the_next_catalog_url ... ok

test result: ok. 525 passed; 0 failed; 3 ignored; 0 measured; 0 filtered out; finished in 75.28s
```

退出码 0。本次没有出现此前的本机模拟服务 `WouldBlock` 失败，因此未做重跑。新增线上测试默认为 `#[ignore]`，普通测试不读取线上清单。

## 只读线上检查

```powershell
cargo test --locked --lib engine_assets::tests::live_dependency_catalog_urls -- --ignored --nocapture 2>&1 | Tee-Object -FilePath '../../TEMP/rvc-client-catalog-urls-live.log'
```

检查时间：2026-11-24 19:09:43（Asia/Taipei）。实际命中 `https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/git/raw/main/index.json`，测试未下载或解压制品。

| 条目 | ModelScope 首选验收 | 线上清单与客户端解析的实际首地址 |
| --- | --- | --- |
| `engine_core` | 未通过 | `https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/engine-core/engine-core-260722.zip` |
| `vbcable` | 未通过 | `https://cnb.cool/Turing-Mirror/RVC-Fabric-Releases/-/releases/download/vbcable/vbcable-setup.zip` |

两项均成功匹配客户端原有 SHA-256；当前清单 Release 地址位于第一位，旧 LFS 地址位于第二位，重复 Release 地址未追加。线上清单当时尚未把 ModelScope 放在首位；更新清单后可用同一忽略测试复验。

输出末尾：

```text
ModelScope is not first for: ["engine_core", "vbcable"]
test engine_assets::tests::live_dependency_catalog_urls ... FAILED

failures:
    engine_assets::tests::live_dependency_catalog_urls

test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 measured; 527 filtered out; finished in 0.47s
```

退出码 101，保留该未通过结果。完整 `CATALOG_URL_RESULT` 记录位于 `TEMP/rvc-client-catalog-urls-live.log`；全部日志位于已忽略的 `TEMP/` 下。

## 用户改动与提交状态

执行前后的 SHA-256 一致：

```text
scripts/build_catalog.py
74A6EE4F04A205BF18CB752073C0F7B052C994A7D850144E67B95AA8619ED906
tests/test_build_catalog.py
B03EFC73ED5831BC53E1C4461882C32A4B8FAC40F3CA62BE204F1CCE79172DF9
```

`git diff --check` 通过。没有暂存、提交或推送；英文提交信息待用户审定。

建议提交信息：`Prefer catalog URLs for RVC dependency downloads`
