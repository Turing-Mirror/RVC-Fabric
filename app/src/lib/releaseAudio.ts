/** Release the media resource before deleting, replacing or abandoning its file. */
export function releaseAudio(audio: HTMLAudioElement | null): void {
  if (!audio) return;
  audio.onended = null;
  audio.onerror = null;
  audio.onloadedmetadata = null;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
}
