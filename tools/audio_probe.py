# -*- coding: utf-8 -*-
"""在独立进程里试一次音频设备枚举。

`sounddevice` 一被 import 就会调 `Pa_Initialize`，PortAudio 在那一步会把注册表
里注册的每个 ASIO 驱动都加载起来问参数。驱动有缺陷时整个进程当场没了，没有
Python 异常可捕获 —— 26.8.21 那份诊断包里是 Realtek 的 rthdasio64.dll 整数除零
（0xC0000094），变声引擎连着九次死在这一步，日志里一个字都没有。

主进程躲不开这次枚举（引擎本身要用音频），但可以先派一个只有 sounddevice、
没有 torch 的小进程去踩一遍：它死了就说明引擎也会死，于是能在开火之前把话说
清楚，而不是让用户对着一根停住的进度条点第九次。

用法（结果写文件，因为 pythonw 没有 stdout）::

    Runtime\\pythonw.exe tools\\audio_probe.py <输出 json 路径>

退出码 0 = 枚举成功，结果已写入；其余一律视为这台机器上的音频枚举不可用。
"""

from __future__ import annotations

import json
import sys


def probe() -> dict:
    import sounddevice as sd

    # 和 gui_v1.update_devices 走同一套：先 terminate 再 initialize，
    # 否则探到的是 import 时那一次的缓存，复现不了真正的失败点。
    sd._terminate()
    sd._initialize()
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()

    api_of = {}
    for api in hostapis:
        for idx in api["devices"]:
            api_of[idx] = api["name"]

    inputs = []
    outputs = []
    for d in devices:
        name = d.get("name") or ""
        api = api_of.get(d.get("index"), "")
        if d.get("max_input_channels", 0) > 0:
            inputs.append({"name": name, "hostapi": api})
        if d.get("max_output_channels", 0) > 0:
            outputs.append({"name": name, "hostapi": api})

    return {
        "ok": True,
        "hostapis": [a["name"] for a in hostapis],
        "inputs": inputs,
        "outputs": outputs,
    }


def main() -> int:
    if len(sys.argv) < 2:
        return 2
    out_path = sys.argv[1]
    try:
        result = probe()
    except BaseException as e:  # noqa: BLE001 - 报告即可，别把栈丢给用户
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception:
        return 3
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
