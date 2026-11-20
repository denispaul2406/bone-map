from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PatientCase(Base):
    __tablename__ = "patient_cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. BM-0001
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fracture_location: Mapped[str] = mapped_column(String(64), default="Tibial shaft")
    ao_classification: Mapped[str | None] = mapped_column(String(32), nullable=True)
    injury_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    open_closed: Mapped[str] = mapped_column(String(16), default="Closed")
    surgical_intervention: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fixation_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comorbidities: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_intact_reference: Mapped[int] = mapped_column(Integer, default=0)
    data_source: Mapped[str] = mapped_column(String(128), default="Clinical Upload")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="Assessment.days_post_injury"
    )


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("patient_cases.id", ondelete="CASCADE"))
    timepoint_label: Mapped[str] = mapped_column(String(16))  # T0, T1, T2, T3
    assessment_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    days_post_injury: Mapped[int] = mapped_column(Integer, default=0)
    modality: Mapped[str] = mapped_column(String(16), default="CT")  # CT | XRAY | PHYSIO_ONLY
    healing_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Track B: Follow-up X-ray, expert mask, 2D Coronal CT & mRUST
    xray_ap_relpath: Mapped[str | None] = mapped_column(String(256), nullable=True)
    xray_lat_relpath: Mapped[str | None] = mapped_column(String(256), nullable=True)
    xray_mask_relpath: Mapped[str | None] = mapped_column(String(256), nullable=True)
    coronal_ct_2d_relpath: Mapped[str | None] = mapped_column(String(256), nullable=True)
    mrust_anterior: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mrust_posterior: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mrust_medial: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mrust_lateral: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mrust_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clinical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped[PatientCase] = relationship(back_populates="assessments")
    ct_runs: Mapped[list[CTScanRun]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", order_by="CTScanRun.created_at.desc()"
    )
    physio: Mapped[PhysioAssessment | None] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", uselist=False
    )


class CTScanRun(Base):
    __tablename__ = "ct_scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(24), default="queued")  # queued | running | completed | failed
    input_relpath: Mapped[str] = mapped_column(String(256))
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    segmentation_backend: Mapped[str] = mapped_column(String(64), default="auto_lower_limb")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    assets_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="ct_runs")


class PhysioAssessment(Base):
    __tablename__ = "physio_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), unique=True
    )
    mmt_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-5
    dynamometry_injured_n: Mapped[float | None] = mapped_column(Float, nullable=True)
    dynamometry_contralateral_n: Mapped[float | None] = mapped_column(Float, nullable=True)
    dynamometry_symmetry_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    knee_flexion_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    knee_extension_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    ankle_dorsiflexion_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    ankle_plantarflexion_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    pain_vas: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-10
    gait_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    gait_cadence_spm: Mapped[float | None] = mapped_column(Float, nullable=True)
    gait_symmetry_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    tug_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    lefs_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-80
    weight_bearing_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    assessment: Mapped[Assessment] = relationship(back_populates="physio")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    assessment_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(64))
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
