"use client";

import React, { useEffect, useRef, useState } from "react";
import { Check } from "lucide-react";
import { api, Assessment } from "@/lib/api";

interface PhysioFormProps {
  assessment: Assessment;
  onSaved: () => void;
}

export function PhysioForm({ assessment, onSaved }: PhysioFormProps) {
  const p = assessment.physio;
  const [form, setForm] = useState({
    mmt_score: p?.mmt_score?.toString() ?? "",
    dynamometry_injured_n: p?.dynamometry_injured_n?.toString() ?? "",
    dynamometry_contralateral_n: p?.dynamometry_contralateral_n?.toString() ?? "",
    knee_flexion_deg: p?.knee_flexion_deg?.toString() ?? "",
    knee_extension_deg: p?.knee_extension_deg?.toString() ?? "",
    ankle_dorsiflexion_deg: p?.ankle_dorsiflexion_deg?.toString() ?? "",
    ankle_plantarflexion_deg: p?.ankle_plantarflexion_deg?.toString() ?? "",
    pain_vas: p?.pain_vas?.toString() ?? "",
    gait_speed_ms: p?.gait_speed_ms?.toString() ?? "",
    gait_cadence_spm: p?.gait_cadence_spm?.toString() ?? "",
    gait_symmetry_pct: p?.gait_symmetry_pct?.toString() ?? "",
    tug_seconds: p?.tug_seconds?.toString() ?? "",
    lefs_score: p?.lefs_score?.toString() ?? "",
    weight_bearing_status: p?.weight_bearing_status ?? "Partial weight bearing (50%)",
    notes: p?.notes ?? "",
  });

  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const np = assessment.physio;
    setForm({
      mmt_score: np?.mmt_score?.toString() ?? "",
      dynamometry_injured_n: np?.dynamometry_injured_n?.toString() ?? "",
      dynamometry_contralateral_n: np?.dynamometry_contralateral_n?.toString() ?? "",
      knee_flexion_deg: np?.knee_flexion_deg?.toString() ?? "",
      knee_extension_deg: np?.knee_extension_deg?.toString() ?? "",
      ankle_dorsiflexion_deg: np?.ankle_dorsiflexion_deg?.toString() ?? "",
      ankle_plantarflexion_deg: np?.ankle_plantarflexion_deg?.toString() ?? "",
      pain_vas: np?.pain_vas?.toString() ?? "",
      gait_speed_ms: np?.gait_speed_ms?.toString() ?? "",
      gait_cadence_spm: np?.gait_cadence_spm?.toString() ?? "",
      gait_symmetry_pct: np?.gait_symmetry_pct?.toString() ?? "",
      tug_seconds: np?.tug_seconds?.toString() ?? "",
      lefs_score: np?.lefs_score?.toString() ?? "",
      weight_bearing_status: np?.weight_bearing_status ?? "Partial weight bearing (50%)",
      notes: np?.notes ?? "",
    });
    setSaveError(null);
    setSavedToast(false);
  }, [assessment]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const numOrNull = (s: string) => (s.trim() === "" ? null : Number(s));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    try {
      await api.upsertPhysio(assessment.id, {
        mmt_score: numOrNull(form.mmt_score),
        dynamometry_injured_n: numOrNull(form.dynamometry_injured_n),
        dynamometry_contralateral_n: numOrNull(form.dynamometry_contralateral_n),
        knee_flexion_deg: numOrNull(form.knee_flexion_deg),
        knee_extension_deg: numOrNull(form.knee_extension_deg),
        ankle_dorsiflexion_deg: numOrNull(form.ankle_dorsiflexion_deg),
        ankle_plantarflexion_deg: numOrNull(form.ankle_plantarflexion_deg),
        pain_vas: numOrNull(form.pain_vas),
        gait_speed_ms: numOrNull(form.gait_speed_ms),
        gait_cadence_spm: numOrNull(form.gait_cadence_spm),
        gait_symmetry_pct: numOrNull(form.gait_symmetry_pct),
        tug_seconds: numOrNull(form.tug_seconds),
        lefs_score: numOrNull(form.lefs_score),
        weight_bearing_status: form.weight_bearing_status || null,
        notes: form.notes || null,
      });
      setSavedToast(true);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setSavedToast(false), 2200);
      onSaved();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save assessment.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="apple-card p-6 flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[#0071E3]">
            Physiotherapy & Functional Outcome
          </span>
          <h3 className="text-base font-semibold text-[#1D1D1F]">
            Visit {assessment.timepoint_label} · Day {assessment.days_post_injury}
          </h3>
        </div>
        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-full bg-[#0071E3] px-4 py-2 text-xs font-medium text-white hover:bg-[#0062C4] transition disabled:opacity-50"
        >
          {savedToast ? (
            <>
              <Check className="h-3.5 w-3.5" /> Saved
            </>
          ) : saving ? (
            "Saving…"
          ) : (
            "Save Functional Assessment"
          )}
        </button>
      </div>

      {saveError && (
        <div className="rounded-xl bg-[#FF3B30]/10 px-3.5 py-2.5 text-xs text-[#B91C1C]">
          {saveError}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        <Field label="LEFS Score (0–80)" value={form.lefs_score} onChange={(v) => setForm({ ...form, lefs_score: v })} placeholder="e.g. 61" min={0} max={80} />
        <Field label="Pain VAS / NRS (0–10)" value={form.pain_vas} onChange={(v) => setForm({ ...form, pain_vas: v })} placeholder="e.g. 2.0" min={0} max={10} />
        <Field label="TUG Mobility (sec)" value={form.tug_seconds} onChange={(v) => setForm({ ...form, tug_seconds: v })} placeholder="e.g. 9.9" min={0} />
        <Field label="MMT Grade (0–5)" value={form.mmt_score} onChange={(v) => setForm({ ...form, mmt_score: v })} placeholder="e.g. 4.5" min={0} max={5} />

        <Field label="Dynamometry Injured (N)" value={form.dynamometry_injured_n} onChange={(v) => setForm({ ...form, dynamometry_injured_n: v })} placeholder="e.g. 238" min={0} />
        <Field label="Dynamometry Contra (N)" value={form.dynamometry_contralateral_n} onChange={(v) => setForm({ ...form, dynamometry_contralateral_n: v })} placeholder="e.g. 318" min={0} />
        <Field label="Gait Speed (m/s)" value={form.gait_speed_ms} onChange={(v) => setForm({ ...form, gait_speed_ms: v })} placeholder="e.g. 1.08" min={0} />
        <Field label="Gait Cadence (steps/min)" value={form.gait_cadence_spm} onChange={(v) => setForm({ ...form, gait_cadence_spm: v })} placeholder="e.g. 102" min={0} />

        <Field label="Gait Symmetry (%)" value={form.gait_symmetry_pct} onChange={(v) => setForm({ ...form, gait_symmetry_pct: v })} placeholder="e.g. 86.5" min={0} max={100} />
        <Field label="Knee Flexion (°)" value={form.knee_flexion_deg} onChange={(v) => setForm({ ...form, knee_flexion_deg: v })} placeholder="e.g. 130" min={0} max={160} />
        <Field label="Knee Extension (°)" value={form.knee_extension_deg} onChange={(v) => setForm({ ...form, knee_extension_deg: v })} placeholder="e.g. 0" min={-30} max={30} />
        <Field label="Ankle Dorsiflexion (°)" value={form.ankle_dorsiflexion_deg} onChange={(v) => setForm({ ...form, ankle_dorsiflexion_deg: v })} placeholder="e.g. 16" min={-20} max={45} />
        <Field label="Ankle Plantarflexion (°)" value={form.ankle_plantarflexion_deg} onChange={(v) => setForm({ ...form, ankle_plantarflexion_deg: v })} placeholder="e.g. 42" min={0} max={70} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-[#6E6E73]">Weight-Bearing Status (Clinician Recorded)</span>
          <select
            value={form.weight_bearing_status}
            onChange={(e) => setForm({ ...form, weight_bearing_status: e.target.value })}
            className="rounded-xl border border-black/10 bg-[#F5F5F7]/60 px-3 py-2 text-sm text-[#1D1D1F] outline-none focus:border-[#0071E3]"
          >
            <option>Non-weight bearing (crutches)</option>
            <option>Touch-down weight bearing</option>
            <option>Partial weight bearing (50%)</option>
            <option>Weight bearing as tolerated</option>
            <option>Full weight bearing</option>
            <option>Full unrestricted activity</option>
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs">
          <span className="font-medium text-[#6E6E73]">Physiotherapist Notes</span>
          <input
            type="text"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            placeholder="Gait observations, swelling, compensatory patterns…"
            className="rounded-xl border border-black/10 bg-[#F5F5F7]/60 px-3 py-2 text-sm text-[#1D1D1F] outline-none focus:border-[#0071E3]"
          />
        </label>
      </div>
    </form>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  min,
  max,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  min?: number;
  max?: number;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      <span className="font-medium text-[#6E6E73]">{label}</span>
      <input
        type="number"
        step="any"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="rounded-xl border border-black/10 bg-[#F5F5F7]/60 px-3 py-2 text-sm tabular-nums text-[#1D1D1F] outline-none focus:border-[#0071E3] focus:bg-white transition"
      />
    </label>
  );
}
