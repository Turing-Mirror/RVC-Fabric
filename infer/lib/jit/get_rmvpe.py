import torch

from infer.lib.safe_load import safe_torch_load


def get_rmvpe(model_path="assets/rmvpe/rmvpe.pt", device=torch.device("cpu")):
    from infer.lib.rmvpe import E2E

    model = E2E(4, 1, (2, 2))
    ckpt = safe_torch_load(model_path, map_location=device)
    model.load_state_dict(ckpt)
    model.eval()
    model = model.to(device)
    return model
