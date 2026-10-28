import { describe, expect, it } from "vitest";
import { shellAreaM2 } from "./shellArea";
import type { Region } from "./types";

function region(over: Partial<Region> & Pick<Region, "points">): Region {
  return { id: "r", kind: "populate", source: "detected", ...over };
}

describe("shellAreaM2", () => {
  it("converts the imported outline from mm² to m²", () => {
    const square = region({
      points: [
        [0, 0],
        [1000, 0],
        [1000, 1000],
        [0, 1000],
      ],
    });
    expect(shellAreaM2([square])).toBeCloseTo(1);
  });

  it("subtracts detected cutouts inside the outline", () => {
    const outer = region({
      id: "outer",
      points: [
        [0, 0],
        [1000, 0],
        [1000, 1000],
        [0, 1000],
        [0, 0],
      ],
    });
    const hole = region({
      id: "hole",
      kind: "keep_out",
      points: [
        [100, 100],
        [300, 100],
        [300, 300],
        [100, 300],
      ],
    });
    expect(shellAreaM2([hole, outer])).toBeCloseTo(0.96);
  });

  it("ignores regions drawn after import", () => {
    const shell = region({
      points: [
        [0, 0],
        [500, 0],
        [500, 500],
        [0, 500],
      ],
    });
    const drawn = region({
      id: "d0",
      source: "drawn",
      kind: "keep_out",
      points: [
        [0, 0],
        [10000, 0],
        [10000, 10000],
        [0, 10000],
      ],
    });
    expect(shellAreaM2([shell, drawn])).toBeCloseTo(0.25);
  });

  it("is empty until a shell is imported", () => {
    expect(shellAreaM2([])).toBeNull();
  });
});
