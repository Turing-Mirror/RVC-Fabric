fn main() {
    let portable = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.join("RVC Fabric.exe")))
        .is_some_and(|p| p.is_file());
    let executable = if cfg!(windows) {
        if portable {
            "RVC Fabric.exe"
        } else {
            "rvc-fabric.exe"
        }
    } else {
        "rvc-fabric"
    };
    if let Err(error) = trm_app_protocol::mcp::run("com.turingmirror.rvcfabric", executable) {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
