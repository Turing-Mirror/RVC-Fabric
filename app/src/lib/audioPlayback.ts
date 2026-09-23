export type PlaybackStatus = {
  state: "idle" | "playing" | "paused" | "ended" | "error";
  name: string;
  played_frames: number;
  length_frames: number;
  sample_rate: number;
};

export type VoicePlaybackStatus = PlaybackStatus & {
  instance_id: number | null;
  active_count: number;
};

export function playbackActive(status: PlaybackStatus | null): boolean {
  return status?.state === "playing" || status?.state === "paused";
}

export function playbackClock(frames: number, sampleRate: number): string {
  const seconds = Math.max(0, Math.floor(frames / Math.max(1, sampleRate)));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}
