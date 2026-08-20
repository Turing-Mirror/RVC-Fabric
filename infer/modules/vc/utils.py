import os


def product_root() -> str:
    """Install / repo root. Prefer TM_VOICE_ROOT (shell sets it); else cwd."""
    env = (os.environ.get("TM_VOICE_ROOT") or "").strip()
    if env and os.path.isdir(env):
        return env
    return os.getcwd()


def resolve_under_product(*parts: str) -> str:
    """Join relative asset paths under product root (absolute)."""
    return os.path.normpath(os.path.join(product_root(), *parts))


def get_index_path_from_model(sid):
    """Find a matching .index under index_root for the given model id/path.

    Product workers (STS / TTS / offline CLI) may run without a dotenv-loaded
    ``index_root`` (installed packs historically omitted ``.env``). Never pass
    ``None`` to ``os.walk`` — return empty string so callers keep working and
    can rely on an explicit index path from config instead.
    """
    index_root = os.getenv("index_root") or ""
    if index_root and not os.path.isabs(index_root):
        index_root = resolve_under_product(index_root)
    if not index_root or not os.path.isdir(index_root):
        return ""

    # Absolute catalog paths: match on the model stem, not the drive letter path.
    #
    # 分隔符自己切，不用 os.path.basename：非 Windows 上它不认反斜杠，
    # `F:\models\Anon\Anon-local.pth` 会被整条当成文件名，key 里带着盘符和
    # 目录，自然什么都匹配不上。产品只发 Windows，但 CI / 开发机是 POSIX，
    # 这条测试因此长期红着 —— 长期红的测试等于没有测试，大家会开始不看失败。
    raw = str(sid or "").replace("\\", "/")
    key = os.path.splitext(raw.rsplit("/", 1)[-1])[0]
    if not key:
        return ""

    return next(
        (
            f
            for f in [
                os.path.join(root, name)
                for root, _, files in os.walk(index_root, topdown=False)
                for name in files
                if name.endswith(".index") and "trained" not in name
            ]
            if key in f
        ),
        "",
    )


def load_hubert(config):
    from fairseq import checkpoint_utils

    from infer.lib.dml_compat import apply_for

    # A / I 卡（DirectML）上 hubert 的 GradMultiply 会当场抛 PrivateUse1，必须在
    # 推理前把补丁打上。实时和训练那两条路各自打过，唯独离线转换这条漏了，A 卡
    # 用户点「语音转换」于是必失败（26.8.20 诊断包）。细节见 infer/lib/dml_compat。
    apply_for(config)

    # Relative "assets/hubert/..." fails when cwd is not the product root, and
    # fairseq only says "Model file not found". Resolve under TM_VOICE_ROOT.
    path = resolve_under_product("assets", "hubert", "hubert_base.pt")
    if not os.path.isfile(path) or os.path.getsize(path) < 1_000_000:
        raise FileNotFoundError(
            f"找不到 hubert 模型（引擎资源未补全）：{path}\n"
            "请回到主界面完成「引擎资源」下载（hubert / rmvpe / ffmpeg）。"
        )
    models, _, _ = checkpoint_utils.load_model_ensemble_and_task(
        [path],
        suffix="",
    )
    hubert_model = models[0]
    hubert_model = hubert_model.to(config.device)
    if config.is_half:
        hubert_model = hubert_model.half()
    else:
        hubert_model = hubert_model.float()
    return hubert_model.eval()
