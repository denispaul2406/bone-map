from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    id: str = Field(
        ...,
        min_length=2,
        max_length=32,
        pattern=r"^[A-Za-z0-9_-]{2,32}$",
        examples=["BM-0001"],
    )
    age: int | None = Field(default=None, ge=0, le=120)
    sex: str | None = None
    fracture_location: str = "Tibial shaft"
    ao_classification: str | None = "42-B2"
    injury_date: str | None = None
    open_closed: str = "Closed"
    surgical_intervention: str | None = None
    fixation_type: str | None = "Intramedullary nail"
    comorbidities: str | None = None
    notes: str | None = None
    is_intact_reference: bool = False


class AssessmentCreate(BaseModel):
    timepoint_label: str = Field(..., min_length=1, max_length=16, examples=["T0", "T1", "T2", "T3"])
    assessment_date: str | None = None
    days_post_injury: int = Field(default=0, ge=0, le=3650)
    modality: str = Field(default="CT", pattern="^(CT|XRAY|PHYSIO_ONLY)$")
    healing_phase: str | None = None
    clinical_notes: str | None = None


class XRayScoresUpdate(BaseModel):
    mrust_anterior: int = Field(..., ge=1, le=4)
    mrust_posterior: int = Field(..., ge=1, le=4)
    mrust_medial: int = Field(..., ge=1, le=4)
    mrust_lateral: int = Field(..., ge=1, le=4)
    healing_phase: str | None = None
    clinical_notes: str | None = None


class PhysioUpsert(BaseModel):
    mmt_score: float | None = Field(default=None, ge=0, le=5)
    dynamometry_injured_n: float | None = Field(default=None, ge=0)
    dynamometry_contralateral_n: float | None = Field(default=None, ge=0)
    knee_flexion_deg: float | None = None
    knee_extension_deg: float | None = None
    ankle_dorsiflexion_deg: float | None = None
    ankle_plantarflexion_deg: float | None = None
    pain_vas: float | None = Field(default=None, ge=0, le=10)
    gait_speed_ms: float | None = Field(default=None, ge=0)
    gait_cadence_spm: float | None = Field(default=None, ge=0)
    gait_symmetry_pct: float | None = Field(default=None, ge=0, le=100)
    tug_seconds: float | None = Field(default=None, ge=0)
    lefs_score: float | None = Field(default=None, ge=0, le=80)
    weight_bearing_status: str | None = None
    notes: str | None = None


class SampleCTAttachRequest(BaseModel):
    sample_filename: str
    segmentation_backend: str = Field(
        default="auto_lower_limb",
        pattern="^(auto_lower_limb|totalsegmentator|manual_nifti)$",
    )
    extra: dict[str, Any] | None = None
