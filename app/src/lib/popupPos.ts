/** Button or trigger box in viewport coordinates. */
export type PopupAnchor = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export type PopupBox = {
  left: number;
  top: number;
  maxHeight: number;
};

/**
 * Place a fixed popup so its full contents stay on screen.
 *
 * Right edges line up with the trigger. If there is not enough room below,
 * the menu opens above. If it is still taller than the window, it gets a
 * max height and scrolls inside.
 */
export function placePopup(
  anchor: PopupAnchor,
  size: { width: number; height: number },
  view: { width: number; height: number },
  pad = 8,
): PopupBox {
  const vw = Math.max(0, view.width);
  const vh = Math.max(0, view.height);
  const maxHeight = Math.max(80, vh - pad * 2);
  const width = Math.max(1, size.width);
  const height = Math.min(Math.max(1, size.height), maxHeight);

  let left = anchor.right - width;
  left = Math.max(pad, Math.min(left, vw - width - pad));
  if (width + pad * 2 > vw) left = pad;

  let top = anchor.bottom + 6;
  if (top + height > vh - pad) {
    const above = anchor.top - 6 - height;
    top = above >= pad ? above : Math.max(pad, vh - height - pad);
  }
  if (top < pad) top = pad;
  return { left, top, maxHeight };
}
