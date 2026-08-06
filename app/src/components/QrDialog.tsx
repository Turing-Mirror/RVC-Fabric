import { useEffect } from "react";

/**
 * 一张二维码，铺在一层半透明底上。
 *
 * QQ 群没有「点开就能加群」的桌面端地址 —— 那种链接在电脑上只会跳去下载 QQ。
 * 所以这条社媒不跳外链，就把码摆出来让用户拿手机扫。图里已经写着群名和群号，
 * 这里不再重复一遍。
 *
 * 关掉的方式和「其他 → 下载模型」那个弹窗一致：点空白处、按 Esc。
 */
export function QrDialog({
  src,
  label,
  onClose,
}: {
  src: string;
  label: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[90] grid place-items-center p-6 bg-[color-mix(in_srgb,var(--ink)_28%,transparent)]"
      onClick={onClose}
    >
      <div
        className="rounded-[var(--r)] bg-[var(--surface)] p-4 shadow-[0_20px_60px_rgba(0,0,0,0.22)]"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={src}
          alt={label}
          draggable={false}
          // 高度跟着视口收，窄窗口下也不会被裁掉一半。
          className="block h-auto max-h-[min(70vh,560px)] w-auto max-w-[min(420px,80vw)] select-none rounded-[var(--rs)]"
        />
      </div>
    </div>
  );
}
