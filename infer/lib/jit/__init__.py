from io import BytesIO
import pickle
import time
import torch
from tqdm import tqdm
from collections import OrderedDict

from infer.lib.safe_load import safe_torch_load


def load_inputs(path, device, is_half=False):
    parm = safe_torch_load(path, map_location=torch.device("cpu"))
    for key in parm.keys():
        parm[key] = parm[key].to(device)
        if is_half and parm[key].dtype == torch.float32:
            parm[key] = parm[key].half()
        elif not is_half and parm[key].dtype == torch.float16:
            parm[key] = parm[key].float()
    return parm


def benchmark(
    model, inputs_path, device=torch.device("cpu"), epoch=1000, is_half=False
):
    parm = load_inputs(inputs_path, device, is_half)
    total_ts = 0.0
    bar = tqdm(range(epoch))
    for i in bar:
        start_time = time.perf_counter()
        o = model(**parm)
        total_ts += time.perf_counter() - start_time
    print(f"num_epoch: {epoch} | avg time(ms): {(total_ts*1000)/epoch}")


def jit_warm_up(model, inputs_path, device=torch.device("cpu"), epoch=5, is_half=False):
    benchmark(model, inputs_path, device, epoch=epoch, is_half=is_half)


def to_jit_model(
    model_path,
    model_type: str,
    mode: str = "trace",
    inputs_path: str = None,
    device=torch.device("cpu"),
    is_half=False,
):
    model = None
    if model_type.lower() == "synthesizer":
        from .get_synthesizer import get_synthesizer

        model, _ = get_synthesizer(model_path, device)
        model.forward = model.infer
    elif model_type.lower() == "rmvpe":
        from .get_rmvpe import get_rmvpe

        model = get_rmvpe(model_path, device)
    elif model_type.lower() == "hubert":
        from .get_hubert import get_hubert_model

        model = get_hubert_model(model_path, device)
        model.forward = model.infer
    else:
        raise ValueError(f"No model type named {model_type}")
    model = model.eval()
    model = model.half() if is_half else model.float()
    if mode == "trace":
        assert not inputs_path
        inputs = load_inputs(inputs_path, device, is_half)
        model_jit = torch.jit.trace(model, example_kwarg_inputs=inputs)
    elif mode == "script":
        model_jit = torch.jit.script(model)
    model_jit.to(device)
    model_jit = model_jit.half() if is_half else model_jit.float()
    # model = model.half() if is_half else model.float()
    return (model, model_jit)


def export(
    model: torch.nn.Module,
    mode: str = "trace",
    inputs: dict = None,
    device=torch.device("cpu"),
    is_half: bool = False,
) -> dict:
    model = model.half() if is_half else model.float()
    model.eval()
    if mode == "trace":
        assert inputs is not None
        model_jit = torch.jit.trace(model, example_kwarg_inputs=inputs)
    elif mode == "script":
        model_jit = torch.jit.script(model)
    model_jit.to(device)
    model_jit = model_jit.half() if is_half else model_jit.float()
    buffer = BytesIO()
    # model_jit=model_jit.cpu()
    torch.jit.save(model_jit, buffer)
    del model_jit
    cpt = OrderedDict()
    cpt["model"] = buffer.getvalue()
    cpt["is_half"] = is_half
    return cpt


class _JitUnpickler(pickle.Unpickler):
    """.jit 旁车文件里只需要容器、标量和 torch.device。

    裸 pickle.load 等于给文件任意代码执行权：.jit 跟 .pth 放在同一目录，
    用户换音色模型时一起被带进来。只允许这几个全局量，其它一律拒读；
    拒读后调用方会重新从 .pth 导一份，等于自愈。
    """

    _ALLOWED = {
        ("collections", "OrderedDict"),
        ("torch", "device"),
        ("torch._C", "device"),
        ("torch", "dtype"),
        ("torch", "float16"),
        ("torch", "float32"),
        ("torch", "float64"),
        ("torch", "int64"),
        ("torch", "int32"),
    }

    def find_class(self, module, name):
        if (module, name) in self._ALLOWED:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"refusing to unpickle {module}.{name} from .jit file"
        )


def load(path: str):
    with open(path, "rb") as f:
        return _JitUnpickler(f).load()


def save(ckpt: dict, save_path: str):
    with open(save_path, "wb") as f:
        pickle.dump(ckpt, f)


def rmvpe_jit_export(
    model_path: str,
    mode: str = "script",
    inputs_path: str = None,
    save_path: str = None,
    device=torch.device("cpu"),
    is_half=False,
):
    if not save_path:
        save_path = model_path.rstrip(".pth")
        save_path += ".half.jit" if is_half else ".jit"
    if "cuda" in str(device) and ":" not in str(device):
        device = torch.device("cuda:0")
    from .get_rmvpe import get_rmvpe

    model = get_rmvpe(model_path, device)
    inputs = None
    if mode == "trace":
        inputs = load_inputs(inputs_path, device, is_half)
    ckpt = export(model, mode, inputs, device, is_half)
    ckpt["device"] = str(device)
    save(ckpt, save_path)
    return ckpt


def synthesizer_jit_export(
    model_path: str,
    mode: str = "script",
    inputs_path: str = None,
    save_path: str = None,
    device=torch.device("cpu"),
    is_half=False,
):
    if not save_path:
        save_path = model_path.rstrip(".pth")
        save_path += ".half.jit" if is_half else ".jit"
    if "cuda" in str(device) and ":" not in str(device):
        device = torch.device("cuda:0")
    from .get_synthesizer import get_synthesizer

    model, cpt = get_synthesizer(model_path, device)
    assert isinstance(cpt, dict)
    model.forward = model.infer
    inputs = None
    if mode == "trace":
        inputs = load_inputs(inputs_path, device, is_half)
    ckpt = export(model, mode, inputs, device, is_half)
    cpt.pop("weight")
    cpt["model"] = ckpt["model"]
    cpt["device"] = device
    save(cpt, save_path)
    return cpt
