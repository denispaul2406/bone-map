export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface HealthResponse {
  status: string;
  gpu: {
    cuda_available: boolean;
    device_name: string | null;
    vram_total_mb: number | null;
  };
  samples: string[];
}

export interface BoneArchitectureMetrics {
  cortical_thickness_mean_mm: number;
  cortical_thickness_median_mm: number;
  cortical_thickness_std_mm: number;
  cortical_thickness_min_mm: number;
  cortical_thickness_p90_mm: number;
  cortical_hu_mean: number;
  cortical_hu_median: number;
  cortical_hu_iqr: number;
  callus_hu_mean: number | null;
  bmd_calibrated: boolean;
  trabecular_status: string;
  trabecular_thickness_mm: number | null;
  trabecular_separation_mm: number | null;
  voxel_spacing_mm: number[];
  early_callus_volume_cm3: number;
  hard_callus_volume_cm3: number;
  total_callus_volume_cm3: number;
  bone_length_mm: number;
  coronal_angulation_deg: number;
  sagittal_angulation_deg: number;
  total_bone_volume_cm3: number;
  bridged_quadrants_count: number;
  quadrant_continuity_pct: Record<string, number>;
  overall_cortical_continuity_pct: number;
  fracture_gap_mm: number;
  fragment_displacement_mm: number;
  fragment_count: number;
  metal_present: boolean;
  metal_volume_cm3: number;
  metal_excluded_voxels: number;
  segmentation_method: string;
  warnings: string[];
  axial_thickness_profile: Array<{
    position_mm: number;
    mean_thickness_mm: number;
    callus_voxels: number;
  }>;
}

