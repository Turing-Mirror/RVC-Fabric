import platform, os
import ffmpeg
import numpy as np
import av
from io import BytesIO
import traceback
import re


def wav2(i, o, format):
    inp = av.open(i, "rb")
    if format == "m4a":
        format = "mp4"
    out = av.open(o, "wb", format=format)
    if format == "ogg":
        format = "libvorbis"
    if format == "mp4":
        format = "aac"

    ostream = out.add_stream(format)

    for frame in inp.decode(audio=0):
        for p in ostream.encode(frame):
            out.mux(p)

    for p in ostream.encode(None):
        out.mux(p)

    out.close()
    inp.close()


def load_audio(file, sr):
    try:
        # https://github.com/openai/whisper/blob/main/whisper/audio.py#L26
        # This launches a subprocess to decode audio while down-mixing and resampling as necessary.
        # Requires the ffmpeg CLI and `ffmpeg-python` package to be installed.
        file = clean_path(file)  # 防止小白拷路径头尾带了空格和"和回车
        if os.path.exists(file) == False:
            raise RuntimeError(
                "You input a wrong audio path that does not exists, please fix it!"
            )
        # ffmpeg-python 的 run() 不认 creationflags（那是 Popen 的参数）。
        # Windows 藏黑框走 worker_protocol.hide_console_subprocesses 打的 Popen 补丁。
        out, _ = (
            ffmpeg.input(file, threads=0)
            .output("-", format="f32le", acodec="pcm_f32le", ac=1, ar=sr)
            .run(cmd=["ffmpeg", "-nostdin"], capture_stdout=True, capture_stderr=True)
        )
    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(f"Failed to load audio: {e}")

    return np.frombuffer(out, np.float32).flatten()



def clean_path(path_str):
    if path_str is None:
        raise ValueError("audio path is empty")
    path_str = str(path_str)
    if platform.system() == "Windows":
        path_str = path_str.replace("/", "\\")
    # Strip bidi / zero-width control characters often pasted from chat apps
    path_str = re.sub(
        r"[\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff]",
        "",
        path_str,
    )
    return path_str.strip(" ").strip('"').strip("\n").strip("'").strip(" ")
