// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // 安装程序换安装位置时调用，搬完就退出，不启动界面。
    if let Some(code) = app_lib::install_move::from_args() {
        std::process::exit(code);
    }
    app_lib::run()
}
