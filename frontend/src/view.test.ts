import { describe, expect, it } from "vitest";
import { fitView, panView, screenToWorld, zoomView } from "./view";

describe("fitView", () => {
  it("fits the whole content and centers it in the viewport", () => {
    const view = fitView({ minx: 100, miny: 200, w: 400, h: 200 }, { w: 800, h: 400 }, 0);
    expect(view.w / view.h).toBeCloseTo(2);
    expect(view.x + view.w / 2).toBeCloseTo(300);
    expect(view.y + view.h / 2).toBeCloseTo(300);
    expect(view.w).toBeGreaterThanOrEqual(400);
    expect(view.h).toBeGreaterThanOrEqual(200);
  });

  it("adds padding around a tall outline in a wide viewport", () => {
    const view = fitView({ minx: 0, miny: 0, w: 100, h: 400 }, { w: 800, h: 400 }, 0.1);
    expect(view.x + view.w / 2).toBeCloseTo(50);
    expect(view.y + view.h / 2).toBeCloseTo(200);
    expect(view.h).toBeGreaterThan(400);
    expect(view.w / view.h).toBeCloseTo(2);
  });
});

describe("zoomView", () => {
  it("keeps the world point under the cursor fixed", () => {
    const view = { x: 0, y: 0, w: 200, h: 100 };
    const next = zoomView(view, 2, 50, 25);
    expect(next.w).toBeCloseTo(100);
    expect(next.h).toBeCloseTo(50);
    expect(screenToWorld(next, { w: 200, h: 100 }, 50, 25)).toEqual({ x: 50, y: 25 });
  });
});

describe("panView", () => {
  it("moves the view opposite the drag so content follows the pointer", () => {
    const view = { x: 10, y: 20, w: 100, h: 50 };
    expect(panView(view, 5, -3)).toEqual({ x: 5, y: 23, w: 100, h: 50 });
  });
});
