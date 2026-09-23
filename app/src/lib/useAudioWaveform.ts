import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type Waveform = { duration: number; peaks: number[] };
type WaveformState = Waveform & { loading: boolean; error: boolean };
type StoredWaveform = WaveformState & { input: string | null };

let nextRequest = 0;
const EMPTY: WaveformState = { duration: 0, peaks: [], loading: false, error: false };

/** Native FFmpeg extraction keeps long source files out of WebView memory. */
export function useAudioWaveform(input: string | null): WaveformState {
  const [state, setState] = useState<StoredWaveform>({ ...EMPTY, input: null });
  useEffect(() => {
    if (!input) {
      setState({ ...EMPTY, input: null });
      return;
    }
    let active = true;
    const requestId = `wave-${Date.now()}-${++nextRequest}`;
    setState({ ...EMPTY, input, loading: true });
    void invoke<Waveform>("audio_waveform_get", { input, requestId })
      .then((waveform) => {
        if (active) setState({ ...waveform, input, loading: false, error: false });
      })
      .catch(() => {
        if (active) setState({ ...EMPTY, input, error: true });
      });
    return () => {
      active = false;
      void invoke("audio_waveform_cancel", { requestId }).catch(() => undefined);
    };
  }, [input]);
  return state.input === input ? state : { ...EMPTY, loading: Boolean(input) };
}
