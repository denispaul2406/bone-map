"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Box,
  ChevronDown,
  Database,
  GitCompareArrows,
  Layers,
  Plus,
  RefreshCw,
  SlidersHorizontal,
  X,
} from "lucide-react";
import {
  API_BASE,
  Assessment,
  CaseDetail,
  CohortAnalytics,
  DashboardData,
  HealthResponse,
  LongitudinalComparison,
  api,
} from "@/lib/api";
import { Bone3DViewer } from "@/components/Bone3DViewer";
import { CTSliceViewer } from "@/components/CTSliceViewer";
import { OverviewSummaryCard } from "@/components/OverviewSummaryCard";
import { RealXRayWorkspace } from "@/components/RealXRayWorkspace";
import { TrajectoryCharts } from "@/components/TrajectoryCharts";
import { PhysioForm } from "@/components/PhysioForm";
import { TechnicalDrawer } from "@/components/TechnicalDrawer";

type Mode = "overview" | "timeline" | "physio";

export default function BoneMapWorkspace() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [cohortStats, setCohortStats] = useState<CohortAnalytics | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const selectedCaseIdRef = useRef<string | null>(null);
  selectedCaseIdRef.current = selectedCaseId;

  const [caseDetail, setCaseDetail] = useState<CaseDetail | null>(null);
  const [comparison, setComparison] = useState<LongitudinalComparison | null>(null);
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<number | null>(null);

  const [mode, setMode] = useState<Mode>("overview");
  const [caseMenuOpen, setCaseMenuOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [slicesModalOpen, setSlicesModalOpen] = useState(false);
  const [showNewCaseModal, setShowNewCaseModal] = useState(false);
  const [showNewVisitModal, setShowNewVisitModal] = useState(false);
  const [importingReal, setImportingReal] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadReqCounter = useRef(0);
  const caseMenuRef = useRef<HTMLDivElement | null>(null);

  const loadDashboard = useCallback(async (preferCaseId?: string) => {
    try {
      const [h, d, c] = await Promise.all([
        api.health(),
        api.dashboard(),
        api.cohortAnalytics(),
      ]);
      setHealth(h);
      setDashboard(d);
      setCohortStats(c);
      setErrorMsg(null);
      const currentId = selectedCaseIdRef.current;
      const targetId =
        preferCaseId ||
        (currentId && d.cases.some((x) => x.id === currentId)
          ? currentId
          : d.cases[0]?.id || null);
      setSelectedCaseId(targetId);
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? `Backend unreachable at ${API_BASE}: ${err.message}`
          : "Connection error"
      );
    }
  }, []);

  const loadCase = useCallback(async (caseId: string) => {
    const reqId = ++loadReqCounter.current;
    try {
      const [detail, comp] = await Promise.all([
        api.getCase(caseId),
        api.compareCase(caseId),
      ]);
      if (reqId !== loadReqCounter.current) return;
      setCaseDetail(detail);
      setComparison(comp);
      setErrorMsg(null);
      if (detail.assessments.length > 0) {
        setSelectedAssessmentId((prev) => {
          if (prev && detail.assessments.some((a) => a.id === prev)) return prev;
          const withCt = detail.assessments.find((a) =>
            a.ct_runs.some((r) => r.status === "completed")
          );
          return withCt ? withCt.id : detail.assessments[0].id;
        });
      } else {
        setSelectedAssessmentId(null);
      }
    } catch (err) {
      if (reqId !== loadReqCounter.current) return;
      setErrorMsg(err instanceof Error ? err.message : "Failed to load case.");
    }
  }, []);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  useEffect(() => {
    if (selectedCaseId) {
      loadCase(selectedCaseId);
    } else {
      setCaseDetail(null);
      setComparison(null);
    }
  }, [selectedCaseId, loadCase]);

  // Close case switcher & slice modal on Escape or outside click
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setCaseMenuOpen(false);
        setSlicesModalOpen(false);
      }
    };
    const onDown = (e: MouseEvent) => {
      if (caseMenuRef.current && !caseMenuRef.current.contains(e.target as Node)) {
        setCaseMenuOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, []);

  const selectedAssessment: Assessment | null = useMemo(() => {
    if (!caseDetail || selectedAssessmentId == null) return null;
    return caseDetail.assessments.find((a) => a.id === selectedAssessmentId) || null;
  }, [caseDetail, selectedAssessmentId]);

  const latestCtRun = useMemo(() => {
    if (!selectedAssessment) return null;
    return selectedAssessment.ct_runs[0] || null;
  }, [selectedAssessment]);

  const lastCompletedCtRun = useMemo(() => {
    if (!selectedAssessment) return null;
    return selectedAssessment.ct_runs.find((r) => r.status === "completed") || null;
  }, [selectedAssessment]);

  const ctRunId = latestCtRun?.id;
  const ctRunStatus = latestCtRun?.status;

  useEffect(() => {
    if (!ctRunId || !ctRunStatus || !["queued", "running"].includes(ctRunStatus)) return;
    const timer = setInterval(() => {
      if (selectedCaseIdRef.current) loadCase(selectedCaseIdRef.current);
    }, 2000);
    return () => clearInterval(timer);
  }, [ctRunId, ctRunStatus, loadCase]);

  const handleImportRealDatasets = async () => {
    setImportingReal(true);
    setErrorMsg(null);
    try {
      const res = await api.seedRealDatasets();
      const firstId = res.cases?.[0];
      await loadDashboard(firstId);
      if (firstId) {
        await loadCase(firstId);
      }
      setCaseMenuOpen(false);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Failed to import public datasets.");
    } finally {
      setImportingReal(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#F5F5F7] text-[#1D1D1F]">
      {/* Single Calm Frosted Header (56 px) */}
      <header className="apple-glass sticky top-0 z-30 border-b border-black/[0.06]">
        <div className="mx-auto flex h-14 max-w-[1380px] items-center justify-between gap-4 px-6">
          {/* Left: Wordmark + Case Switcher Popover */}
          <div className="flex items-center gap-3 relative" ref={caseMenuRef}>
            <div className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-[#1D1D1F] text-white">
              <Box className="h-4 w-4" />
            </div>
            <span className="text-sm font-semibold tracking-tight text-[#1D1D1F]">
              BONE-MAP
            </span>

            {dashboard && (
              <div className="relative">
                <button
                  onClick={() => setCaseMenuOpen((o) => !o)}
                  aria-expanded={caseMenuOpen}
                  aria-haspopup="menu"
                  className="inline-flex items-center gap-2 rounded-full bg-black/[0.05] hover:bg-black/[0.08] px-3.5 py-1.5 text-xs font-medium text-[#1D1D1F] transition"
                >
                  <span className="tabular-nums font-semibold">
                    {caseDetail ? caseDetail.id : "Select Patient"}
                  </span>
                  {caseDetail?.ao_classification && (
                    <span className="hidden sm:inline text-[#6E6E73]">
                      · {caseDetail.ao_classification}
                    </span>
                  )}
                  <ChevronDown className="h-3.5 w-3.5 text-[#6E6E73]" />
                </button>

                {caseMenuOpen && (
                  <div
                    role="menu"
                    className="absolute left-0 mt-2 w-80 rounded-2xl bg-white p-2 shadow-xl border border-black/[0.08] z-50"
                  >
                    <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-[#86868B]">
                      Patients ({dashboard.cases.length})
                    </div>
                    <div className="max-h-72 overflow-y-auto flex flex-col gap-1">
                      {dashboard.cases.map((c) => {
                        const active = c.id === selectedCaseId;
                        return (
                          <button
                            key={c.id}
                            onClick={() => {
                              setSelectedCaseId(c.id);
                              setCaseMenuOpen(false);
                            }}
                            className={`w-full rounded-xl px-3 py-2 text-left transition ${
                              active ? "bg-[#0071E3] text-white" : "hover:bg-[#F5F5F7]"
                            }`}
                          >
                            <div className="flex items-center justify-between text-xs font-semibold">
                              <span className="tabular-nums">{c.id}</span>
                              <span
                                className={`text-[10px] font-normal ${
                                  active ? "text-white/80" : "text-[#6E6E73]"
                                }`}
                              >
                                {c.ao_classification}
                              </span>
                            </div>
                            <div
                              className={`text-[11px] truncate ${
                                active ? "text-white/85" : "text-[#6E6E73]"
                              }`}
                            >
                              {c.data_source}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                    <div className="mt-2 pt-2 border-t border-black/[0.06] flex items-center justify-between gap-2 px-1">
                      <button
                        onClick={() => {
                          setCaseMenuOpen(false);
                          setShowNewCaseModal(true);
                        }}
                        className="inline-flex items-center gap-1 rounded-full bg-[#0071E3] px-3 py-1.5 text-xs font-medium text-white"
                      >
                        <Plus className="h-3.5 w-3.5" /> New Case
                      </button>
                      <button
                        onClick={handleImportRealDatasets}
                        disabled={importingReal}
                        className="inline-flex items-center gap-1 rounded-full bg-[#F5F5F7] px-3 py-1.5 text-xs font-medium text-[#1D1D1F] hover:bg-black/10"
                      >
                        <Database className="h-3.5 w-3.5" />
                        {importingReal ? "Importing…" : "Sync Public Data"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Center: 3 Calm Mode Pills */}
          {caseDetail && (
            <div className="hidden md:flex rounded-full bg-black/[0.05] p-1">
              {(
                [
                  ["overview", "Overview", Box],
                  ["timeline", "Timeline", GitCompareArrows],
                  ["physio", "Physiotherapy", Activity],
                ] as Array<[Mode, string, React.ElementType]>
              ).map(([id, label, Icon]) => (
                <button
                  key={id}
                  onClick={() => setMode(id)}
                  className={`inline-flex items-center gap-1.5 rounded-full px-4 py-1 text-xs font-medium transition ${
                    mode === id
                      ? "bg-white text-[#1D1D1F] shadow-xs"
                      : "text-[#6E6E73] hover:text-[#1D1D1F]"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {label}
                </button>
              ))}
            </div>
          )}

          {/* Right: Quiet Technical Drawer Trigger & New Case */}
          <div className="flex items-center gap-2">
            {caseDetail && (
              <button
                onClick={() => setDrawerOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-full border border-black/10 bg-white px-3.5 py-1.5 text-xs font-medium text-[#1D1D1F] hover:bg-[#F5F5F7] transition"
              >
                <SlidersHorizontal className="h-3.5 w-3.5 text-[#6E6E73]" />
                Data & Tools
              </button>
            )}
            <button
              onClick={() => setShowNewCaseModal(true)}
              className="inline-flex items-center gap-1 rounded-full bg-[#0071E3] px-3.5 py-1.5 text-xs font-medium text-white hover:bg-[#0062C4] transition"
            >
              <Plus className="h-3.5 w-3.5" />
              New
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto w-full max-w-[1380px] flex-1 px-6 py-6 flex flex-col gap-5">
        {errorMsg && (
          <div className="rounded-2xl border border-[#FF3B30]/20 bg-[#FF3B30]/10 px-4 py-3 text-xs text-[#B91C1C]">
            {errorMsg}
          </div>
        )}

        {/* Mobile mode switcher */}
        {caseDetail && (
          <div className="flex md:hidden rounded-full bg-black/[0.05] p-1 self-start">
            {(
              [
                ["overview", "Overview"],
                ["timeline", "Timeline"],
                ["physio", "Physio"],
              ] as Array<[Mode, string]>
            ).map(([id, label]) => (
              <button
                key={id}
                onClick={() => setMode(id)}
                className={`rounded-full px-3.5 py-1 text-xs font-medium transition ${
                  mode === id ? "bg-white text-[#1D1D1F] shadow-xs" : "text-[#6E6E73]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {/* Empty State */}
        {dashboard && dashboard.cases.length === 0 && (
          <div className="apple-card p-16 text-center flex flex-col items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#0071E3]/10 text-[#0071E3]">
              <Layers className="h-7 w-7" />
            </div>
            <div className="max-w-md">
              <h2 className="text-lg font-semibold text-[#1D1D1F]">
                Load real clinical datasets or create a case
              </h2>
              <p className="mt-1.5 text-sm text-[#6E6E73]">
                Import the real VSDFullBody 3D lower-limb CT and PlaTiF tibial fracture radiographs already on disk, or upload your own patient scan.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleImportRealDatasets}
                disabled={importingReal}
                className="rounded-full bg-[#0071E3] px-5 py-2.5 text-xs font-medium text-white hover:bg-[#0062C4]"
              >
                {importingReal ? "Importing Real Data…" : "Load Real Public Datasets"}
              </button>
              <button
                onClick={() => setShowNewCaseModal(true)}
                className="rounded-full border border-black/10 bg-white px-5 py-2.5 text-xs font-medium text-[#1D1D1F]"
              >
                Create Patient Case
              </button>
            </div>
          </div>
        )}

        {/* Subtle Patient Sub-header + Visit Pills */}
        {caseDetail && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 text-xs text-[#6E6E73]">
              <span className="font-semibold text-[#1D1D1F]">{caseDetail.id}</span>
              <span>·</span>
              <span>
                {caseDetail.age ? `${caseDetail.age} yrs` : "Age N/A"}
                {caseDetail.sex ? ` ${caseDetail.sex}` : ""}
              </span>
              {caseDetail.fixation_type && caseDetail.fixation_type !== "None" && (
                <>
                  <span>·</span>
                  <span>{caseDetail.fixation_type}</span>
                </>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {caseDetail.assessments.map((a) => {
                const active = a.id === selectedAssessmentId;
                const hasCtDone = a.ct_runs.some((r) => r.status === "completed");
                return (
                  <button
                    key={a.id}
                    onClick={() => setSelectedAssessmentId(a.id)}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                      active
                        ? "bg-[#1D1D1F] text-white"
                        : "bg-white text-[#6E6E73] border border-black/[0.06] hover:text-[#1D1D1F]"
                    }`}
                  >
                    {a.timepoint_label} · Day {a.days_post_injury} ({hasCtDone ? "3D CT" : a.modality})
                  </button>
                );
              })}
              <button
                onClick={() => setShowNewVisitModal(true)}
                className="inline-flex items-center gap-1 rounded-full bg-white px-3 py-1 text-xs font-medium text-[#0071E3] border border-black/[0.06] hover:bg-[#0071E3]/5"
              >
                <Plus className="h-3 w-3" /> Add Visit
              </button>
            </div>
          </div>
        )}

        {/* MODE 1: OVERVIEW (Hero View — Max 4 numbers above fold) */}
        {caseDetail && mode === "overview" && (
          <>
            {!selectedAssessment ? (
              <div className="apple-card p-12 text-center flex flex-col items-center gap-3">
                <div className="text-sm font-semibold text-[#1D1D1F]">
                  No imaging visits recorded for {caseDetail.id}
                </div>
                <p className="text-xs text-[#6E6E73]">
                  Add a baseline visit (CT or X-ray) to start quantifying bone architecture.
                </p>
                <button
                  onClick={() => setShowNewVisitModal(true)}
                  className="rounded-full bg-[#0071E3] px-4 py-2 text-xs font-medium text-white"
                >
                  Add First Visit
                </button>
              </div>
            ) : latestCtRun?.status === "failed" ? (
              <div className="flex flex-col gap-4">
                <div className="rounded-2xl border border-[#FF3B30]/25 bg-[#FF3B30]/8 p-5 flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 text-[#DC2626] shrink-0 mt-0.5" />
                    <div>
                      <div className="text-sm font-semibold text-[#991B1B]">
                        CT Reconstruction Failed ({selectedAssessment.timepoint_label})
                      </div>
                      <p className="mt-1 text-xs text-[#B91C1C]">
                        {latestCtRun.error_message || "Unknown processing error."}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => setDrawerOpen(true)}
                    className="shrink-0 rounded-full bg-[#1D1D1F] px-3.5 py-1.5 text-xs font-medium text-white"
                  >
                    Re-upload Scan
                  </button>
                </div>
                {lastCompletedCtRun && (
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                    <div className="lg:col-span-7">
                      <Bone3DViewer
                        ctRun={lastCompletedCtRun}
                        onOpenSlices={() => setSlicesModalOpen(true)}
                      />
                    </div>
                    <div className="lg:col-span-5">
                      <OverviewSummaryCard
                        caseDetail={caseDetail}
                        ctRun={lastCompletedCtRun}
                        onOpenTechnical={() => setDrawerOpen(true)}
                      />
                    </div>
                  </div>
                )}
              </div>
            ) : latestCtRun && latestCtRun.status === "completed" ? (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                <div className="lg:col-span-7">
                  <Bone3DViewer
                    ctRun={latestCtRun}
                    onOpenSlices={() => setSlicesModalOpen(true)}
                  />
                </div>
                <div className="lg:col-span-5">
                  <OverviewSummaryCard
                    caseDetail={caseDetail}
                    ctRun={latestCtRun}
                    onOpenTechnical={() => setDrawerOpen(true)}
                  />
                </div>
              </div>
            ) : latestCtRun && ["queued", "running"].includes(latestCtRun.status) ? (
              <div className="apple-card p-16 flex flex-col items-center justify-center gap-3 text-center">
                <RefreshCw className="h-6 w-6 animate-spin text-[#0071E3]" />
                <div className="text-sm font-medium text-[#1D1D1F]">
                  Reconstructing 3D bone & quantifying architecture…
                </div>
                <p className="text-xs text-[#6E6E73]">
                  Sequential local processing active (RTX 4050 · 6 GB VRAM safeguard)
                </p>
              </div>
            ) : selectedAssessment.modality === "XRAY" ||
              selectedAssessment.xray_ap_url ||
              selectedAssessment.xray_lat_url ||
              selectedAssessment.coronal_ct_2d_url ? (
              <RealXRayWorkspace
                caseDetail={caseDetail}
                assessment={selectedAssessment}
                onUpdated={() => loadCase(caseDetail.id)}
                onOpenTechnical={() => setDrawerOpen(true)}
              />
            ) : (
              <div className="apple-card p-12 text-center flex flex-col items-center gap-3">
                <div className="text-sm font-semibold text-[#1D1D1F]">
                  No scan attached to {selectedAssessment.timepoint_label}
                </div>
                <p className="text-xs text-[#6E6E73]">
                  Open Data & Tools to upload a 3D CT (.nii/.nii.gz or DICOM .zip) or attach a real public CT sample.
                </p>
                <button
                  onClick={() => setDrawerOpen(true)}
                  className="rounded-full bg-[#0071E3] px-4 py-2 text-xs font-medium text-white"
                >
                  Upload Imaging Scan
                </button>
              </div>
            )}
          </>
        )}

        {/* MODE 2: TIMELINE & COHORT BENCHMARK */}
        {caseDetail && mode === "timeline" && (
          <div className="flex flex-col gap-5">
            {cohortStats && (
              <div className="apple-card px-5 py-3.5 flex flex-wrap items-center justify-between gap-4 text-xs">
                <span className="font-semibold text-[#1D1D1F]">
                  Cohort Summary ({cohortStats.total_cases} real cases)
                </span>
                <div className="flex flex-wrap items-center gap-5 tabular-nums text-[#6E6E73]">
                  <span>
                    Mean Cortical Thickness:{" "}
                    <strong className="text-[#1D1D1F]">
                      {cohortStats.mean_cortical_thickness_mm != null
                        ? `${cohortStats.mean_cortical_thickness_mm} mm`
                        : "—"}
                    </strong>
                  </span>
                  <span>
                    Mean mRUST:{" "}
                    <strong className="text-[#1D1D1F]">
                      {cohortStats.mean_mrust_total != null
                        ? `${cohortStats.mean_mrust_total}/16`
                        : "—"}
                    </strong>
                  </span>
                  <span>
                    Mean LEFS:{" "}
                    <strong className="text-[#1D1D1F]">
                      {cohortStats.mean_lefs_score != null
                        ? `${cohortStats.mean_lefs_score}/80`
                        : "—"}
                    </strong>
                  </span>
                </div>
              </div>
            )}

            {!comparison ? (
              <div className="apple-card p-8 text-xs text-[#6E6E73]">
                Loading longitudinal timeline…
              </div>
            ) : comparison.ct_comparison ? (
              <div className="apple-card p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-[#0071E3]">
                      Registered CT Comparison
                    </span>
                    <h3 className="text-base font-semibold text-[#1D1D1F]">
                      {comparison.ct_comparison.baseline_timepoint} vs.{" "}
                      {comparison.ct_comparison.followup_timepoint}
                    </h3>
                  </div>
                  <span className="rounded-full bg-[#34C759]/12 px-3 py-1 text-xs font-medium text-[#15803D]">
                    Dice {comparison.ct_comparison.deltas.dice_bone_overlap}
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 tabular-nums">
                  <DeltaTile
                    label="Callus Volume"
                    from={`${comparison.ct_comparison.deltas.callus_volume_baseline_cm3} cm³`}
                    to={`${comparison.ct_comparison.deltas.callus_volume_followup_cm3} cm³`}
                  />
                  <DeltaTile
                    label="Cortical Thickness"
                    from={`${comparison.ct_comparison.deltas.cortical_thickness_baseline_mm} mm`}
                    to={`${comparison.ct_comparison.deltas.cortical_thickness_followup_mm} mm`}
                  />
                  <DeltaTile
                    label="Fracture Gap"
                    from={`${comparison.ct_comparison.deltas.fracture_gap_baseline_mm} mm`}
                    to={`${comparison.ct_comparison.deltas.fracture_gap_followup_mm} mm`}
                  />
                  <DeltaTile
                    label="Bridged Cortices"
                    from={`${comparison.ct_comparison.deltas.bridged_quadrants_baseline}/4`}
                    to={`${comparison.ct_comparison.deltas.bridged_quadrants_followup}/4`}
                  />
                </div>
              </div>
            ) : (
              <div className="apple-card p-5 text-xs text-[#6E6E73]">
                {comparison.modality_note} Add a follow-up visit to track structural and physiotherapy changes over time.
              </div>
            )}
            {comparison && <TrajectoryCharts comparison={comparison} />}
          </div>
        )}

        {/* MODE 3: PHYSIOTHERAPY */}
        {caseDetail && mode === "physio" && (
          <div className="mx-auto w-full max-w-4xl">
            {selectedAssessment ? (
              <PhysioForm
                assessment={selectedAssessment}
                onSaved={() => {
                  loadCase(caseDetail.id);
                  loadDashboard();
                }}
              />
            ) : (
              <div className="apple-card p-10 text-center flex flex-col items-center gap-3">
                <div className="text-sm font-semibold text-[#1D1D1F]">
                  No visit selected for Physiotherapy
                </div>
                <p className="text-xs text-[#6E6E73]">
                  Add a visit to record LEFS, pain VAS, dynamometry, ROM, TUG, and gait.
                </p>
                <button
                  onClick={() => setShowNewVisitModal(true)}
                  className="rounded-full bg-[#0071E3] px-4 py-2 text-xs font-medium text-white"
                >
                  Add Visit
                </button>
              </div>
            )}
          </div>
        )}
      </main>

      {/* 2D CT Slices Modal */}
      {slicesModalOpen && (lastCompletedCtRun || latestCtRun) && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="2D Multi-Planar CT Slices"
          onClick={() => setSlicesModalOpen(false)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-2xl relative"
          >
            <button
              onClick={() => setSlicesModalOpen(false)}
              aria-label="Close 2D slice viewer"
              className="absolute right-3 top-3 z-10 rounded-full bg-black/10 p-1.5 text-[#1D1D1F] hover:bg-black/20"
            >
              <X className="h-4 w-4" />
            </button>
            <CTSliceViewer ctRun={(lastCompletedCtRun || latestCtRun)!} />
          </div>
        </div>
      )}

      {/* Slide-Over Engineering & Upload Drawer */}
      {caseDetail && (
        <TechnicalDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          health={health}
          caseDetail={caseDetail}
          assessment={selectedAssessment}
          latestCtRun={lastCompletedCtRun || latestCtRun}
          onUpdated={() => {
            loadCase(caseDetail.id);
            loadDashboard();
          }}
        />
      )}

      {showNewCaseModal && (
        <NewCaseModal
          onClose={() => setShowNewCaseModal(false)}
          onCreated={async (id) => {
            setShowNewCaseModal(false);
            await loadDashboard(id);
          }}
        />
      )}

      {showNewVisitModal && caseDetail && (
        <NewVisitModal
          caseId={caseDetail.id}
          onClose={() => setShowNewVisitModal(false)}
          onCreated={async (newId, createdModality) => {
            setShowNewVisitModal(false);
            await loadCase(caseDetail.id);
            setSelectedAssessmentId(newId);
            if (createdModality === "CT") {
              setDrawerOpen(true);
            } else if (createdModality === "PHYSIO_ONLY") {
              setMode("physio");
            } else {
              setMode("overview");
            }
          }}
        />
      )}
    </div>
  );
}

function DeltaTile({ label, from, to }: { label: string; from: string; to: string }) {
  return (
    <div className="rounded-2xl bg-[#F5F5F7] p-3.5">
      <div className="text-[11px] text-[#6E6E73]">{label}</div>
      <div className="mt-1 text-sm font-semibold text-[#1D1D1F]">
        {from} → {to}
      </div>
    </div>
  );
}

function NewCaseModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => Promise<void>;
}) {
  const [form, setForm] = useState({
    id: `BM-${Math.floor(1000 + Math.random() * 9000)}`,
    age: "",
    sex: "M",
    fracture_location: "Tibial shaft",
    ao_classification: "42-B2",
    open_closed: "Closed",
    fixation_type: "Intramedullary nail",
    is_intact_reference: false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.createCase({
        ...form,
        age: form.age ? Number(form.age) : null,
      });
      await onCreated(form.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create case.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="New Patient Case"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-xs p-4"
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="apple-card w-full max-w-md p-6 flex flex-col gap-4"
      >
        <h2 className="text-base font-semibold text-[#1D1D1F]">New Patient Case</h2>
        {error && (
          <div className="rounded-xl bg-[#FF3B30]/10 px-3 py-2 text-xs text-[#B91C1C]">
            {error}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Research ID</span>
            <input
              required
              pattern="[A-Za-z0-9_-]{2,32}"
              title="Letters, numbers, hyphens, or underscores only"
              value={form.id}
              onChange={(e) => setForm({ ...form, id: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">AO/OTA or Schatzker</span>
            <input
              value={form.ao_classification}
              onChange={(e) => setForm({ ...form, ao_classification: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Age</span>
            <input
              type="number"
              min={0}
              max={120}
              placeholder="Optional"
              value={form.age}
              onChange={(e) => setForm({ ...form, age: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Sex</span>
            <select
              value={form.sex}
              onChange={(e) => setForm({ ...form, sex: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            >
              <option value="M">Male</option>
              <option value="F">Female</option>
              <option value="Other">Other</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Injury Type</span>
            <select
              value={form.open_closed}
              onChange={(e) => setForm({ ...form, open_closed: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            >
              <option>Closed</option>
              <option>Open</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Fixation</span>
            <select
              value={form.fixation_type}
              onChange={(e) => setForm({ ...form, fixation_type: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            >
              <option>Intramedullary nail</option>
              <option>Locking plate</option>
              <option>External fixator</option>
              <option>Conservative</option>
              <option>None</option>
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-[#6E6E73]">Location</span>
          <input
            value={form.fracture_location}
            onChange={(e) => setForm({ ...form, fracture_location: e.target.value })}
            className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
          />
        </label>
        <label className="flex items-center gap-2 text-xs text-[#6E6E73]">
          <input
            type="checkbox"
            checked={form.is_intact_reference}
            onChange={(e) => setForm({ ...form, is_intact_reference: e.target.checked })}
          />
          Intact anatomical reference / healthy control scan
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full px-4 py-2 text-xs text-[#6E6E73] hover:bg-black/5"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-full bg-[#0071E3] px-4 py-2 text-xs font-medium text-white disabled:opacity-50"
          >
            {submitting ? "Creating…" : "Create Case"}
          </button>
        </div>
      </form>
    </div>
  );
}

function NewVisitModal({
  caseId,
  onClose,
  onCreated,
}: {
  caseId: string;
  onClose: () => void;
  onCreated: (assessmentId: number, modality: string) => Promise<void>;
}) {
  const [form, setForm] = useState({
    timepoint_label: "T0",
    days_post_injury: "0",
    modality: "CT",
    healing_phase: "Inflammatory",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.createAssessment(caseId, {
        ...form,
        days_post_injury: Number(form.days_post_injury),
      });
      await onCreated(created.id, form.modality);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create visit.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Add Visit"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-xs p-4"
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
        className="apple-card w-full max-w-sm p-6 flex flex-col gap-4"
      >
        <h2 className="text-base font-semibold text-[#1D1D1F]">Add Visit ({caseId})</h2>
        {error && (
          <div className="rounded-xl bg-[#FF3B30]/10 px-3 py-2 text-xs text-[#B91C1C]">
            {error}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Timepoint</span>
            <input
              required
              value={form.timepoint_label}
              onChange={(e) => setForm({ ...form, timepoint_label: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Days Post-Injury</span>
            <input
              type="number"
              min={0}
              max={3650}
              required
              value={form.days_post_injury}
              onChange={(e) => setForm({ ...form, days_post_injury: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Primary Modality</span>
            <select
              value={form.modality}
              onChange={(e) => setForm({ ...form, modality: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            >
              <option value="CT">CT (3D Architecture)</option>
              <option value="XRAY">X-ray + mRUST</option>
              <option value="PHYSIO_ONLY">Physiotherapy Only</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[#6E6E73]">Healing Phase</span>
            <select
              value={form.healing_phase}
              onChange={(e) => setForm({ ...form, healing_phase: e.target.value })}
              className="rounded-xl border border-black/10 bg-[#F5F5F7] px-3 py-2"
            >
              <option>Inflammatory</option>
              <option>Soft Callus</option>
              <option>Hard Callus</option>
              <option>Remodelling</option>
            </select>
          </label>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full px-4 py-2 text-xs text-[#6E6E73] hover:bg-black/5"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-full bg-[#0071E3] px-4 py-2 text-xs font-medium text-white disabled:opacity-50"
          >
            {submitting ? "Adding…" : "Add Visit"}
          </button>
        </div>
      </form>
    </div>
  );
}
