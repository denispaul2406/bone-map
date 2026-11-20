"use client";

import React, { useEffect, useRef, useState } from "react";
import { Check, Upload } from "lucide-react";
import { Assessment, CaseDetail, api, fullAssetUrl } from "@/lib/api";

interface RealXRayWorkspaceProps {
  caseDetail: CaseDetail;
  assessment: Assessment;
  onUpdated: () => void;
  onOpenTechnical: () => void;
}

type ViewMode = "split" | "xray" | "lat" | "mask" | "ct2d";

export function RealXRayWorkspace({
  caseDetail,
  assessment,
  onUpdated,
  onOpenTechnical,
}: RealXRayWorkspaceProps) {
  const hasAp = Boolean(assessment.xray_ap_url);
  const hasLat = Boolean(assessment.xray_lat_url);
  const hasMask = Boolean(assessment.xray_mask_url);
  const hasCt2d = Boolean(assessment.coronal_ct_2d_url);

  const defaultMode: ViewMode =
    hasAp && hasCt2d ? "split" : hasAp ? "xray" : hasLat ? "lat" : hasCt2d ? "ct2d" : "xray";

  const [mode, setMode] = useState<ViewMode>(defaultMode);
  const [mrust, setMrust] = useState({
    anterior: assessment.mrust?.anterior ?? 1,
    posterior: assessment.mrust?.posterior ?? 1,
    medial: assessment.mrust?.medial ?? 1,
    lateral: assessment.mrust?.lateral ?? 1,
    healing_phase: assessment.healing_phase ?? "Inflammatory",
    clinical_notes: assessment.clinical_notes ?? "",
  });
  const [apFile, setApFile] = useState<File | null>(null);
  const [latFile, setLatFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const nextMode: ViewMode =
      assessment.xray_ap_url && assessment.coronal_ct_2d_url
        ? "split"
        : assessment.xray_ap_url
        ? "xray"
        : assessment.xray_lat_url
        ? "lat"
        : assessment.coronal_ct_2d_url
        ? "ct2d"
        : "xray";
    setMode(nextMode);
    setMrust({
      anterior: assessment.mrust?.anterior ?? 1,
      posterior: assessment.mrust?.posterior ?? 1,
      medial: assessment.mrust?.medial ?? 1,
      lateral: assessment.mrust?.lateral ?? 1,
      healing_phase: assessment.healing_phase ?? "Inflammatory",
      clinical_notes: assessment.clinical_notes ?? "",
    });
    setApFile(null);
    setLatFile(null);
    setSaved(false);
    setSaveError(null);
  }, [assessment]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleSaveMrust = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    try {
      const fd = new FormData();
      fd.append("mrust_anterior", String(mrust.anterior));
      fd.append("mrust_posterior", String(mrust.posterior));
      fd.append("mrust_medial", String(mrust.medial));
      fd.append("mrust_lateral", String(mrust.lateral));
      fd.append("healing_phase", mrust.healing_phase);
      if (mrust.clinical_notes.trim()) {
        fd.append("clinical_notes", mrust.clinical_notes.trim());
      }
      if (apFile) fd.append("ap_file", apFile);
      if (latFile) fd.append("lat_file", latFile);
      await api.updateXRay(assessment.id, fd);
      setApFile(null);
      setLatFile(null);
      setSaved(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setSaved(false), 2000);
      onUpdated();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save X-ray & mRUST");
    } finally {
      setSaving(false);
    }
  };

  const totalMrust = mrust.anterior + mrust.posterior + mrust.medial + mrust.lateral;
  const activeImgUrl =
    mode === "mask"
      ? assessment.xray_mask_url
      : mode === "ct2d"
      ? assessment.coronal_ct_2d_url
      : mode === "lat"
      ? assessment.xray_lat_url
      : assessment.xray_ap_url || assessment.xray_lat_url;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      {/* Left 64%: Obsidian Clinical Radiology Stage */}
      <div className="lg:col-span-7 relative overflow-hidden rounded-[22px] bg-[#0E1116] border border-black/10 p-4 flex flex-col gap-3 min-h-[560px]">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1 rounded-full bg-white/10 p-1 backdrop-blur-md">
            {hasAp && hasCt2d && (
              <PillBtn active={mode === "split"} onClick={() => setMode("split")}>
                Split View
              </PillBtn>
            )}
            {hasAp && (
              <PillBtn active={mode === "xray"} onClick={() => setMode("xray")}>
                AP Radiograph
              </PillBtn>
            )}
            {hasLat && (
              <PillBtn active={mode === "lat"} onClick={() => setMode("lat")}>
                Lateral
              </PillBtn>
            )}
            {hasMask && (
              <PillBtn active={mode === "mask"} onClick={() => setMode("mask")}>
                Tibia Mask
              </PillBtn>
            )}
            {hasCt2d && (
              <PillBtn active={mode === "ct2d"} onClick={() => setMode("ct2d")}>
                Coronal CT
              </PillBtn>
            )}
          </div>
          <span className="text-[11px] text-white/60">{caseDetail.data_source}</span>
        </div>

        <div className="flex-1 flex items-center justify-center">
          {!hasAp && !hasLat && !hasCt2d ? (
            <div className="text-center px-6 flex flex-col items-center gap-2">
              <Upload className="h-7 w-7 text-white/40" />
              <p className="text-sm font-medium text-white/80">
                No radiograph uploaded for {assessment.timepoint_label}
              </p>
              <p className="text-xs text-white/50">
                Select an AP or Lateral radiograph image on the right to attach and score mRUST.
              </p>
            </div>
          ) : mode === "split" && hasAp && hasCt2d ? (
            <div className="grid grid-cols-2 gap-3 w-full h-[480px]">
              <div className="flex flex-col items-center justify-center rounded-xl bg-black/40 p-2 overflow-hidden">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={fullAssetUrl(assessment.xray_ap_url) || ""}
                  alt="AP Radiograph"
                  className="max-h-[430px] object-contain"
                />
                <span className="mt-2 text-[11px] text-white/60">AP Radiograph</span>
              </div>
              <div className="flex flex-col items-center justify-center rounded-xl bg-black/40 p-2 overflow-hidden">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={fullAssetUrl(assessment.coronal_ct_2d_url) || ""}
                  alt="2D Coronal CT"
                  className="max-h-[430px] object-contain"
                />
                <span className="mt-2 text-[11px] text-white/60">2D Coronal CT Slice</span>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center w-full h-[480px]">
              {activeImgUrl ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={fullAssetUrl(activeImgUrl) || ""}
                  alt="Clinical radiograph"
                  className="max-h-[470px] object-contain"
                />
              ) : null}
            </div>
          )}
        </div>
      </div>

      {/* Right 36%: Calm Clinical Summary & mRUST Scorer */}
      <form onSubmit={handleSaveMrust} className="lg:col-span-5 apple-card p-6 flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <span className="rounded-full bg-[#FF9F0A]/14 px-3 py-1 text-xs font-medium text-[#B45309]">
              {caseDetail.ao_classification || "Fracture Case"}
            </span>
            <span className="text-[11px] text-[#86868B]">
              {assessment.mrust ? `mRUST ${assessment.mrust.total}/16` : "Unscored"}
            </span>
          </div>
          <h2 className="text-lg font-semibold tracking-tight text-[#1D1D1F] mt-1">
            {caseDetail.fracture_location}
          </h2>
          {caseDetail.notes && (
            <p className="text-xs text-[#6E6E73] leading-relaxed">{caseDetail.notes}</p>
          )}
        </div>

        <div className="rounded-2xl bg-[#F5F5F7] p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-[#1D1D1F]">
              Clinician mRUST Score (Track B)
            </span>
            <span className="text-sm font-semibold tabular-nums text-[#0071E3]">
              {totalMrust} / 16
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {(["anterior", "posterior", "medial", "lateral"] as const).map((q) => (
              <label key={q} className="flex flex-col gap-1 text-[11px]">
                <span className="capitalize text-[#6E6E73]">{q}</span>
                <select
                  value={mrust[q]}
                  onChange={(e) => setMrust({ ...mrust, [q]: Number(e.target.value) })}
                  className="rounded-xl border border-black/10 bg-white px-2 py-1.5 text-xs font-medium tabular-nums"
                >
                  <option value={1}>1 · None</option>
                  <option value={2}>2 · Callus</option>
                  <option value={3}>3 · Bridging</option>
                  <option value={4}>4 · Remodel</option>
                </select>
              </label>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5 text-[11px]">
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Upload AP X-Ray (optional)</span>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setApFile(e.target.files?.[0] || null)}
              className="text-[11px] file:mr-2 file:rounded-full file:border-0 file:bg-[#F5F5F7] file:px-2.5 file:py-1 file:text-[11px]"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Upload Lateral X-Ray (optional)</span>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setLatFile(e.target.files?.[0] || null)}
              className="text-[11px] file:mr-2 file:rounded-full file:border-0 file:bg-[#F5F5F7] file:px-2.5 file:py-1 file:text-[11px]"
            />
          </label>
        </div>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-[#6E6E73]">Clinical Notes</span>
          <textarea
            rows={2}
            value={mrust.clinical_notes}
            onChange={(e) => setMrust({ ...mrust, clinical_notes: e.target.value })}
            placeholder="Radiographic observations, hardware alignment…"
            className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2 text-xs text-[#1D1D1F] outline-none focus:border-[#0071E3]"
          />
        </label>

        {saveError && (
          <div className="rounded-xl bg-[#FF3B30]/10 px-3 py-2 text-xs text-[#B91C1C]">
            {saveError}
          </div>
        )}

        <div className="flex items-center justify-between gap-2">
          <select
            value={mrust.healing_phase}
            onChange={(e) => setMrust({ ...mrust, healing_phase: e.target.value })}
            className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2 text-xs text-[#1D1D1F]"
          >
            <option>Inflammatory</option>
            <option>Soft Callus</option>
            <option>Hard Callus</option>
            <option>Remodelling</option>
          </select>

          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-full bg-[#0071E3] px-4 py-2 text-xs font-medium text-white hover:bg-[#0062C4] transition disabled:opacity-50"
          >
            {saved ? (
              <>
                <Check className="h-3.5 w-3.5" /> Saved
              </>
            ) : saving ? (
              "Saving…"
            ) : (
              "Save X-Ray & Score"
            )}
          </button>
        </div>

        <div className="border-t border-black/[0.06] pt-3 flex items-center justify-between text-xs">
          <span className="text-[#6E6E73]">Have a 3D DICOM/NIfTI CT for this visit?</span>
          <button
            type="button"
            onClick={onOpenTechnical}
            className="font-medium text-[#0071E3] hover:underline"
          >
            Upload 3D CT ›
          </button>
        </div>
      </form>
    </div>
  );
}

function PillBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs font-medium transition ${
        active ? "bg-white text-[#1D1D1F]" : "text-white/70 hover:text-white"
      }`}
    >
      {children}
    </button>
  );
}
