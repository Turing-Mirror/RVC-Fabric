/**
 * 试听：让用户当场听一下这个音色像不像。
 *
 * 训完 500 轮才发现不像，是这个产品里最贵的一种失望。而「像不像」只有他自己
 * 能判断，我们能做的就是把这一步从「导出、找文件、拖进播放器」缩成一个按钮。
 *
 * 不额外附带样音：产品自带的 SAPI 朗读 + 离线换声本来就能凑出一段人声，省掉
 * 一份要考虑体积和授权的内置音频，念的那句话还能跟着界面语言走。
 */
import { convertFileSrc, invoke } from "@tauri-apps/api/core";

let player: HTMLAudioElement | null = null;

/** 合成并播放一段试听。返回错误文本，成功返回空串。 */
export async function auditionVoice(modelPath: string): Promise<string> {
  try {
    const r = await invoke<{ file?: string }>("voice_audition", {
      modelPath,
      voice: null,
    });
    const file = r?.file;
    if (!file) return "";
    // 上一段还在放就掐掉：连点两下不该变成两个声音叠在一起。
    if (player) {
      player.pause();
    }
    player = player ?? new Audio();
    player.src = convertFileSrc(file);
    await player.play();
    return "";
  } catch (e) {
    return String(e);
  }
}

export function stopAudition(): void {
  player?.pause();
}
