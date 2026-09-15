export type NearRect = {
  left: number;
  top: number;
  width: number;
  height: number;
  bottom?: number;
};

export type NearSize = {
  width: number;
  height: number;
};

export function placeFixedNearRect(
  rect: NearRect,
  size: NearSize,
  options?: {
    preferBelow?: boolean;
    pad?: number;
    viewport?: { width: number; height: number };
  },
): { left: number; top: number } {
  const pad = options?.pad ?? 8;
  const preferBelow = options?.preferBelow ?? true;
  const vw = options?.viewport?.width ?? (typeof window !== "undefined" ? window.innerWidth : 800);
  const vh = options?.viewport?.height ?? (typeof window !== "undefined" ? window.innerHeight : 600);
  const w = size.width || 80;
  const h = size.height || 32;
  const bottom = rect.bottom ?? rect.top + rect.height;

  let left = rect.left + rect.width / 2 - w / 2;
  left = Math.max(pad, Math.min(left, vw - w - pad));

  let top: number;
  if (preferBelow) {
    top = bottom + pad;
    if (top + h > vh - pad) top = rect.top - h - pad;
  } else {
    top = rect.top - h - pad;
    if (top < pad) top = bottom + pad;
  }
  top = Math.max(pad, Math.min(top, vh - h - pad));
  return { left: Math.round(left), top: Math.round(top) };
}
