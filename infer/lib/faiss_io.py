# -*- coding: utf-8 -*-
"""faiss 索引的读写入口，中文路径也能用。

faiss 的 C++ 侧用 fopen 打开文件。中文 Windows 上，路径里一旦有非 ASCII
字符（「新建文件夹(2)」「伊蕾娜」这种），``faiss.read_index`` 就
``Illegal byte sequence``。但这条限制只长在「拿路径打开文件」这一步上：
索引文件本身就是一段序列化字节，Python 的 ``open`` 读中文路径毫无压力，
读进来交给 ``faiss.deserialize_index`` 就得到同一个索引对象。写侧同理
（``serialize_index`` 再落盘）。所以这里不报错、也不拷临时目录 —— 把这条
限制正面解除（diag 26.8.29/103223：音色叫「伊蕾娜」的用户被纯 ASCII 守卫
挡在开启变声之外，而他的检索库根本是空的）。

ASCII 路径仍走 faiss 原生接口，行为与直接调 faiss 一致。
"""

from __future__ import annotations


def is_ascii_path(path: str) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def read_index(path):
    """faiss.read_index；非 ASCII 路径走字节反序列化。"""
    import faiss

    if is_ascii_path(path):
        return faiss.read_index(path)
    import numpy as np

    with open(path, "rb") as f:
        data = f.read()
    return faiss.deserialize_index(np.frombuffer(data, dtype=np.uint8))


def write_index(index, path) -> None:
    """faiss.write_index；非 ASCII 路径先序列化再落盘。"""
    import faiss

    if is_ascii_path(path):
        faiss.write_index(index, path)
        return
    import numpy as np

    data = faiss.serialize_index(index)
    with open(path, "wb") as f:
        f.write(data.tobytes())
