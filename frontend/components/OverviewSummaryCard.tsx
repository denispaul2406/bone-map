"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp, Sliders } from "lucide-react";
import { CaseDetail, CTRun } from "@/lib/api";

interface OverviewSummaryCardProps {
  caseDetail: CaseDetail;
  ctRun: CTRun;
  onOpenTechnical: () => void;
}

export function OverviewSummaryCard({
  caseDetail,
  ctRun,
  onOpenTechnical,
}: OverviewSummaryCardProps) {
  const [expanded, setExpanded] = useState(false);
  const m = ctRun.metrics;

  if (!m) {
    return (
      <div className="apple-card p-6 text-sm text-[#6E6E73]">
        CT processing is {ctRun.status}…
      </div>
    );
  }

  const isRef = caseDetail.is_intact_reference;
  const verdictLabel = isRef
    ? "Intact Anatomical Reference"
    : m.bridged_quadrants_count >= 3
    ? `Bridging Progressing (${m.bridged_quadrants_count}/4)`
    : m.fracture_gap_mm > 0
    ? `Active Fracture Gap (${m.fracture_gap_mm} mm)`
    : "Quantified 3D Assessment";

  const verdictTone = isRef
    ? "bg-[#0071E3]/10 text-[#0071E3]"
    : m.bridged_quadrants_count >= 3
    ? "bg-[#34C759]/12 text-[#15803D]"
    : "bg-[#FF9F0A]/14 text-[#B45309]";

  return (
    <div className="apple-card p-6 flex flex-col gap-5">
      {/* Calm Header & Verdict */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <span className={`rounded-full px-3 py-1 text-xs font-medium ${verdictTone}`}>
            {verdictLabel}
          </span>
          <span className="text-[11px] text-[#86868B]">{caseDetail.data_source}</span>
        </div>
        <h2 className="text-lg font-semibold tracking-tight text-[#1D1D1F]">
          {caseDetail.fracture_location}
        </h2>
        <p className="text-xs text-[#6E6E73] leading-relaxed">{caseDetail.notes}</p>
      </div>

      {/* Maximum 4 Key Numbers Above the Fold */}
      <div className="grid grid-cols-2 gap-3">
        <HeroMetric
          label="Cortical Thickness"
          value={`${m.cortical_thickness_mean_mm} mm`}
          hint={`Median ${m.cortical_thickness_median_mm} mm`}
        />
        <HeroMetric
          label="Cortical Bridging"
          value={`${m.bridged_quadrants_count} / 4`}
          hint={`${m.overall_cortical_continuity_pct}% continuity`}
        />
        <HeroMetric
          label="Callus Volume"
          value={`${m.total_callus_volume_cm3} cm³`}
          hint={isRef ? "Intact control" : `Hard ${m.hard_callus_volume_cm3} cm³`}
        />
        <HeroMetric
          label="Fracture Gap"
          value={`${m.fracture_gap_mm} mm`}
          hint={`${m.fragment_count} major fragment(s)`}
        />
      </div>

      {/* Quiet 4-Quadrant Status Dots */}
      <div className="flex items-center justify-between rounded-2xl bg-[#F5F5F7] px-4 py-3">
        <span className="text-xs font-medium text-[#6E6E73]">Cortices</span>
        <div className="flex items-center gap-4 text-xs tabular-nums">
          {(["anterior", "posterior", "medial", "lateral"] as const).map((q) => {
            const pct = m.quadrant_continuity_pct[q] ?? 0;
            const ok = pct >= 75;
            return (
              <span key={q} className="flex items-center gap-1.5 text-[#1D1D1F]">
                <span
                  className={`h-2 w-2 rounded-full ${
                    ok ? "bg-[#34C759]" : "bg-[#FF9F0A]"
                  }`}
                />
                <span className="capitalize text-[#6E6E73]">{q.slice(0, 3)}</span>
                <span className="font-medium">{pct}%</span>
              </span>
            );
          })}
        </div>
      </div>

      {/* Real Axial Cortical Thickness Profile Sparkline (Distal -> Proximal) */}
      {m.axial_thickness_profile?.length > 2 && (
        <AxialThicknessSparkline profile={m.axial_thickness_profile} />
      )}

      {/* Progressive Disclosure: Full Technical Report */}
      <div className="border-t border-black/[0.06] pt-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[#0071E3] hover:underline"
          >
            {expanded ? "Hide Full Architecture Metrics" : "View Full Architecture Report (12 metrics)"}
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>

          <button
            onClick={onOpenTechnical}
            className="inline-flex items-center gap-1 text-xs font-medium text-[#6E6E73] hover:text-[#1D1D1F]"
          >
            <Sliders className="h-3.5 w-3.5" />
            3D Slicer & Audit
          </button>
        </div>

        {expanded && (
          <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 rounded-2xl bg-[#F5F5F7]/80 p-4 text-xs tabular-nums">
            <DetailRow label="Cortical HU (mean)" value={`${m.cortical_hu_mean} HU`} />
            <DetailRow label="Cortical HU (IQR)" value={`${m.cortical_hu_iqr} HU`} />
            <DetailRow label="Bone Length" value={`${m.bone_length_mm} mm`} />
            <DetailRow label="Bone Volume" value={`${m.total_bone_volume_cm3} cm³`} />
            <DetailRow label="Coronal Angulation" value={`${m.coronal_angulation_deg}°`} />
            <DetailRow label="Sagittal Angulation" value={`${m.sagittal_angulation_deg}°`} />
            <DetailRow label="Thickness P90" value={`${m.cortical_thickness_p90_mm} mm`} />
            <DetailRow label="Displacement" value={`${m.fragment_displacement_mm} mm`} />
            <DetailRow
              label="Trabecular Tb.Th / Tb.Sp"
              value={
                m.trabecular_status === "measured_high_resolution"
                  ? `${m.trabecular_thickness_mm} / ${m.trabecular_separation_mm} mm`
                  : "Hidden (clinical CT >0.25 mm)"
              }
            />
            <DetailRow label="Voxel Spacing" value={`${m.voxel_spacing_mm.join(" × ")} mm`} />
          </div>
        )}
      </div>
    </div>
  );
}

function HeroMetric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-2xl bg-[#F5F5F7]/90 px-4 py-3.5 border border-black/[0.04]">
      <div className="text-[11px] font-medium text-[#6E6E73]">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-[#1D1D1F]">
        {value}
      </div>
      <div className="mt-0.5 text-[11px] text-[#86868B]">{hint}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-black/[0.04] pb-1.5">
      <span className="text-[#6E6E73]">{label}</span>
      <span className="font-medium text-[#1D1D1F]">{value}</span>
    </div>
  );
}

function AxialThicknessSparkline({
  profile,
}: {
  profile: Array<{ position_mm: number; mean_thickness_mm: number }>;
}) {
  const w = 360;
  const h = 68;
  const padX = 8;
  const padY = 10;
  const maxPos = Math.max(...profile.map((p) => p.position_mm), 1);
  const minPos = Math.min(...profile.map((p) => p.position_mm), 0);
  const maxTh = Math.max(...profile.map((p) => p.mean_thickness_mm), 3.5);
  const pts = profile.map((p) => {
    const x =
      padX + ((p.position_mm - minPos) / Math.max(maxPos - minPos, 1)) * (w - padX * 2);
    const y = h - padY - (p.mean_thickness_mm / maxTh) * (h - padY * 2);
    return { x, y };
  });
  const d = pts
    .map((pt, i) => `${i === 0 ? "M" : "L"} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`)
    .join(" ");
  const area = `${d} L ${pts[pts.length - 1].x.toFixed(1)} ${h - padY} L ${pts[0].x.toFixed(1)} ${h - padY} Z`;

  return (
    <div className="rounded-2xl bg-[#F5F5F7] px-4 py-3">
      <div className="flex items-center justify-between text-[11px] mb-1">
        <span className="font-medium text-[#6E6E73]">
          Axial Cortical Profile (Distal → Proximal)
        </span>
        <span className="tabular-nums text-[#86868B]">
          Peak {Math.max(...profile.map((p) => p.mean_thickness_mm)).toFixed(2)} mm
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-14 overflow-visible">
        <defs>
          <linearGradient id="cortGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#0071E3" stopOpacity="0.24" />
            <stop offset="100%" stopColor="#0071E3" stopOpacity="0.0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#cortGrad)" />
        <path
          d={d}
          fill="none"
          stroke="#0071E3"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
