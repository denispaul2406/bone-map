"use client";

import React, { useEffect, useMemo, useState } from "react";
import { API_BASE, CTRun } from "@/lib/api";

interface CTSliceViewerProps {
  ctRun: CTRun;
}

type Plane = "axial" | "coronal" | "sagittal";

export function CTSliceViewer({ ctRun }: CTSliceViewerProps) {
  const dims = ctRun.metadata?.dimensions_zyx || [140, 144, 144];
  const defaults = useMemo(
    () =>
      ctRun.assets.default_slice_indices || {
        axial: Math.floor(dims[0] / 2),
        coronal: Math.floor(dims[1] / 2),
        sagittal: Math.floor(dims[2] / 2),
      },
    [ctRun.assets.default_slice_indices, dims]
  );

  const [plane, setPlane] = useState<Plane>("axial");
  const [overlay, setOverlay] = useState(true);
  const [indices, setIndices] = useState(defaults);
  const [sliceError, setSliceError] = useState(false);

  useEffect(() => {
    setIndices(defaults);
    setSliceError(false);
  }, [ctRun.id, defaults]);

  const maxIndex = useMemo(() => {
    if (plane === "axial") return Math.max(0, dims[0] - 1);
    if (plane === "coronal") return Math.max(0, dims[1] - 1);
    return Math.max(0, dims[2] - 1);
  }, [dims, plane]);

  const currentIdx = Math.min(indices[plane], maxIndex);
  const sliceUrl = `${API_BASE}/api/ct-runs/${ctRun.id}/slice/${plane}/${currentIdx}?overlay=${overlay}`;

  return (
    <div className="apple-card p-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-[#1D1D1F]">2D Multi-Planar CT Inspector</h3>
          <p className="text-xs text-[#6E6E73]">Bone window (WL 450 · WW 1800 HU)</p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex rounded-full bg-[#F5F5F7] p-0.5 border border-black/6">
            {(["axial", "coronal", "sagittal"] as Plane[]).map((p) => (
              <button
                key={p}
                onClick={() => setPlane(p)}
                className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition ${
                  plane === p
                    ? "bg-white text-[#1D1D1F] shadow-xs"
                    : "text-[#6E6E73] hover:text-[#1D1D1F]"
                }`}
              >
                {p}
              </button>
            ))}
          </div>

          <button
            onClick={() => setOverlay((v) => !v)}
            className={`rounded-full px-3 py-1 text-xs font-medium border transition ${
              overlay
                ? "border-[#0071E3]/30 bg-[#0071E3]/10 text-[#0071E3]"
                : "border-black/8 bg-white text-[#6E6E73]"
            }`}
          >
            {overlay ? "Mask On" : "Mask Off"}
          </button>
        </div>
      </div>

      <div className="relative flex h-[280px] items-center justify-center overflow-hidden rounded-xl bg-[#0E1116]">
        {sliceError ? (
          <div className="text-xs text-white/70">Unable to load slice preview</div>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={sliceUrl}
            alt={`${plane} CT slice ${currentIdx}`}
            onLoad={() => setSliceError(false)}
            onError={() => setSliceError(true)}
            className="max-h-full max-w-full object-contain"
          />
        )}
        <div className="absolute bottom-2 right-2 rounded-full bg-black/60 px-2.5 py-0.5 text-[11px] font-mono tabular-nums text-white/90">
          {plane.toUpperCase()} {currentIdx + 1} / {maxIndex + 1}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-[#6E6E73] w-14">Slice</span>
        <input
          type="range"
          min={0}
          max={maxIndex}
          value={currentIdx}
          onChange={(e) =>
            setIndices((prev) => ({ ...prev, [plane]: Number(e.target.value) }))
          }
          className="w-full accent-[#0071E3] cursor-pointer"
        />
      </div>

      <div className="flex flex-wrap gap-4 text-[11px] text-[#6E6E73]">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#0071E3]" /> Tibia
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#F59E0B]" /> Callus
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#38BDF8]" /> Fixation Hardware
        </span>
      </div>
    </div>
  );
}
