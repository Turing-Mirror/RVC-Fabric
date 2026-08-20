# -*- coding: utf-8 -*-
"""faiss 读索引。路径必须是纯英文。

faiss 的 C++ 侧用 fopen 打开文件。中文 Windows 上，路径里一旦有非 ASCII
字符（「新建文件夹」这种），就会 ``Illegal byte sequence``。不要偷偷拷到
临时目录再读：用户看不见原因，下次换个音色还会再踩一次。直接告诉他们
换到纯英文文件夹。
"""

from __future__ import annotations


class NonAsciiPathError(OSError):
    """路径含非 ASCII 字符，faiss 读不了。"""


def is_ascii_path(path: str) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def require_ascii_path(path: str) -> None:
    if not path:
        return
    if is_ascii_path(path):
        return
    raise NonAsciiPathError(
        "路径含有中文或其他非英文字符，检索库无法读取。"
        "请把软件或音色移到纯英文文件夹（例如 D:\\RVCFabric）后再试。"
        f" 当前路径：{path}"
    )


def read_index(path):
    """faiss.read_index。非 ASCII 路径直接报错，不兜底拷贝。"""
    import faiss

    require_ascii_path(path)
    return faiss.read_index(path)
