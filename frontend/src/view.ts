export type ContentBounds = { minx: number; miny: number; w: number; h: number };
export type Size = { w: number; h: number };
export type View = { x: number; y: number; w: number; h: number };

export function fitView(content: ContentBounds, viewport: Size, padding = 0.08): View {
  const cw = content.w || 1;
  const ch = content.h || 1;
  const aspect = (viewport.w || 1) / (viewport.h || 1);
  let vw: number;
  let vh: number;
  if (cw / ch > aspect) {
    vw = cw * (1 + padding);
    vh = vw / aspect;
  } else {
    vh = ch * (1 + padding);
    vw = vh * aspect;
  }
  const cx = content.minx + cw / 2;
  const cy = content.miny + ch / 2;
  return { x: cx - vw / 2, y: cy - vh / 2, w: vw, h: vh };
}

export function zoomView(view: View, factor: number, worldX: number, worldY: number): View {
  const f = factor > 0 ? factor : 1;
  const w = view.w / f;
  const h = view.h / f;
  const rx = view.w ? (worldX - view.x) / view.w : 0.5;
  const ry = view.h ? (worldY - view.y) / view.h : 0.5;
  return { x: worldX - rx * w, y: worldY - ry * h, w, h };
}

export function panView(view: View, dxWorld: number, dyWorld: number): View {
  return { ...view, x: view.x - dxWorld, y: view.y - dyWorld };
}

export function screenToWorld(view: View, viewport: Size, screenX: number, screenY: number) {
  return {
    x: view.x + (screenX / (viewport.w || 1)) * view.w,
    y: view.y + (screenY / (viewport.h || 1)) * view.h,
  };
}
