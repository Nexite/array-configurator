import { describe, expect, it } from "vitest";
import { unsupportedImportMessage } from "./routing";

describe("import formats", () => {
  it("rejects PDF, AI, EPS, and DWG", () => {
    for (const name of ["shell.PDF", "shell.ai", "shell.eps", "shell.dwg"]) {
      expect(unsupportedImportMessage(name)).toMatch(/DXF, SVG, or HPGL/);
    }
  });

  it("accepts DXF, SVG, and HPGL", () => {
    expect(unsupportedImportMessage("TOPSHELL.DXF")).toBeNull();
    expect(unsupportedImportMessage("rectangle.svg")).toBeNull();
    expect(unsupportedImportMessage("plot.hpgl")).toBeNull();
    expect(unsupportedImportMessage("plot.plt")).toBeNull();
  });
});
