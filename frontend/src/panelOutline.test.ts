import { describe, expect, it } from "vitest";
import { panelOutlineEdges } from "./panelOutline";

describe("panelOutlineEdges", () => {
  it("omits the shared edge of a 1×2 panel", () => {
    const edges = panelOutlineEdges([
      [0, 0],
      [1, 0],
    ]);
    expect(edges.some((e) => e.i === 0 && e.j === 0 && e.from === 1 && e.to === 2)).toBe(false);
    expect(edges.some((e) => e.i === 1 && e.j === 0 && e.from === 3 && e.to === 0)).toBe(false);
    expect(edges).toHaveLength(6);
  });

  it("keeps all four sides of a single cell", () => {
    expect(panelOutlineEdges([[0, 0]])).toHaveLength(4);
  });
});
