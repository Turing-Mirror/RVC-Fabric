from importlib import import_module
import sys

_LOCAL_MODULE_PREFIX = "pymss.modules."
_CORE_MODULE_PREFIX = "pymss_core.modules."


def _as_pymss_module(name):
    """``tools.pymss…`` is the same files imported from the product root.

    VR 的 uvr_lib_v5 用 ``__name__`` 做别名。worker 若走 ``import tools.pymss``，
    这里会变成 ``tools.pymss.modules.…``，3.9 上直接 ValueError，HP3/HP4 过不了。
    """
    if name.startswith("tools."):
        return name[len("tools.") :]
    return name


def alias_module(local_name, core_name):
    local_name = _as_pymss_module(local_name)
    if not local_name.startswith(_LOCAL_MODULE_PREFIX):
        raise ValueError(f"invalid local module alias: {local_name}")
    if not core_name.startswith(_CORE_MODULE_PREFIX):
        raise ValueError(f"invalid core module alias: {core_name}")
    module = import_module(core_name)
    sys.modules[local_name] = module
    return module


def alias_submodules(local_package, core_package, names):
    local_package = _as_pymss_module(local_package)
    for name in names:
        alias_module(f"{local_package}.{name}", f"{core_package}.{name}")
