fn main() {
    trm_app_protocol::codegen::generate(
        std::path::Path::new("src"),
        &std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap()),
    );
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows")
        && std::env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc")
    {
        // Same Common-Controls v6 dependency as Tauri's default manifest, but
        // also embedded in Rust test executables that exercise real windows.
        // tauri-build's resource manifest is otherwise linked only into bins.
        tauri_build::try_build(
            tauri_build::Attributes::new()
                .windows_attributes(tauri_build::WindowsAttributes::new_without_app_manifest()),
        )
        .expect("build Tauri resources");
        println!("cargo:rustc-link-arg=/MANIFEST:EMBED");
        println!("cargo:rustc-link-arg=/MANIFESTDEPENDENCY:type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'");
    } else {
        tauri_build::build();
    }
}
