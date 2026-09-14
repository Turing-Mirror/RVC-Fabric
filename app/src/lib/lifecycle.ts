/**
 * 组件装卸计数（C-01 验收依据）。测试和诊断用它核对「连续切页 N 次后，
 * 监听器/挂载数没有净增长」；生产路径只是两个 Map 加法，开销可忽略。
 */
const counts = new Map<string, { mounts: number; unmounts: number }>();

export function noteMount(name: string): void {
  const c = counts.get(name) || { mounts: 0, unmounts: 0 };
  c.mounts += 1;
  counts.set(name, c);
}

export function noteUnmount(name: string): void {
  const c = counts.get(name) || { mounts: 0, unmounts: 0 };
  c.unmounts += 1;
  counts.set(name, c);
}

export function mountCounts(): Map<string, { mounts: number; unmounts: number }> {
  return new Map(counts);
}

export function resetMountCounts(): void {
  counts.clear();
}
