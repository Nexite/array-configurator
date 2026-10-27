import { useMemo, useState } from "react";
import { exportFile, importFile, loadSample, pack, validate } from "./api";
import {
  addDrawnRegion,
  confirmReplace,
  cycleRegion,
  deletePanel,
  initialState,
  loadRegions,
  movePanel,
  redo,
  resizeBound,
  selectGallery,
  setLayouts,
  toggleCell,
  undo,
  type AppState,
} from "./state/store";
import { type Issue, type LayoutParams, type Panel } from "./types";

function num(v: string, fallback: number) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function cellPoly(p: Panel, i: number, j: number, params: LayoutParams) {
  const px = params.cell_w_mm + params.cell_gap_mm;
  const py = params.cell_h_mm + params.cell_gap_mm;
  const rad = (p.angle_deg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  const corners: [number, number][] = [
    [i * px, j * py],
    [i * px + params.cell_w_mm, j * py],
    [i * px + params.cell_w_mm, j * py + params.cell_h_mm],
    [i * px, j * py + params.cell_h_mm],
  ];
  return corners.map(([x, y]) => [p.origin[0] + x * c - y * s, p.origin[1] + x * s + y * c] as [number, number]);
}

export function App() {
  const [s, setS] = useState<AppState>(initialState);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [drawMode, setDrawMode] = useState(false);
  const [draft, setDraft] = useState<[number, number][]>([]);

  const params = s.params;
  const bounds = useMemo(() => {
    const pts = s.regions.flatMap((r) => r.points);
    if (!pts.length) return { minx: 0, miny: 0, w: 100, h: 100 };
    const xs = pts.map((p) => p[0]);
    const ys = pts.map((p) => p[1]);
    const minx = Math.min(...xs);
    const miny = Math.min(...ys);
    return { minx, miny, w: Math.max(...xs) - minx || 1, h: Math.max(...ys) - miny || 1 };
  }, [s.regions]);

  async function refreshIssues(state: AppState) {
    if (!state.active) return setIssues([]);
    try {
      const r = await validate(state.regions, state.params, state.active.panels);
      setIssues(r.issues);
    } catch {
      setIssues([]);
    }
  }

  function setParam<K extends keyof LayoutParams>(k: K, v: LayoutParams[K]) {
    setS((prev) => ({ ...prev, params: { ...prev.params, [k]: v } }));
  }

  async function onSample() {
    setErr("");
    const r = await loadSample();
    setS((prev) => loadRegions(prev, r.regions));
  }

  async function onUpload(f: File) {
    setErr("");
    try {
      const r = await importFile(f, params.unit_scale);
      setS((prev) => loadRegions(prev, r.regions));
    } catch (e) {
      setErr(String(e));
    }
  }

  async function onGenerate() {
    setBusy(true);
    setErr("");
    try {
      if (s.dirty && !confirm("Replace the edited layout?")) return;
      const r = await pack(s.regions, s.params);
      const next = setLayouts(s, r.layouts);
      setS(next);
      await refreshIssues(next);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onExport(fmt: "svg" | "dxf" | "json") {
    if (!s.active) return;
    const blob = await exportFile(fmt, s.regions, s.params, s.active.panels);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `layout.${fmt}`;
    a.click();
  }

  const score = s.active?.score;

  return (
    <div className="app">
      <aside>
        <h1>Array Configurator</h1>
        <button onClick={onSample}>Load TOPSHELL sample</button>
        <label>
          Upload
          <input type="file" onChange={(e) => e.target.files && onUpload(e.target.files[0])} />
        </label>
        <label>
          Unit scale
          <input type="number" step="0.01" value={params.unit_scale} onChange={(e) => setParam("unit_scale", num(e.target.value, 1))} />
        </label>
        <h2>Cell footprint (pack)</h2>
        <label>
          Width mm
          <input type="number" value={params.cell_w_mm} onChange={(e) => setParam("cell_w_mm", num(e.target.value, 125))} />
        </label>
        <label>
          Height mm
          <input type="number" value={params.cell_h_mm} onChange={(e) => setParam("cell_h_mm", num(e.target.value, 125))} />
        </label>
        <h2>Usable / active area</h2>
        <p className="hint">Counts toward the target. Can be smaller than the footprint.</p>
        <label>
          Active W mm
          <input type="number" value={params.active_w_mm} onChange={(e) => setParam("active_w_mm", num(e.target.value, 125))} />
        </label>
        <label>
          Active H mm
          <input type="number" value={params.active_h_mm} onChange={(e) => setParam("active_h_mm", num(e.target.value, 125))} />
        </label>
        <h2>Gaps and panels</h2>
        <label>
          Cell gap mm
          <input type="number" value={params.cell_gap_mm} onChange={(e) => setParam("cell_gap_mm", num(e.target.value, 2))} />
        </label>
        <label>
          Panel gap mm
          <input type="number" value={params.panel_gap_mm} onChange={(e) => setParam("panel_gap_mm", num(e.target.value, 10))} />
        </label>
        <label>
          Max cells wide
          <input type="number" value={params.max_wide} onChange={(e) => setParam("max_wide", num(e.target.value, 6))} />
        </label>
        <label>
          Max cells tall
          <input type="number" value={params.max_tall} onChange={(e) => setParam("max_tall", num(e.target.value, 10))} />
        </label>
        <label>
          Target m²
          <input type="number" step="0.01" value={params.target_area_m2} onChange={(e) => setParam("target_area_m2", num(e.target.value, 6))} />
        </label>
        <button className="primary" disabled={busy || !s.regions.length} onClick={onGenerate}>
          {busy ? "Packing…" : "Generate"}
        </button>
        <p className="hint">Click a region to cycle populate / keep-out / unused. {drawMode ? "Click the canvas to draw an exclude polygon." : ""}</p>
        <button onClick={() => setDrawMode((d) => !d)}>{drawMode ? "Finish drawing" : "Draw exclude"}</button>
        {drawMode && draft.length > 2 && (
          <button
            onClick={() => {
              setS((prev) => addDrawnRegion(prev, draft, "keep_out"));
              setDraft([]);
              setDrawMode(false);
            }}
          >
            Add keep-out
          </button>
        )}
        {err && <p className="issue">{err}</p>}
        <h2>Selected panel</h2>
        {s.selectedPanelId && s.active && (
          <>
            <label>
              Wide
              <input
                type="number"
                onChange={(e) => setS((prev) => resizeBound(prev, s.selectedPanelId!, num(e.target.value, 1), prev.active?.panels.find((p) => p.id === s.selectedPanelId)?.cells_tall ?? 1))}
              />
            </label>
            <button className="danger" onClick={() => setS((prev) => deletePanel(prev, s.selectedPanelId!))}>
              Delete panel
            </button>
          </>
        )}
        <button onClick={() => setS((prev) => undo(prev))}>Undo</button>
        <button onClick={() => setS((prev) => redo(prev))}>Redo</button>
        <h2>Export</h2>
        <button onClick={() => onExport("svg")}>SVG</button>
        <button onClick={() => onExport("dxf")}>DXF</button>
        <button onClick={() => onExport("json")}>JSON</button>
      </aside>
      <div className="canvas-wrap">
        <div className="status">
          <span>Cells {score?.cell_count ?? 0}</span>
          <span>Panels {score?.panel_count ?? 0}</span>
          <span>Usable {score?.active_area_m2.toFixed(4) ?? "0"} m²</span>
          <span>Target {params.target_area_m2.toFixed(3)} m²</span>
          <span className={score?.meets_target ? "ok" : "off"}>Δ {score?.delta_m2.toFixed(4) ?? "0"} m²</span>
          {s.pendingGalleryId && (
            <button
              onClick={() => {
                const next = confirmReplace(s);
                setS(next);
                refreshIssues(next);
              }}
            >
              Confirm replace
            </button>
          )}
        </div>
        <svg
          className="board"
          viewBox={`${bounds.minx} ${bounds.miny} ${bounds.w} ${bounds.h}`}
          onClick={(ev) => {
            if (!drawMode) return;
            const svg = ev.currentTarget;
            const pt = svg.createSVGPoint();
            pt.x = ev.clientX;
            pt.y = ev.clientY;
            const ctm = svg.getScreenCTM();
            if (!ctm) return;
            const loc = pt.matrixTransform(ctm.inverse());
            setDraft((d) => [...d, [loc.x, loc.y]]);
          }}
        >
          {s.regions.map((r) => (
            <polygon
              key={r.id}
              points={r.points.map((p) => p.join(",")).join(" ")}
              fill={r.kind === "populate" ? "#1f6feb" : r.kind === "keep_out" ? "#e05a4f" : "#555"}
              fillOpacity={r.kind === "populate" ? 0.25 : 0.2}
              stroke={r.kind === "populate" ? "#3d8ef0" : "#888"}
              strokeWidth={Math.max(bounds.w, bounds.h) / 400}
              onClick={(e) => {
                e.stopPropagation();
                if (!drawMode) setS((prev) => cycleRegion(prev, r.id));
              }}
            />
          ))}
          {s.active?.panels.map((p) =>
            p.occupied.map(([i, j]) => {
              const pts = cellPoly(p, i, j, params);
              const bad = issues.some((iss) => iss.panel_ids.includes(p.id));
              return (
                <polygon
                  key={`${p.id}-${i}-${j}`}
                  points={pts.map((q) => q.join(",")).join(" ")}
                  fill={bad ? "#e05a4f" : "#f0c14b"}
                  fillOpacity={0.75}
                  stroke="#111"
                  strokeWidth={Math.max(bounds.w, bounds.h) / 800}
                  onMouseDown={(ev) => {
                    ev.preventDefault();
                    setS((prev) => ({ ...prev, selectedPanelId: p.id }));
                    const start = { x: ev.clientX, y: ev.clientY, ox: p.origin[0], oy: p.origin[1] };
                    const move = (e: MouseEvent) => {
                      const scale = bounds.w / (ev.currentTarget.ownerSVGElement?.clientWidth || 1);
                      const nx = Math.round(start.ox + (e.clientX - start.x) * scale);
                      const ny = Math.round(start.oy + (e.clientY - start.y) * scale);
                      setS((prev) => movePanel(prev, p.id, [nx, ny]));
                    };
                    const up = () => {
                      window.removeEventListener("mousemove", move);
                      window.removeEventListener("mouseup", up);
                      setS((prev) => {
                        refreshIssues(prev);
                        return prev;
                      });
                    };
                    window.addEventListener("mousemove", move);
                    window.addEventListener("mouseup", up);
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (e.shiftKey) setS((prev) => toggleCell(prev, p.id, i, j));
                  }}
                />
              );
            }),
          )}
          {draft.length > 1 && <polyline points={draft.map((p) => p.join(",")).join(" ")} fill="none" stroke="#e05a4f" />}
        </svg>
      </div>
      <div className="gallery">
        <h2>Layouts</h2>
        {s.layouts.map((l) => (
          <div
            key={l.id}
            className={`card ${s.active?.id === l.id ? "active" : ""}`}
            onClick={() => setS((prev) => selectGallery(prev, l.id))}
          >
            <strong>{l.family}</strong>
            <div>{l.score?.cell_count} cells · {l.score?.active_area_m2.toFixed(3)} m²</div>
          </div>
        ))}
        <h2>Issues</h2>
        {!issues.length && <p className="hint">No issues.</p>}
        {issues.map((iss, i) => (
          <div key={i} className="issue">
            {iss.message}
          </div>
        ))}
      </div>
    </div>
  );
}
