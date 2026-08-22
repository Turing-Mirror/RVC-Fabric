//! asset 协议的运行时放行清单。
//!
//! tauri.conf.json 里的 scope 是静态 glob，而安装根目录随用户安装位置变化
//! ——静态写死只有两个选择：`**`（全盘放行）或者漏掉真实路径。这里改为
//! 启动时按解析出的产品根目录 + User_Data 递归放行（见 lib.rs 的 setup），
//! 用户从任意位置选进来的文件/目录（壁纸、转换的输入输出、训练数据集）
//! 在选择成功的那个命令里当场放行。
//!
//! 漏放行的症状是那张图/那段音频悄悄 404，界面不报错。所以以后新增
//! 「选一个文件/目录给界面显示或播放」的命令时，返回路径前必须顺手
//! grant 一行 —— 这也是这组函数存在的意义：让这一行足够好写。

use std::path::Path;

use tauri::AppHandle;

fn scope(app: &AppHandle) -> tauri::scope::fs::Scope {
    use tauri::Manager;
    app.asset_protocol_scope()
}

/// 递归放行一个目录。
pub fn grant_dir(app: &AppHandle, path: &Path) {
    let _ = scope(app).allow_directory(path, true);
}

/// 放行单个文件。空路径直接忽略（「清除壁纸」会写入空串）。
pub fn grant_file(app: &AppHandle, path: &str) {
    let p = path.trim();
    if p.is_empty() {
        return;
    }
    let _ = scope(app).allow_file(p);
}

/// 选择框结果按语义放行：目录递归，文件单放。
pub fn grant_picked(app: &AppHandle, path: &str, is_dir: bool) {
    if is_dir {
        grant_dir(app, Path::new(path));
    } else {
        grant_file(app, path);
    }
}
