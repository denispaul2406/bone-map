"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Cpu,
  Download,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";
import {
  API_BASE,
  Assessment,
  CTRun,
  CaseDetail,
  HealthResponse,
  api,
  fullAssetUrl,
} from "@/lib/api";

interface TechnicalDrawerProps {
  open: boolean;
  onClose: () => void;
  health: HealthResponse | null;
  caseDetail: CaseDetail;
  assessment: Assessment | null;
  latestCtRun: CTRun | null;
  onUpdated: () => void;
}

export function TechnicalDrawer({
  open,
  onClose,
  health,
  caseDetail,
  assessment,
  latestCtRun,
  onUpdated,
}: TechnicalDrawerProps) {
  const [ctFile, setCtFile] = useState<File | null>(null);
  const [sampleName, setSampleName] = useState(health?.samples[0] || "");
  const [segBackend, setSegBackend] = useState<"auto_lower_limb" | "totalsegmentator">(
    "totalsegmentator"
  );
  const [uploadingCt, setUploadingCt] = useState(false);
  const [uploadingMask, setUploadingMask] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const [drawerNotice, setDrawerNotice] = useState<string | null>(null);
  const maskInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setCtFile(null);
    setDrawerError(null);
    setDrawerNotice(null);
  }, [assessment?.id]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const samples = health?.samples || [];
  const selectedSample = sampleName || samples[0] || "";
  const labelDownloadUrl = fullAssetUrl(latestCtRun?.assets.label_nifti);

  const handleUploadCt = async () => {
    if (!assessment || !ctFile) return;
    setUploadingCt(true);
    setDrawerError(null);
    setDrawerNotice(null);
    try {
      await api.uploadCT(assessment.id, ctFile, segBackend);
      setCtFile(null);
      onUpdated();
      onClose();
    } catch (err) {
      setDrawerError(err instanceof Error ? err.message : "Failed to upload CT scan.");
    } finally {
      setUploadingCt(false);
    }
  };

  const handleAttachSample = async () => {
    if (!assessment || !selectedSample) return;
    setUploadingCt(true);
    setDrawerError(null);
    setDrawerNotice(null);
    try {
      await api.attachSampleCT(assessment.id, selectedSample, segBackend);
      onUpdated();
      onClose();
    } catch (err) {
      setDrawerError(err instanceof Error ? err.message : "Failed to attach sample CT.");
    } finally {
      setUploadingCt(false);
    }
  };

  const handleMaskReimport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !latestCtRun) return;
    setUploadingMask(true);
    setDrawerError(null);
    setDrawerNotice(null);
    try {
      await api.reimportMask(latestCtRun.id, file);
      setDrawerNotice("Corrected mask queued for recomputation.");
      onUpdated();
    } catch (err) {
      setDrawerError(err instanceof Error ? err.message : "Failed to re-import mask.");
    } finally {
      setUploadingMask(false);
      if (maskInputRef.current) maskInputRef.current.value = "";
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Data, 3D Slicer and Audit Drawer"
      onClick={onClose}
      className="fixed inset-0 z-50 flex justify-end bg-black/25 backdrop-blur-xs"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-md bg-white shadow-2xl border-l border-black/8 flex flex-col"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-black/[0.06]">
          <div>
            <h2 className="text-sm font-semibold text-[#1D1D1F]">Data, 3D Slicer & Audit</h2>
            <p className="text-[11px] text-[#6E6E73]">
              Engineering controls for {caseDetail.id}
              {assessment ? ` · ${assessment.timepoint_label}` : ""}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close Data and Tools drawer"
            className="rounded-full p-1.5 text-[#6E6E73] hover:bg-black/5"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-6">
          {drawerError && (
            <div className="rounded-xl bg-[#FF3B30]/10 px-3.5 py-2.5 text-xs text-[#B91C1C]">
              {drawerError}
            </div>
          )}
          {drawerNotice && (
            <div className="rounded-xl bg-[#34C759]/12 px-3.5 py-2.5 text-xs text-[#15803D]">
              {drawerNotice}
            </div>
          )}

          {/* Hardware & Export */}
          <div className="flex items-center justify-between rounded-2xl bg-[#F5F5F7] px-4 py-3 text-xs">
            <div className="flex items-center gap-2 text-[#1D1D1F]">
              <Cpu className="h-4 w-4 text-[#34C759]" />
              <span>
                {health?.gpu.cuda_available
                  ? `${health.gpu.device_name?.replace("NVIDIA GeForce ", "")} (${Math.round(
                      (health.gpu.vram_total_mb || 0) / 1024
                    )} GB)`
                  : "CPU Mode"}
              </span>
            </div>
            <a
              href={`${API_BASE}/api/cases/${encodeURIComponent(caseDetail.id)}/export/csv`}
              className="inline-flex items-center gap-1 font-medium text-[#0071E3] hover:underline"
            >
              <Download className="h-3.5 w-3.5" /> Export CSV
            </a>
          </div>

          {/* 3D CT Ingest */}
          {assessment && (
            <div className="flex flex-col gap-3">
              <div className="text-xs font-semibold text-[#1D1D1F]">
                Upload 3D CT Volume ({assessment.timepoint_label})
              </div>
              <p className="text-[11px] text-[#6E6E73]">
                Accepts `.nii`, `.nii.gz`, or zipped DICOM series (`.zip`). PHI tags are stripped automatically.
              </p>
              <label className="flex flex-col gap-1 text-[11px]">
                <span className="text-[#6E6E73]">Segmentation Engine</span>
                <select
                  value={segBackend}
                  onChange={(e) =>
                    setSegBackend(e.target.value as "auto_lower_limb" | "totalsegmentator")
                  }
                  className="rounded-xl border border-black/10 bg-[#F5F5F7] px-2.5 py-1.5 text-xs text-[#1D1D1F]"
                >
                  <option value="totalsegmentator">
                    TotalSegmentator AI (appendicular_bones · GPU)
                  </option>
                  <option value="auto_lower_limb">
                    Fast Lower-Limb HU + Morphology (CPU)
                  </option>
                </select>
              </label>
              <input
                type="file"
                accept=".nii,.nii.gz,.zip"
                onChange={(e) => setCtFile(e.target.files?.[0] || null)}
                className="text-xs file:mr-3 file:rounded-full file:border-0 file:bg-[#F5F5F7] file:px-3 file:py-1.5 file:text-xs file:font-medium"
              />
              <button
                onClick={handleUploadCt}
                disabled={!ctFile || uploadingCt}
                className="self-start rounded-full bg-[#0071E3] px-4 py-2 text-xs font-medium text-white disabled:opacity-50"
              >
                {uploadingCt ? "Processing…" : "Process CT Scan"}
              </button>

              {samples.length > 0 && (
                <div className="pt-3 border-t border-black/[0.06] flex flex-col gap-2">
                  <span className="text-[11px] font-medium text-[#6E6E73]">
                    Attach Real Local Public CT Sample
                  </span>
                  <div className="flex items-center gap-2">
                    <select
                      value={selectedSample}
                      onChange={(e) => setSampleName(e.target.value)}
                      className="flex-1 rounded-xl border border-black/10 bg-[#F5F5F7] px-2.5 py-1.5 text-xs"
                    >
                      {samples.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={handleAttachSample}
                      disabled={uploadingCt}
                      className="rounded-full border border-black/10 px-3 py-1.5 text-xs font-medium hover:bg-[#F5F5F7]"
                    >
                      Attach
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 3D Slicer Mask Correction */}
          {latestCtRun && (
            <div className="border-t border-black/[0.06] pt-5 flex flex-col gap-3">
              <div className="text-xs font-semibold text-[#1D1D1F]">
                3D Slicer Mask Round-Trip
              </div>
              <p className="text-[11px] text-[#6E6E73]">
                Download the NIfTI segmentation mask, refine labels in 3D Slicer, and re-import to recompute all metrics.
              </p>
              <div className="flex items-center gap-2">
                {labelDownloadUrl && (
                  <a
                    href={labelDownloadUrl}
                    download
                    className="inline-flex items-center gap-1.5 rounded-full border border-black/10 px-3 py-1.5 text-xs font-medium hover:bg-[#F5F5F7]"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Mask (.nii.gz)
                  </a>
                )}
                <input
                  ref={maskInputRef}
                  type="file"
                  accept=".nii,.nii.gz"
                  onChange={handleMaskReimport}
                  className="hidden"
                />
                <button
                  onClick={() => maskInputRef.current?.click()}
                  disabled={uploadingMask}
                  className="inline-flex items-center gap-1.5 rounded-full bg-[#1D1D1F] px-3 py-1.5 text-xs font-medium text-white"
                >
                  <UploadCloud className="h-3.5 w-3.5" />
                  {uploadingMask ? "Recomputing…" : "Re-import Mask"}
                </button>
              </div>
            </div>
          )}

          {/* Technical Safeguard Warnings */}
          {latestCtRun?.metrics?.warnings?.length ? (
            <div className="border-t border-black/[0.06] pt-5 flex flex-col gap-2">
              <div className="text-xs font-semibold text-[#1D1D1F]">Imaging Safeguards</div>
              {latestCtRun.metrics.warnings.map((w, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-2 rounded-xl bg-[#FF9F0A]/10 px-3 py-2 text-[11px] text-[#92400E]"
                >
                  <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <span>{w}</span>
                </div>
              ))}
            </div>
          ) : null}

          {/* Provenance Audit Log */}
          <div className="border-t border-black/[0.06] pt-5 flex flex-col gap-2.5">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-[#1D1D1F]">
              <ShieldCheck className="h-4 w-4 text-[#34C759]" />
              Audit Trail
            </div>
            <div className="flex flex-col gap-2 text-[11px]">
              {caseDetail.audit_logs.map((log) => (
                <div key={log.id} className="rounded-xl bg-[#F5F5F7] px-3 py-2">
                  <div className="flex items-center justify-between font-medium text-[#1D1D1F]">
                    <span>{log.action}</span>
                    <span className="text-[10px] text-[#86868B]">{log.actor}</span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-[#6E6E73]">
                    {new Date(log.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
