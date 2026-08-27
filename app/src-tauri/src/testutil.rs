//! 单元测试用的临时目录。
//!
//! 以前每个测试各自写 `temp_dir().join("固定名字")`。同一个进程里跑的测试是并发的，
//! 上一次跑剩下的目录也不会自动消失，于是偶尔会出现一条测试踩到另一条的现场、
//! 复现不出来的失败。这里给每次调用一个独占路径：标签 + 进程号 + 自增序号。

use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};

static SEQ: AtomicU64 = AtomicU64::new(0);

/// 返回一条本次调用独占、且确定不存在的临时路径。
///
/// 不负责创建——调用方要目录就 `create_dir_all`，要文件就直接写。
///
/// 前缀刻意避开 `rvcf-` / `rvc-fabric` / `rvc`：`paths::clean_system_temp_leftovers`
/// 会扫系统 TEMP 里带这些特征的残留，用产品前缀命名的测试夹具会被自己的清理逻辑
/// 当垃圾删掉——开着变声器跑 `cargo test` 就能踩到。
pub fn scratch(tag: &str) -> PathBuf {
    let p = std::env::temp_dir().join(format!(
        "trm-t-{}-{}-{}",
        tag,
        std::process::id(),
        SEQ.fetch_add(1, Ordering::Relaxed)
    ));
    let _ = std::fs::remove_dir_all(&p);
    let _ = std::fs::remove_file(&p);
    p
}