export interface CTRun {
  id: number;
  assessment_id: number;
  status: "queued" | "running" | "completed" | "failed";
  source_hash: string | null;
  segmentation_backend: string;
  metadata: {
    dimensions_zyx?: number[];
    voxel_spacing_mm?: number[];
    source_format?: string;
    slice_thickness_mm?: number | null;
    kvp?: number | null;
    phi_stripped?: boolean;
  } | null;
  metrics: BoneArchitectureMetrics | null;
  assets: {
    combined_scene?: string;
    tibia_cortical?: string;
    mineralised_callus?: string;
    metal_hardware?: string;
    fibula?: string;
    tibia_thickness_heatmap?: string;
    label_nifti?: string;
    ct_nifti?: string;
    slice_axial_png?: string;
    slice_coronal_png?: string;
    slice_sagittal_png?: string;
    default_slice_indices?: { axial: number; coronal: number; sagittal: number };
  };
  error_message: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface PhysioAssessment {
  id: number;
  assessment_id: number;
  mmt_score: number | null;
  dynamometry_injured_n: number | null;
  dynamometry_contralateral_n: number | null;
  dynamometry_symmetry_pct: number | null;
  knee_flexion_deg: number | null;
  knee_extension_deg: number | null;
  ankle_dorsiflexion_deg: number | null;
  ankle_plantarflexion_deg: number | null;
  pain_vas: number | null;
  gait_speed_ms: number | null;
  gait_cadence_spm: number | null;
  gait_symmetry_pct: number | null;
  tug_seconds: number | null;
  lefs_score: number | null;
  weight_bearing_status: string | null;
  notes: string | null;
  updated_at: string | null;
}

export interface Assessment {
  id: number;
  case_id: string;
  timepoint_label: string;
  assessment_date: string | null;
  days_post_injury: number;
  modality: "CT" | "XRAY" | "PHYSIO_ONLY";
  healing_phase: string | null;
  xray_ap_url: string | null;
  xray_lat_url: string | null;
  xray_mask_url: string | null;
  coronal_ct_2d_url: string | null;
  mrust: {
    anterior: number;
    posterior: number;
    medial: number;
    lateral: number;
    total: number;
  } | null;
  clinical_notes: string | null;
  ct_runs: CTRun[];
  physio: PhysioAssessment | null;
}

export interface CaseSummary {
  id: string;
  age: number | null;
  sex: string | null;
  fracture_location: string;
  ao_classification: string | null;
  injury_date: string | null;
  open_closed: string;
  surgical_intervention: string | null;
  fixation_type: string | null;
  comorbidities: string | null;
  notes: string | null;
  is_intact_reference: boolean;
  data_source: string;
  assessment_count: number;
  completed_ct_count: number;
  physio_count: number;
  latest_timepoint: string | null;
  latest_healing_phase: string | null;
  latest_metrics: BoneArchitectureMetrics | null;
}

export interface CaseDetail extends CaseSummary {
  assessments: Assessment[];
  audit_logs: Array<{
    id: number;
    actor: string;
    action: string;
    details: Record<string, unknown> | null;
    created_at: string;
  }>;
}

export interface DashboardData {
  kpis: {
    research_cases: number;
    imaging_assessments: number;
    completed_ct_reconstructions: number;
    longitudinal_cases: number;
    functional_assessments: number;
  };
  cases: CaseSummary[];
}

export interface LongitudinalComparison {
  case_id: string;
  timeline: Array<{
    assessment_id: number;
    timepoint_label: string;
    days_post_injury: number;
    assessment_date: string | null;
    modality: string;
    healing_phase: string | null;
    ct_metrics: BoneArchitectureMetrics | null;
    mrust_total: number | null;
    physio: PhysioAssessment | null;
  }>;
  ct_comparison: {
    baseline_timepoint: string;
    followup_timepoint: string;
    baseline_run_id: number;
    followup_run_id: number;
    deltas: {
      registration_converged: boolean;
      dice_bone_overlap: number;
      callus_volume_baseline_cm3: number;
      callus_volume_followup_cm3: number;
      callus_volume_change_pct: number | null;
      cortical_thickness_baseline_mm: number;
      cortical_thickness_followup_mm: number;
      cortical_thickness_change_pct: number | null;
      fracture_gap_baseline_mm: number;
      fracture_gap_followup_mm: number;
      fracture_gap_change_pct: number | null;
      bridged_quadrants_baseline: number;
      bridged_quadrants_followup: number;
      bridged_quadrants_delta: number;
      cortical_hu_baseline: number;
      cortical_hu_followup: number;
      cortical_hu_delta: number;
    };
  } | null;
  modality_note: string;
}

export interface CohortAnalytics {
  total_cases: number;
  ct_quantified_visits: number;
  xray_mrust_scored_visits: number;
  physio_visits: number;
  mean_cortical_thickness_mm: number | null;
  mean_callus_volume_cm3: number | null;
  mean_mrust_total: number | null;
  mean_lefs_score: number | null;
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    let message = text || `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed?.detail === "string") {
        message = parsed.detail;
      } else if (Array.isArray(parsed?.detail)) {
        message = parsed.detail
          .map((e: { loc?: unknown[]; msg?: string }) =>
            `${Array.isArray(e.loc) ? e.loc.slice(1).join(".") : "field"}: ${e.msg || "invalid"}`
          )
          .join("; ");
      }
    } catch {
      // Keep raw text if not JSON
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export function fullAssetUrl(relOrApiUrl?: string | null): string | null {
  if (!relOrApiUrl) return null;
  if (relOrApiUrl.startsWith("http")) return relOrApiUrl;
  return `${API_BASE}${relOrApiUrl}`;
}

export const api = {
  health: () => apiJson<HealthResponse>("/api/health"),
  dashboard: () => apiJson<DashboardData>("/api/dashboard"),
  seedRealDatasets: () =>
    apiJson<{ status: string; cases: string[] }>("/api/datasets/seed-real", {
      method: "POST",
    }),
  createCase: (payload: Record<string, unknown>) =>
    apiJson<CaseSummary>("/api/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getCase: (caseId: string) => apiJson<CaseDetail>(`/api/cases/${encodeURIComponent(caseId)}`),
  createAssessment: (caseId: string, payload: Record<string, unknown>) =>
    apiJson<Assessment>(`/api/cases/${encodeURIComponent(caseId)}/assessments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  uploadCT: async (assessmentId: number, file: File, backend = "auto_lower_limb") => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("segmentation_backend", backend);
    return apiJson<CTRun>(`/api/assessments/${assessmentId}/ct`, {
      method: "POST",
      body: fd,
    });
  },
  attachSampleCT: (
    assessmentId: number,
    sampleFilename: string,
    segmentationBackend = "auto_lower_limb"
  ) =>
    apiJson<CTRun>(`/api/assessments/${assessmentId}/ct/attach-sample`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sample_filename: sampleFilename,
        segmentation_backend: segmentationBackend,
      }),
    }),
  getCTRun: (runId: number) => apiJson<CTRun>(`/api/ct-runs/${runId}`),
  reimportMask: async (runId: number, maskFile: File) => {
    const fd = new FormData();
    fd.append("mask_file", maskFile);
    return apiJson<CTRun>(`/api/ct-runs/${runId}/reimport-mask`, {
      method: "POST",
      body: fd,
    });
  },
  updateXRay: async (assessmentId: number, fd: FormData) =>
    apiJson<Assessment>(`/api/assessments/${assessmentId}/xray`, {
      method: "POST",
      body: fd,
    }),
  upsertPhysio: (assessmentId: number, payload: Record<string, unknown>) =>
    apiJson<PhysioAssessment>(`/api/assessments/${assessmentId}/physio`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  compareCase: (caseId: string, baselineId?: number, followupId?: number) => {
    const params = new URLSearchParams();
    if (baselineId != null) params.set("baseline_assessment_id", String(baselineId));
    if (followupId != null) params.set("followup_assessment_id", String(followupId));
    const qs = params.toString() ? `?${params.toString()}` : "";
    return apiJson<LongitudinalComparison>(`/api/cases/${encodeURIComponent(caseId)}/compare${qs}`);
  },
  cohortAnalytics: () => apiJson<CohortAnalytics>("/api/analytics/cohort"),
};
