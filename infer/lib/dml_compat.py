# -*- coding: utf-8 -*-
"""DirectML（``privateuseone``）后端上要提前打的补丁，各条推理路径共用。

AMD / Intel 版走的是 torch-directml，设备字符串是 ``privateuseone:0``。这个
后端只实现了常用算子的一部分，落在缺口上的调用会当场抛 RuntimeError，而不是
悄悄退回 CPU。目前踩到的有两处：

* **fairseq 的 GradMultiply**。``x.new(x)`` 在 DirectML 上不认账::

      File "fairseq/modules/grad_multiply.py", line 13, in forward
        res = x.new(x)
      RuntimeError: new(): expected key in DispatchKeySet(CPU, CUDA, HIP, ...)
                    but got: PrivateUse1

  hubert 的 ``feature_grad_mult`` 是 0.1，只要不是 1.0 就会走进 GradMultiply，
  所以 A 卡上每一次特征提取都必炸。换成 ``x.clone().detach()`` 结果完全一样：
  这条路只做推理，反向的那点缩放没人用。

* **torchcrepe 的权重加载**。它内部是 ``torch.load(file, map_location=device)``，
  而 torch 的反序列化不认识 privateuseone 标签::

      RuntimeError: don't know how to restore data location of
                    torch.storage.UntypedStorage (tagged with privateuseone:0)

补丁本身早就有，问题出在入口漏打：实时（``rtrvc``）和训练特征提取
（``extract_feature_print``）各自写过一份，离线文件转换的 ``load_hubert``
一直没打（26.8.20，A 卡 8 次「语音转换」全挂）。文字合成第二步走的是另一条
冷路径 ``tools/infer_cli.py``，不经过 sts_worker，连 CPU 兜底都没有 ——
26.8.21 的 TTS 日志就是 SAPI 念完之后整次换音色挂在 GradMultiply 上。

所以这里收成一份，谁要用谁调，别再各写各的。本模块**不导入 torch，也不导入
fairseq**，只在真的要打补丁时才现拿 —— 开发机和 CI 上这两个包都没有。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def is_dml_device(device) -> bool:
    """设备字符串是不是 DirectML。``torch.device`` 和纯字符串都能认。"""
    return "privateuseone" in str(device or "").lower()


def index_dtype(device):
    """音高 / 长度这类索引张量用的整数类型。

    DirectML 对 int64（``torch.long``）支持很差：``torch.zeros(..., dtype=long)``
    在 ``privateuseone`` 上会抛**空消息**的 ``RuntimeError``（diag 26.9.6）。
    改用 int32，Embedding 索引和 ``net_g.infer`` 都认。
    """
    import torch

    return torch.int32 if is_dml_device(device) else torch.long


def wants_dml(config) -> bool:
    """这份配置跑不跑 DirectML。

    先看 ``config.dml``（``configs/config.py`` 按 ``--dml`` / ``TM_ACCEL`` 定的），
    再看设备字符串兜底：DirectML 初始化失败时 config 会把设备退回 cpu，那种情况
    下 ``dml`` 仍是 True，但补丁打了也无害；反过来有些调用方只传得出设备。
    """
    if config is None:
        return False
    if bool(getattr(config, "dml", False)):
        return True
    return is_dml_device(getattr(config, "device", ""))


def _forward_dml(ctx, x, scale):
    ctx.scale = scale
    return x.clone().detach()


_forward_dml._tm_dml_patch = True  # 幂等标记，见 patch_fairseq_grad_multiply


def patch_fairseq_grad_multiply(fairseq_module=None) -> bool:
    """把 ``GradMultiply.forward`` 换成 DirectML 认识的写法。

    返回是否已就位。fairseq 没装（开发机 / CI）或结构对不上就返回 False，不抛：
    调用方都是「顺手打一下」的位置，真缺依赖会在后面加载模型时报得更清楚。

    ``fairseq_module`` 只给测试用，正常调用不传。
    """
    mod = fairseq_module
    if mod is None:
        try:
            import fairseq  # noqa: F401

            mod = fairseq
        except Exception:
            logger.debug("fairseq not importable; skip DirectML GradMultiply patch")
            return False
    try:
        grad_multiply = mod.modules.grad_multiply.GradMultiply
    except Exception:
        logger.warning("fairseq.modules.grad_multiply.GradMultiply not found; skip patch")
        return False
    if getattr(grad_multiply.forward, "_tm_dml_patch", False):
        return True
    grad_multiply.forward = _forward_dml
    logger.info("DirectML: patched fairseq GradMultiply.forward")
    return True


def apply_for(config, *, fairseq_module=None) -> bool:
    """非 DirectML 配置原样返回 False，是的话把补丁打上。"""
    if not wants_dml(config):
        return False
    return patch_fairseq_grad_multiply(fairseq_module)


def crepe_device(device):
    """crepe 该在哪块设备上跑。

    DirectML 上退回 CPU：torchcrepe 一上来就 ``torch.load(map_location=device)``，
    privateuseone 直接反序列化失败，连模型都装不起来。实时路径不能这么退（CPU
    crepe 慢到跟不上流，那边改用 fcpe），但离线转换宁可慢也得出结果。
    """
    return "cpu" if is_dml_device(device) else device
