import os


def get_index_path_from_model(sid):
    """Find a matching .index under index_root for the given model id/path.

    Product workers (STS / TTS / offline CLI) may run without a dotenv-loaded
    ``index_root`` (installed packs historically omitted ``.env``). Never pass
    ``None`` to ``os.walk`` — return empty string so callers keep working and
    can rely on an explicit index path from config instead.
    """
    index_root = os.getenv("index_root") or ""
    if not index_root or not os.path.isdir(index_root):
        return ""

    # Absolute catalog paths: match on the model stem, not the drive letter path.
    key = os.path.splitext(os.path.basename(str(sid or "")))[0]
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

    models, _, _ = checkpoint_utils.load_model_ensemble_and_task(
        ["assets/hubert/hubert_base.pt"],
        suffix="",
    )
    hubert_model = models[0]
    hubert_model = hubert_model.to(config.device)
    if config.is_half:
        hubert_model = hubert_model.half()
    else:
        hubert_model = hubert_model.float()
    return hubert_model.eval()
