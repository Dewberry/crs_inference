import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { GeoJSON, MapContainer, Pane, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import {
  CheckCircle2,
  FileText,
  Hash,
  Loader2,
  MapPin,
  Upload,
  XCircle,
} from "lucide-react";
import type { GeoJsonObject } from "geojson";

// ─── Types ────────────────────────────────────────────────────────────────────

interface InferResult {
  crs: string | null;
  confidence: number;
  method: "local" | "non_local" | "none";
  candidates: GeoJsonObject | null;
  target: GeoJsonObject | null;
  geometry: GeoJsonObject | null;
}

interface County {
  geoid: string;
  name: string;
  state: string;
}

type TargetTab = "file" | "county";

type Counties = County[];

// ─── API ──────────────────────────────────────────────────────────────────────

async function runInference(
  rasFile: File,
  target: { file: File } | { countyFips: string[] },
): Promise<InferResult> {
  const form = new FormData();
  form.append("geometry_file", rasFile);
  if ("file" in target) {
    form.append("target_file", target.file);
  } else {
    form.append("county_fips", target.countyFips.join(","));
  }
  const res = await fetch("/api/infer", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(String(err.detail ?? "Inference failed"));
  }
  return res.json();
}

// ─── Basemap selector ────────────────────────────────────────────────────────

const BASEMAPS = [
  { label: "Streets",   url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",                                                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' },
  { label: "Satellite", url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",          attribution: "Tiles &copy; Esri" },
  { label: "Light",     url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",                                        attribution: '&copy; <a href="https://carto.com/">CARTO</a>' },
  { label: "Dark",      url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",                                         attribution: '&copy; <a href="https://carto.com/">CARTO</a>' },
] as const;

type BasemapLabel = typeof BASEMAPS[number]["label"];

function BasemapSelector({ value, onChange }: { value: BasemapLabel; onChange: (b: BasemapLabel) => void }) {
  return (
    <div className="absolute bottom-6 right-3 z-[1000] flex gap-1 bg-background/90 backdrop-blur-sm border rounded-lg p-1 shadow-md">
      {BASEMAPS.map(({ label }) => (
        <button
          key={label}
          className={[
            "px-2.5 py-1 rounded-md text-[11px] font-medium transition-all",
            value === label
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-accent",
          ].join(" ")}
          onClick={() => onChange(label)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ─── Map helpers ──────────────────────────────────────────────────────────────

function MapAutoFit({ candidates }: { candidates: GeoJsonObject | null }) {
  const map = useMap();
  useEffect(() => {
    if (!candidates) return;
    try {
      const bounds = L.geoJSON(candidates).getBounds();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [48, 48] });
    } catch {
      // ignore invalid / empty bounds
    }
  }, [candidates, map]);
  return null;
}

// ─── Drop Zone ────────────────────────────────────────────────────────────────

interface DropZoneProps {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  onChange: (f: File) => void;
}

function DropZone({ label, hint, accept, file, onChange }: DropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) onChange(f);
    },
    [onChange],
  );

  return (
    <div>
      <p className="text-xs font-medium text-foreground mb-1.5">{label}</p>
      <div
        role="button"
        tabIndex={0}
        className={[
          "flex flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-5 cursor-pointer transition-colors select-none",
          dragging
            ? "border-primary bg-accent"
            : file
              ? "border-primary/60 bg-accent/30"
              : "border-border hover:border-primary/40 hover:bg-accent/10",
        ].join(" ")}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
      >
        {file ? (
          <>
            <FileText className="h-5 w-5 text-primary" />
            <span className="text-xs font-medium text-foreground text-center break-all">{file.name}</span>
            <span className="text-[11px] text-muted-foreground">
              {(file.size / 1024).toFixed(1)} KB
            </span>
          </>
        ) : (
          <>
            <Upload className="h-5 w-5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground text-center">{hint}</span>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onChange(f);
          }}
        />
      </div>
    </div>
  );
}

// ─── Tab toggle ───────────────────────────────────────────────────────────────

function TabToggle({ value, onChange }: { value: TargetTab; onChange: (v: TargetTab) => void }) {
  return (
    <div className="flex rounded-lg bg-muted p-0.5">
      {(["file", "county"] as TargetTab[]).map((tab) => (
        <button
          key={tab}
          className={[
            "flex-1 flex items-center justify-center gap-1.5 rounded-md py-1 text-xs font-medium transition-all",
            value === tab
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          ].join(" ")}
          onClick={() => onChange(tab)}
        >
          {tab === "file" ? (
            <><Upload className="h-3 w-3" />File</>
          ) : (
            <><Hash className="h-3 w-3" />County</>
          )}
        </button>
      ))}
    </div>
  );
}

// ─── County search ────────────────────────────────────────────────────────────

function CountySearch({
  value,
  onChange,
}: {
  value: Counties;
  onChange: (c: Counties) => void;
}) {
  const [geoid, setGeoid] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [pending, setPending] = useState<County | null>(null);

  // Look up county whenever a complete 5-digit GEOID is entered
  useEffect(() => {
    if (geoid.length !== 5) { setPending(null); setNotFound(false); return; }
    let cancelled = false;
    fetch(`/api/counties/${geoid}`)
      .then((res) => {
        if (cancelled) return;
        if (res.ok) { res.json().then((c: County) => { setPending(c); setNotFound(false); }); }
        else { setPending(null); setNotFound(true); }
      })
      .catch(() => { if (!cancelled) { setPending(null); setNotFound(false); } });
    return () => { cancelled = true; };
  }, [geoid]);

  const addCounty = useCallback(() => {
    if (!pending || value.some((c) => c.geoid === pending.geoid)) return;
    onChange([...value, pending]);
    setGeoid("");
    setPending(null);
  }, [pending, value, onChange]);

  const removeCounty = useCallback((geoid: string) => {
    onChange(value.filter((c) => c.geoid !== geoid));
  }, [value, onChange]);

  const alreadyAdded = pending ? value.some((c) => c.geoid === pending.geoid) : false;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-foreground">County GEOIDs</p>

      {value.length > 0 && (
        <div className="flex flex-col gap-1">
          {value.map((c) => (
            <div key={c.geoid} className="flex items-center justify-between rounded-lg border border-primary/40 bg-accent/20 px-2.5 py-1.5">
              <div className="min-w-0">
                <span className="text-xs font-mono font-medium">{c.geoid}</span>
                <span className="text-[11px] text-muted-foreground ml-1.5">{c.name}, {c.state}</span>
              </div>
              <button
                className="ml-2 shrink-0 text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => removeCounty(c.geoid)}
              >
                <XCircle className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-1.5">
        <div className="relative flex-1">
          <input
            className={[
              "w-full rounded-lg border bg-background px-3 py-2 text-xs font-mono placeholder:text-muted-foreground",
              "focus:outline-none focus:ring-1 focus:ring-primary transition-colors",
              notFound ? "border-destructive/60" : pending ? "border-primary/60" : "",
            ].join(" ")}
            placeholder="5-digit FIPS (e.g. 50007)"
            maxLength={5}
            value={geoid}
            onChange={(e) => setGeoid(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && addCounty()}
          />
        </div>
        <button
          className="shrink-0 rounded-lg border bg-secondary px-2.5 py-1 text-xs font-medium transition-colors hover:bg-accent disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={!pending || alreadyAdded}
          onClick={addCounty}
        >
          Add
        </button>
      </div>

      {pending && !alreadyAdded && (
        <p className="text-[11px] text-muted-foreground">
          <span className="font-medium text-foreground">{pending.name}</span>
          {" · "}{pending.state}
        </p>
      )}
      {alreadyAdded && (
        <p className="text-[11px] text-muted-foreground">Already added</p>
      )}
      {notFound && (
        <p className="text-[11px] text-destructive">GEOID not found</p>
      )}
    </div>
  );
}

// ─── Candidate list ──────────────────────────────────────────────────────────

interface CandidateFeature {
  crs: string;
  overlap_pct: number;
  is_best: boolean;
}

function CandidateList({
  candidates,
  showAll,
  onToggle,
}: {
  candidates: GeoJsonObject | null;
  showAll: boolean;
  onToggle: () => void;
}) {
  if (!candidates || !("features" in candidates)) return null;
  const features = (candidates as { features: { properties: CandidateFeature }[] }).features
    .map((f) => f.properties)
    .sort((a, b) => b.overlap_pct - a.overlap_pct);
  if (features.length === 0) return null;

  const visible = showAll ? features : features.filter((c) => c.is_best);

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Candidates</p>
        <button
          className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
          onClick={onToggle}
        >
          {showAll ? `Show best only` : `Show all ${features.length}`}
        </button>
      </div>
      {visible.map((c, i) => (
        <div
          key={c.crs}
          className={[
            "rounded-lg border px-3 py-2 flex flex-col gap-1",
            c.is_best ? "border-green-500/40 bg-green-500/5" : "bg-card",
          ].join(" ")}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="text-[10px] text-muted-foreground tabular-nums w-4 shrink-0">#{i + 1}</span>
              <span className="text-xs font-mono font-medium truncate">{c.crs}</span>
            </div>
            {c.is_best && (
              <span className="text-[10px] font-medium text-green-600 shrink-0">best</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1 rounded-full bg-secondary overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(c.overlap_pct * 100).toFixed(1)}%`,
                  backgroundColor:
                    c.overlap_pct > 0.7
                      ? "var(--color-confidence-high)"
                      : c.overlap_pct > 0.4
                        ? "var(--color-confidence-mid)"
                        : "var(--color-confidence-low)",
                }}
              />
            </div>
            <span className="text-[10px] tabular-nums text-muted-foreground w-10 text-right shrink-0">
              {(c.overlap_pct * 100).toFixed(1)}%
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Result card ──────────────────────────────────────────────────────────────

function ResultCard({ result }: { result: InferResult }) {
  const pct = Math.round(result.confidence * 100);
  const barColor =
    pct > 70
      ? "var(--color-confidence-high)"
      : pct > 40
        ? "var(--color-confidence-mid)"
        : "var(--color-confidence-low)";
  const methodLabel =
    { local: "Local CRS", non_local: "Non-local CRS", none: "No match" }[result.method];
  const candidateCount =
    result.candidates && "features" in result.candidates
      ? (result.candidates as { features: unknown[] }).features.length
      : 0;

  return (
    <div className="rounded-xl border bg-card p-4 space-y-3.5">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
            Inferred CRS
          </p>
          {result.crs ? (
            <p className="text-xl font-semibold tracking-tight">{result.crs}</p>
          ) : (
            <p className="text-base text-muted-foreground">No CRS found</p>
          )}
        </div>
        {result.crs ? (
          <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0 mt-0.5" />
        ) : (
          <XCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
        )}
      </div>

      {result.crs && (
        <div className="space-y-1">
          <div className="flex justify-between text-[11px] text-muted-foreground">
            <span>Confidence</span>
            <span>{pct}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-secondary overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${pct}%`, backgroundColor: barColor }}
            />
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium">
          {methodLabel}
        </span>
        {candidateCount > 0 && (
          <span className="text-[11px] text-muted-foreground">
            {candidateCount} candidate{candidateCount !== 1 ? "s" : ""}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [basemap, setBasemap] = useState<BasemapLabel>("Streets");
  const [showAllCandidates, setShowAllCandidates] = useState(false);
  const [rasFile, setRasFile] = useState<File | null>(null);
  const [targetTab, setTargetTab] = useState<TargetTab>("file");
  const [targetFile, setTargetFile] = useState<File | null>(null);
  const [selectedCounties, setSelectedCounties] = useState<Counties>([]);

  const targetReady = targetTab === "file" ? targetFile !== null : selectedCounties.length > 0;

  const mutation = useMutation({
    mutationFn: () =>
      runInference(
        rasFile!,
        targetTab === "file"
          ? { file: targetFile! }
          : { countyFips: selectedCounties.map((c) => c.geoid) },
      ),
    onSuccess: () => setShowAllCandidates(false),
  });

  const result = mutation.data ?? null;

  // Stable key so GeoJSON layers remount when a new result arrives
  const resultKey = result
    ? `${result.crs ?? "none"}-${result.confidence}`
    : "empty";

  // Filter candidates GeoJSON to only the best match when the toggle is off
  const visibleCandidates = useMemo(() => {
    if (showAllCandidates || !result?.candidates) return result?.candidates ?? null;
    if (!("features" in result.candidates)) return result.candidates;
    const col = result.candidates as { type: string; features: { properties?: { is_best?: boolean } }[] };
    return { ...col, features: col.features.filter((f) => f.properties?.is_best) } as GeoJsonObject;
  }, [result?.candidates, showAllCandidates]);

  const candidateStyle = useCallback(
    (feature?: { properties?: { is_best?: boolean } }) =>
      feature?.properties?.is_best
        ? { color: "var(--color-best)", weight: 3, opacity: 1 }
        : { color: "var(--color-candidate)", weight: 1.5, opacity: 0.5 },
    [],
  );

  return (
    <div className="flex flex-col h-screen bg-background text-foreground">
      {/* Header */}
      <header className="flex-none border-b px-5 py-3 flex items-center gap-2.5">
        <MapPin className="h-4 w-4 text-primary shrink-0" />
        <div className="min-w-0">
          <h1 className="text-base font-semibold leading-tight">CRS Finder</h1>
          <p className="text-[11px] text-muted-foreground leading-tight">
            Identify the coordinate reference system of a geometry
          </p>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside className="w-72 flex-none border-r overflow-y-auto p-4 flex flex-col gap-4">
          <div className="flex flex-col gap-3">
            <DropZone
              label="Geometry File"
              hint="HEC-RAS .g## · GeoJSON · GeoPackage"
              accept=".g00,.g01,.g02,.g03,.g04,.g05,.g06,.g07,.g08,.g09,.g10,.g11,.g12,.geojson,.json,.gpkg"
              file={rasFile}
              onChange={setRasFile}
            />

            {/* Target boundary — file upload or county lookup */}
            <div className="flex flex-col gap-2">
              <p className="text-xs font-medium text-foreground">Target Boundary</p>
              <TabToggle value={targetTab} onChange={setTargetTab} />
              {targetTab === "file" ? (
                <DropZone
                  label=""
                  hint="Drop GeoJSON or GeoPackage"
                  accept=".geojson,.json,.gpkg"
                  file={targetFile}
                  onChange={setTargetFile}
                />
              ) : (
                <CountySearch value={selectedCounties} onChange={setSelectedCounties} />
              )}
            </div>
          </div>

          <button
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-opacity disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 active:opacity-80"
            disabled={!rasFile || !targetReady || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Running…
              </>
            ) : (
              "Run Inference"
            )}
          </button>

          {mutation.isError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 flex gap-2 items-start">
              <XCircle className="h-4 w-4 text-destructive shrink-0 mt-px" />
              <p className="text-xs text-destructive leading-snug">
                {(mutation.error as Error).message}
              </p>
            </div>
          )}

          {result && <ResultCard result={result} />}
          {result && (
            <CandidateList
              candidates={result.candidates}
              showAll={showAllCandidates}
              onToggle={() => setShowAllCandidates((v) => !v)}
            />
          )}
        </aside>

        {/* Map */}
        <main className="flex-1 relative">
          {!result && !mutation.isPending && (
            <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
              <p className="text-sm text-muted-foreground bg-background/80 backdrop-blur-sm px-4 py-2 rounded-lg border">
                Upload files and run inference to see results
              </p>
            </div>
          )}

          <MapContainer
            center={[39.5, -98.35]}
            zoom={4}
            className="h-full w-full"
            zoomControl
          >
            {/* Swap basemap without remounting by keying on the URL */}
            {BASEMAPS.map(({ label, url, attribution }) =>
              label === basemap ? (
                <TileLayer key={url} url={url} attribution={attribution} />
              ) : null
            )}

            {result?.target && (
              <GeoJSON
                key={`target-${resultKey}`}
                data={result.target}
                style={{ color: "var(--color-target)", fillColor: "var(--color-target)", fillOpacity: 0.06, weight: 1.5, dashArray: "6 4" }}
              />
            )}

            {result?.candidates && (
              <GeoJSON
                key={`candidates-${resultKey}-${showAllCandidates}`}
                data={visibleCandidates!}
                style={candidateStyle}
              />
            )}

            {/* Elevated pane keeps the RAS geometry above all candidate polygons */}
            <Pane name="ras-geometry" style={{ zIndex: 650 }}>
              {result?.geometry && (
                <GeoJSON
                  key={`geometry-${resultKey}`}
                  data={result.geometry}
                  style={{ color: "var(--color-geometry)", weight: 3, opacity: 1 }}
                />
              )}
            </Pane>

            <MapAutoFit candidates={result?.candidates ?? null} />
          </MapContainer>

          <BasemapSelector value={basemap} onChange={setBasemap} />
        </main>
      </div>
    </div>
  );
}

