"use client";

import React from "react";
import { LongitudinalComparison } from "@/lib/api";

interface TrajectoryChartsProps {
  comparison: LongitudinalComparison;
}

export function TrajectoryCharts({ comparison }: TrajectoryChartsProps) {
  const tl = comparison.timeline;
  if (!tl.length) return null;

  const maxDay = Math.max(...tl.map((t) => t.days_post_injury), 90);
  const w = 520;
  const h = 190;
  const padL = 38;
  const padR = 20;
  const padT = 18;
  const padB = 28;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  const xForDay = (d: number) => padL + (d / Math.max(maxDay, 1)) * innerW;

  // Functional series: LEFS (0-80), Pain VAS (0-10 scaled to 0-80), Strength Symmetry % (0-100 scaled to 0-80)
  const lefsPts = tl
    .filter((t) => t.physio?.lefs_score != null)
    .map((t) => ({
      x: xForDay(t.days_post_injury),
      y: padT + innerH - ((t.physio!.lefs_score || 0) / 80) * innerH,
      label: t.timepoint_label,
      val: t.physio!.lefs_score!,
    }));

  const symPts = tl
    .filter((t) => t.physio?.dynamometry_symmetry_pct != null)
    .map((t) => ({
      x: xForDay(t.days_post_injury),
      y: padT + innerH - ((t.physio!.dynamometry_symmetry_pct || 0) / 100) * innerH,
      label: t.timepoint_label,
      val: t.physio!.dynamometry_symmetry_pct!,
    }));

  const painPts = tl
    .filter((t) => t.physio?.pain_vas != null)
    .map((t) => ({
      x: xForDay(t.days_post_injury),
      y: padT + innerH - ((t.physio!.pain_vas || 0) / 10) * innerH,
      label: t.timepoint_label,
      val: t.physio!.pain_vas!,
    }));

  // Structural series: mRUST (4-16) and CT Callus Volume (cm^3)
  const mrustPts = tl
    .filter((t) => t.mrust_total != null)
    .map((t) => ({
      x: xForDay(t.days_post_injury),
      y: padT + innerH - ((t.mrust_total || 4) / 16) * innerH,
      label: t.timepoint_label,
      val: t.mrust_total!,
    }));

  const ctCallusPts = tl
    .filter((t) => t.ct_metrics != null)
    .map((t) => {
      const vol = t.ct_metrics!.total_callus_volume_cm3;
      const maxVol = Math.max(
        20,
        ...tl.map((x) => x.ct_metrics?.total_callus_volume_cm3 || 0)
      );
      return {
        x: xForDay(t.days_post_injury),
        y: padT + innerH - (vol / maxVol) * innerH,
        label: t.timepoint_label,
        val: vol,
      };
    });

  const toPath = (pts: Array<{ x: number; y: number }>) =>
    pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");

  return (
    <div className="flex flex-col gap-4">
      {/* Structured Visit Cards (informative even on 1-visit cases) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {tl.map((t) => (
          <div key={t.assessment_id} className="apple-card p-4 flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-[#1D1D1F]">
                {t.timepoint_label} · Day {t.days_post_injury}
              </span>
              <span className="rounded-full bg-[#F5F5F7] px-2.5 py-0.5 text-[10px] font-medium text-[#6E6E73]">
                {t.ct_metrics ? "3D CT" : t.modality}
              </span>
            </div>
            <div className="text-[11px] text-[#6E6E73]">
              Phase: <strong className="text-[#1D1D1F]">{t.healing_phase || "Recorded"}</strong>
            </div>
            <div className="mt-1 flex flex-wrap gap-3 text-xs tabular-nums text-[#6E6E73]">
              {t.ct_metrics && (
                <span>
                  Cortex <strong className="text-[#1D1D1F]">{t.ct_metrics.cortical_thickness_mean_mm} mm</strong>
                </span>
              )}
              {t.mrust_total != null && (
                <span>
                  mRUST <strong className="text-[#0071E3]">{t.mrust_total}/16</strong>
                </span>
              )}
              {t.physio?.lefs_score != null && (
                <span>
                  LEFS <strong className="text-[#15803D]">{t.physio.lefs_score}/80</strong>
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* Track A & B: Structural Trajectory */}
      <div className="apple-card p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-[#1D1D1F]">Structural Healing Trajectory</h3>
            <p className="text-xs text-[#6E6E73]">Track A (CT Callus cm³) & Track B (X-Ray mRUST /16)</p>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-[#6E6E73]">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-[#F59E0B]" /> Callus (cm³)
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-[#0071E3]" /> mRUST
            </span>
          </div>
        </div>

        <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto">
          {[0, 0.25, 0.5, 0.75, 1].map((f) => {
            const y = padT + f * innerH;
            return (
              <line
                key={f}
                x1={padL}
                x2={w - padR}
                y1={y}
                y2={y}
                stroke="rgba(0,0,0,0.06)"
                strokeDasharray="3 3"
              />
            );
          })}
          {tl.map((t) => (
            <text
              key={t.assessment_id}
              x={xForDay(t.days_post_injury)}
              y={h - 8}
              textAnchor="middle"
              className="fill-[#6E6E73] text-[10px]"
            >
              {t.timepoint_label} (d{t.days_post_injury})
            </text>
          ))}
          {mrustPts.length > 1 && (
            <path d={toPath(mrustPts)} fill="none" stroke="#0071E3" strokeWidth={2.5} strokeLinecap="round" />
          )}
          {ctCallusPts.length > 1 && (
            <path
              d={toPath(ctCallusPts)}
              fill="none"
              stroke="#F59E0B"
              strokeWidth={2.5}
              strokeDasharray="5 4"
              strokeLinecap="round"
            />
          )}
          {mrustPts.map((p, i) => (
            <g key={`mr-${i}`}>
              <circle cx={p.x} cy={p.y} r={4.5} fill="#0071E3" stroke="#fff" strokeWidth={1.5} />
              <text x={p.x} y={p.y - 9} textAnchor="middle" className="fill-[#0071E3] text-[10px] font-semibold">
                {p.val}/16
              </text>
            </g>
          ))}
          {ctCallusPts.map((p, i) => (
            <g key={`cal-${i}`}>
              <circle cx={p.x} cy={p.y} r={4.5} fill="#F59E0B" stroke="#fff" strokeWidth={1.5} />
              <text x={p.x} y={p.y + 15} textAnchor="middle" className="fill-[#B45309] text-[10px] font-semibold">
                {p.val} cm³
              </text>
            </g>
          ))}
        </svg>
      </div>

      {/* Track C: Functional Trajectory */}
      <div className="apple-card p-5">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-[#1D1D1F]">Physiotherapy & Functional Recovery</h3>
            <p className="text-xs text-[#6E6E73]">LEFS (/80), Strength Symmetry (%) & Pain VAS (/10)</p>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-[#6E6E73]">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-[#34C759]" /> LEFS
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-[#5856D6]" /> Strength %
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-[#FF3B30]" /> Pain
            </span>
          </div>
        </div>

        <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto">
          {[0, 0.25, 0.5, 0.75, 1].map((f) => {
            const y = padT + f * innerH;
            return (
              <line
                key={f}
                x1={padL}
                x2={w - padR}
                y1={y}
                y2={y}
                stroke="rgba(0,0,0,0.06)"
                strokeDasharray="3 3"
              />
            );
          })}
          {tl.map((t) => (
            <text
              key={t.assessment_id}
              x={xForDay(t.days_post_injury)}
              y={h - 8}
              textAnchor="middle"
              className="fill-[#6E6E73] text-[10px]"
            >
              {t.timepoint_label} (d{t.days_post_injury})
            </text>
          ))}
          {lefsPts.length > 1 && (
            <path d={toPath(lefsPts)} fill="none" stroke="#34C759" strokeWidth={2.5} strokeLinecap="round" />
          )}
          {symPts.length > 1 && (
            <path d={toPath(symPts)} fill="none" stroke="#5856D6" strokeWidth={2} strokeLinecap="round" />
          )}
          {painPts.length > 1 && (
            <path d={toPath(painPts)} fill="none" stroke="#FF3B30" strokeWidth={2} strokeDasharray="4 4" strokeLinecap="round" />
          )}
          {lefsPts.map((p, i) => (
            <g key={`lefs-${i}`}>
              <circle cx={p.x} cy={p.y} r={4.5} fill="#34C759" stroke="#fff" strokeWidth={1.5} />
              <text x={p.x} y={p.y - 9} textAnchor="middle" className="fill-[#15803D] text-[10px] font-semibold">
                {p.val}
              </text>
            </g>
          ))}
          {painPts.map((p, i) => (
            <circle key={`pain-${i}`} cx={p.x} cy={p.y} r={3.5} fill="#FF3B30" stroke="#fff" strokeWidth={1.2} />
          ))}
        </svg>
      </div>
    </div>
    </div>
  );
}
