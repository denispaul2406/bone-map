from __future__ import annotations

import csv
import io
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import SimpleITK as sitk
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from app.db import Base, CASES_DIR, DATA_DIR, SAMPLES_DIR, SessionLocal, engine, get_db
from app.imaging.loader import window_ct_slice_to_png
from app.imaging.registration import compute_longitudinal_ct_delta, register_ct_masks_rigid
from app.models import Assessment, AuditLog, CTScanRun, PatientCase, PhysioAssessment
from app.real_datasets import seed_real_public_cases
from app.schemas import (
    AssessmentCreate,
    CaseCreate,
    PhysioUpsert,
    SampleCTAttachRequest,
)
from app.workers.ct_worker import enqueue_ct_job

Base.metadata.create_all(bind=engine)


def _startup_db_maintenance() -> None:
    """Safely add missing columns on upgrades and recover CT jobs interrupted by crashes."""
    with engine.begin() as conn:
        case_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(patient_cases)"))}
        if "is_intact_reference" not in case_cols:
            conn.execute(text("ALTER TABLE patient_cases ADD COLUMN is_intact_reference INTEGER DEFAULT 0"))
        if "data_source" not in case_cols:
            conn.execute(text("ALTER TABLE patient_cases ADD COLUMN data_source VARCHAR(128) DEFAULT 'Clinical Upload'"))

        assess_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(assessments)"))}
        if "xray_mask_relpath" not in assess_cols:
            conn.execute(text("ALTER TABLE assessments ADD COLUMN xray_mask_relpath VARCHAR(256)"))
        if "coronal_ct_2d_relpath" not in assess_cols:
            conn.execute(text("ALTER TABLE assessments ADD COLUMN coronal_ct_2d_relpath VARCHAR(256)"))

    db = SessionLocal()
    try:
        stale = db.query(CTScanRun).filter(CTScanRun.status.in_(["queued", "running"])).all()
        for run in stale:
            run.status = "failed"
            run.error_message = "Interrupted by server restart; please re-upload or re-run."
        if stale:
            db.commit()
    finally:
        db.close()


_startup_db_maintenance()

app = FastAPI(
    title="BONE-MAP API",
    version="0.1.0",
    description="Bone Architecture Quantification and Fracture Recovery Monitoring Platform",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ALLOWED_BACKENDS = {"auto_lower_limb", "totalsegmentator", "manual_nifti"}
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
ALLOWED_SERVE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".glb", ".nii", ".gz"}
MAX_CT_UPLOAD_BYTES = 600 * 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = 50 * 1024 * 1024


def _csv_safe(val: Any) -> Any:
    if isinstance(val, str) and val and val[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + val
    return val


def _safe_filename(raw: str | None, fallback: str = "upload.bin") -> str:
    name = Path(raw or fallback).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._")
    return cleaned or fallback


def _save_upload_limited(upload: UploadFile, dest_path: Path, max_bytes: int) -> None:
    written = 0
    try:
        with dest_path.open("wb") as out:
            while chunk := upload.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds limit ({max_bytes // (1024 * 1024)} MB).",
                    )
                out.write(chunk)
    except Exception:
        dest_path.unlink(missing_ok=True)
        raise


def _serialize_case_summary(case: PatientCase) -> dict[str, Any]:
    assessments = sorted(case.assessments, key=lambda a: a.days_post_injury)
    latest = assessments[-1] if assessments else None
    ct_count = sum(1 for a in assessments if any(r.status == "completed" for r in a.ct_runs))
    physio_count = sum(1 for a in assessments if a.physio is not None)

    latest_metrics = None
    for a in reversed(assessments):
        done_runs = [r for r in a.ct_runs if r.status == "completed" and r.metrics_json]
        if done_runs:
            latest_metrics = done_runs[0].metrics_json
            break

    return {
        "id": case.id,
        "age": case.age,
        "sex": case.sex,
        "fracture_location": case.fracture_location,
        "ao_classification": case.ao_classification,
        "injury_date": case.injury_date,
        "open_closed": case.open_closed,
        "surgical_intervention": case.surgical_intervention,
        "fixation_type": case.fixation_type,
        "comorbidities": case.comorbidities,
        "notes": case.notes,
        "is_intact_reference": bool(case.is_intact_reference),
        "data_source": case.data_source,
        "assessment_count": len(assessments),
        "completed_ct_count": ct_count,
        "physio_count": physio_count,
        "latest_timepoint": latest.timepoint_label if latest else None,
        "latest_healing_phase": latest.healing_phase if latest else None,
        "latest_metrics": latest_metrics,
        "created_at": case.created_at.isoformat() if case.created_at else None,
    }


def _serialize_assessment(a: Assessment) -> dict[str, Any]:
    return {
        "id": a.id,
        "case_id": a.case_id,
        "timepoint_label": a.timepoint_label,
        "assessment_date": a.assessment_date,
        "days_post_injury": a.days_post_injury,
        "modality": a.modality,
        "healing_phase": a.healing_phase,
        "xray_ap_url": f"/api/files/{a.xray_ap_relpath}" if a.xray_ap_relpath else None,
        "xray_lat_url": f"/api/files/{a.xray_lat_relpath}" if a.xray_lat_relpath else None,
        "xray_mask_url": f"/api/files/{a.xray_mask_relpath}" if a.xray_mask_relpath else None,
        "coronal_ct_2d_url": f"/api/files/{a.coronal_ct_2d_relpath}" if a.coronal_ct_2d_relpath else None,
        "mrust": {
            "anterior": a.mrust_anterior,
            "posterior": a.mrust_posterior,
            "medial": a.mrust_medial,
            "lateral": a.mrust_lateral,
            "total": a.mrust_total,
        }
        if a.mrust_total is not None
        else None,
        "clinical_notes": a.clinical_notes,
        "ct_runs": [_serialize_ct_run(r) for r in a.ct_runs],
        "physio": _serialize_physio(a.physio) if a.physio else None,
    }


def _serialize_ct_run(r: CTScanRun) -> dict[str, Any]:
    assets_urls: dict[str, Any] = {}
    if r.assets_json:
        for k, v in r.assets_json.items():
            if isinstance(v, str):
                assets_urls[k] = f"/api/files/{v}"
            else:
                assets_urls[k] = v
    return {
        "id": r.id,
        "assessment_id": r.assessment_id,
        "status": r.status,
        "source_hash": r.source_hash,
        "segmentation_backend": r.segmentation_backend,
        "metadata": r.metadata_json,
        "metrics": r.metrics_json,
        "assets": assets_urls,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


def _serialize_physio(p: PhysioAssessment) -> dict[str, Any]:
    return {
        "id": p.id,
        "assessment_id": p.assessment_id,
        "mmt_score": p.mmt_score,
        "dynamometry_injured_n": p.dynamometry_injured_n,
        "dynamometry_contralateral_n": p.dynamometry_contralateral_n,
        "dynamometry_symmetry_pct": p.dynamometry_symmetry_pct,
        "knee_flexion_deg": p.knee_flexion_deg,
        "knee_extension_deg": p.knee_extension_deg,
        "ankle_dorsiflexion_deg": p.ankle_dorsiflexion_deg,
        "ankle_plantarflexion_deg": p.ankle_plantarflexion_deg,
        "pain_vas": p.pain_vas,
        "gait_speed_ms": p.gait_speed_ms,
        "gait_cadence_spm": p.gait_cadence_spm,
        "gait_symmetry_pct": p.gait_symmetry_pct,
        "tug_seconds": p.tug_seconds,
        "lefs_score": p.lefs_score,
        "weight_bearing_status": p.weight_bearing_status,
        "notes": p.notes,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@app.get("/api/health")
def health_check() -> dict[str, Any]:
    gpu_info: dict[str, Any] = {"cuda_available": False, "device_name": None, "vram_total_mb": None}
    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            gpu_info = {
                "cuda_available": True,
                "device_name": props.name,
                "vram_total_mb": round(props.total_memory / (1024 * 1024)),
            }
    except Exception:
        pass
    samples = [p.name for p in SAMPLES_DIR.glob("*.nii*")]
    return {"status": "ok", "gpu": gpu_info, "samples": samples}


@app.get("/api/dashboard")
def get_dashboard(db: Session = Depends(get_db)) -> dict[str, Any]:
    cases = (
        db.query(PatientCase)
        .options(
            selectinload(PatientCase.assessments).selectinload(Assessment.ct_runs),
            selectinload(PatientCase.assessments).selectinload(Assessment.physio),
        )
        .order_by(PatientCase.created_at.desc())
        .all()
    )
    total_assessments = sum(len(c.assessments) for c in cases)
    completed_cts = sum(
        1 for c in cases for a in c.assessments if any(r.status == "completed" for r in a.ct_runs)
    )
    longitudinal_cases = sum(1 for c in cases if len(c.assessments) >= 2)
    physio_records = sum(1 for c in cases for a in c.assessments if a.physio is not None)

    return {
        "kpis": {
            "research_cases": len(cases),
            "imaging_assessments": total_assessments,
            "completed_ct_reconstructions": completed_cts,
            "longitudinal_cases": longitudinal_cases,
            "functional_assessments": physio_records,
        },
        "cases": [_serialize_case_summary(c) for c in cases],
    }


@app.get("/api/cases")
def list_cases(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    cases = (
        db.query(PatientCase)
        .options(
            selectinload(PatientCase.assessments).selectinload(Assessment.ct_runs),
            selectinload(PatientCase.assessments).selectinload(Assessment.physio),
        )
        .order_by(PatientCase.created_at.desc())
        .all()
    )
    return [_serialize_case_summary(c) for c in cases]


@app.post("/api/cases")
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    existing = db.get(PatientCase, payload.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Case {payload.id} already exists.")
    payload_data = payload.model_dump()
    is_ref = int(bool(payload_data.pop("is_intact_reference", False)))
    case = PatientCase(**payload_data, is_intact_reference=is_ref)
    db.add(case)
    db.add(
        AuditLog(
            case_id=case.id,
            actor="researcher",
            action="case_created",
            details_json={"ao_classification": case.ao_classification, "fixation_type": case.fixation_type},
        )
    )
    db.commit()
    db.refresh(case)
    return _serialize_case_summary(case)


@app.get("/api/cases/{case_id}")
def get_case_detail(case_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    case = (
        db.query(PatientCase)
        .options(
            selectinload(PatientCase.assessments).selectinload(Assessment.ct_runs),
            selectinload(PatientCase.assessments).selectinload(Assessment.physio),
        )
        .filter(PatientCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.created_at.desc())
        .limit(25)
        .all()
    )
    data = _serialize_case_summary(case)
    data["assessments"] = [_serialize_assessment(a) for a in case.assessments]
    data["audit_logs"] = [
        {
            "id": l.id,
            "actor": l.actor,
            "action": l.action,
            "details": l.details_json,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]
    return data


@app.post("/api/cases/{case_id}/assessments")
def create_assessment(
    case_id: str, payload: AssessmentCreate, db: Session = Depends(get_db)
) -> dict[str, Any]:
    case = db.get(PatientCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")
    assessment = Assessment(case_id=case_id, **payload.model_dump())
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return _serialize_assessment(assessment)


@app.post("/api/assessments/{assessment_id}/ct")
def upload_ct_scan(
    assessment_id: int,
    file: UploadFile = File(...),
    segmentation_backend: str = Form("auto_lower_limb"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found.")

    if segmentation_backend not in ALLOWED_BACKENDS:
        raise HTTPException(status_code=400, detail="Invalid segmentation backend.")

    filename = _safe_filename(file.filename, "scan.nii.gz")
    lower = filename.lower()
    if not (lower.endswith(".nii.gz") or lower.endswith(".nii") or lower.endswith(".zip")):
        raise HTTPException(
            status_code=400,
            detail="Upload must be a .nii, .nii.gz, or zipped DICOM series (.zip).",
        )

    dest_dir = CASES_DIR / assessment.case_id / f"assessment_{assessment.id}" / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{int(datetime.now(timezone.utc).timestamp())}_{filename}"
    dest_path = dest_dir / safe_name

    _save_upload_limited(file, dest_path, MAX_CT_UPLOAD_BYTES)

    run = CTScanRun(
        assessment_id=assessment.id,
        status="queued",
        input_relpath=dest_path.relative_to(DATA_DIR).as_posix(),
        segmentation_backend=segmentation_backend,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    enqueue_ct_job(run.id, backend=segmentation_backend)  # type: ignore[arg-type]
    return _serialize_ct_run(run)


@app.post("/api/assessments/{assessment_id}/ct/attach-sample")
def attach_sample_ct(
    assessment_id: int, payload: SampleCTAttachRequest, db: Session = Depends(get_db)
) -> dict[str, Any]:
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    sample_name = Path(payload.sample_filename).name
    sample_path = (SAMPLES_DIR / sample_name).resolve()
    if not sample_path.is_relative_to(SAMPLES_DIR.resolve()) or not sample_path.is_file():
        raise HTTPException(status_code=404, detail="Sample file not found.")

    run = CTScanRun(
        assessment_id=assessment.id,
        status="queued",
        input_relpath=sample_path.relative_to(DATA_DIR).as_posix(),
        segmentation_backend=payload.segmentation_backend,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    enqueue_ct_job(run.id, backend=payload.segmentation_backend)  # type: ignore[arg-type]
    return _serialize_ct_run(run)


@app.get("/api/ct-runs/{run_id}")
def get_ct_run(run_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.get(CTScanRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="CT run not found.")
    return _serialize_ct_run(run)


@app.post("/api/ct-runs/{run_id}/reimport-mask")
def reimport_corrected_mask(
    run_id: int,
    mask_file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    old_run = db.get(CTScanRun, run_id)
    if not old_run:
        raise HTTPException(status_code=404, detail="CT run not found.")

    dest_dir = CASES_DIR / old_run.assessment.case_id / f"assessment_{old_run.assessment_id}" / "manual_masks"
    dest_dir.mkdir(parents=True, exist_ok=True)
    mask_name = _safe_filename(mask_file.filename, "mask.nii.gz")
    if not (mask_name.lower().endswith(".nii.gz") or mask_name.lower().endswith(".nii")):
        raise HTTPException(status_code=400, detail="Mask must be a .nii or .nii.gz file.")
    mask_path = dest_dir / f"corrected_{int(datetime.now(timezone.utc).timestamp())}_{mask_name}"
    _save_upload_limited(mask_file, mask_path, MAX_IMAGE_UPLOAD_BYTES)

    new_run = CTScanRun(
        assessment_id=old_run.assessment_id,
        status="queued",
        input_relpath=old_run.input_relpath,
        segmentation_backend="manual_slicer_nifti",
    )
    db.add(new_run)
    db.add(
        AuditLog(
            case_id=old_run.assessment.case_id,
            assessment_id=old_run.assessment_id,
            actor="researcher",
            action="manual_mask_reimported",
            details_json={"parent_run_id": old_run.id, "mask_file": mask_path.name},
        )
    )
    db.commit()
    db.refresh(new_run)

    enqueue_ct_job(new_run.id, backend="manual_nifti", manual_mask_path=mask_path)
    return _serialize_ct_run(new_run)


@app.get("/api/ct-runs/{run_id}/slice/{plane}/{index}")
def render_live_slice(
    run_id: int,
    plane: str,
    index: int,
    overlay: bool = Query(True),
    db: Session = Depends(get_db),
) -> FileResponse:
    run = db.get(CTScanRun, run_id)
    if not run or not run.assets_json or "ct_nifti" not in run.assets_json:
        raise HTTPException(status_code=404, detail="CT volume not ready.")

    data_root = DATA_DIR.resolve()
    ct_path = (DATA_DIR / run.assets_json["ct_nifti"]).resolve()
    if not ct_path.is_relative_to(data_root) or not ct_path.is_file():
        raise HTTPException(status_code=404, detail="CT NIfTI file missing.")

    plane_l = plane.lower()
    if plane_l not in ("axial", "coronal", "sagittal"):
        raise HTTPException(status_code=400, detail="Plane must be axial, coronal, or sagittal.")

    dims = (run.metadata_json or {}).get("dimensions_zyx")
    if isinstance(dims, list) and len(dims) == 3:
        axis_map = {"axial": 0, "coronal": 1, "sagittal": 2}
        idx = int(np.clip(index, 0, max(0, int(dims[axis_map[plane_l]]) - 1)))
        cache_path = ct_path.parent / "slice_cache" / f"{plane_l}_{idx}_{int(overlay)}.png"
        if cache_path.is_file():
            return FileResponse(cache_path, media_type="image/png")

    ct_arr = sitk.GetArrayFromImage(sitk.ReadImage(str(ct_path), sitk.sitkFloat32))

    lbl_arr = None
    if overlay and "label_nifti" in run.assets_json:
        lbl_path = (DATA_DIR / run.assets_json["label_nifti"]).resolve()
        if lbl_path.is_relative_to(data_root) and lbl_path.is_file():
            lbl_arr = sitk.GetArrayFromImage(sitk.ReadImage(str(lbl_path), sitk.sitkUInt8))

    if plane_l == "axial":
        idx = int(np.clip(index, 0, ct_arr.shape[0] - 1))
        sl = ct_arr[idx]
        ov = lbl_arr[idx] if lbl_arr is not None else None
    elif plane_l == "coronal":
        idx = int(np.clip(index, 0, ct_arr.shape[1] - 1))
        sl = ct_arr[:, idx, :]
        ov = lbl_arr[:, idx, :] if lbl_arr is not None else None
    else:
        idx = int(np.clip(index, 0, ct_arr.shape[2] - 1))
        sl = ct_arr[:, :, idx]
        ov = lbl_arr[:, :, idx] if lbl_arr is not None else None

    cache_path = ct_path.parent / "slice_cache" / f"{plane_l}_{idx}_{int(overlay)}.png"
    if not cache_path.exists():
        window_ct_slice_to_png(sl, cache_path, overlay_mask=ov)
    return FileResponse(cache_path, media_type="image/png")


@app.post("/api/assessments/{assessment_id}/xray")
def update_xray_and_mrust(
    assessment_id: int,
    mrust_anterior: int = Form(..., ge=1, le=4),
    mrust_posterior: int = Form(..., ge=1, le=4),
    mrust_medial: int = Form(..., ge=1, le=4),
    mrust_lateral: int = Form(..., ge=1, le=4),
    healing_phase: str | None = Form(None),
    clinical_notes: str | None = Form(None),
    ap_file: UploadFile | None = File(None),
    lat_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found.")

    xray_dir = CASES_DIR / assessment.case_id / f"assessment_{assessment.id}" / "xrays"
    xray_dir.mkdir(parents=True, exist_ok=True)

    if ap_file is not None and ap_file.filename:
        ap_name = _safe_filename(ap_file.filename, "ap.png")
        if Path(ap_name).suffix.lower() not in ALLOWED_IMAGE_EXTS:
            raise HTTPException(status_code=400, detail="AP radiograph must be PNG/JPG/TIFF/WebP.")
        ap_path = xray_dir / f"ap_{int(datetime.now(timezone.utc).timestamp())}_{ap_name}"
        _save_upload_limited(ap_file, ap_path, MAX_IMAGE_UPLOAD_BYTES)
        assessment.xray_ap_relpath = ap_path.relative_to(DATA_DIR).as_posix()

    if lat_file is not None and lat_file.filename:
        lat_name = _safe_filename(lat_file.filename, "lat.png")
        if Path(lat_name).suffix.lower() not in ALLOWED_IMAGE_EXTS:
            raise HTTPException(status_code=400, detail="Lateral radiograph must be PNG/JPG/TIFF/WebP.")
        lat_path = xray_dir / f"lat_{int(datetime.now(timezone.utc).timestamp())}_{lat_name}"
        _save_upload_limited(lat_file, lat_path, MAX_IMAGE_UPLOAD_BYTES)
        assessment.xray_lat_relpath = lat_path.relative_to(DATA_DIR).as_posix()

    assessment.mrust_anterior = mrust_anterior
    assessment.mrust_posterior = mrust_posterior
    assessment.mrust_medial = mrust_medial
    assessment.mrust_lateral = mrust_lateral
    assessment.mrust_total = mrust_anterior + mrust_posterior + mrust_medial + mrust_lateral
    if healing_phase is not None:
        assessment.healing_phase = healing_phase
    if clinical_notes is not None:
        assessment.clinical_notes = clinical_notes

    db.add(
        AuditLog(
            case_id=assessment.case_id,
            assessment_id=assessment.id,
            actor="clinician",
            action="xray_mrust_updated",
            details_json={"mrust_total": assessment.mrust_total, "healing_phase": assessment.healing_phase},
        )
    )
    db.commit()
    db.refresh(assessment)
    return _serialize_assessment(assessment)


@app.put("/api/assessments/{assessment_id}/physio")
def upsert_physio(
    assessment_id: int, payload: PhysioUpsert, db: Session = Depends(get_db)
) -> dict[str, Any]:
    assessment = db.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found.")

    data = payload.model_dump()
    inj = data.get("dynamometry_injured_n")
    contra = data.get("dynamometry_contralateral_n")
    sym = round((inj / contra) * 100.0, 1) if (inj is not None and contra and contra > 0) else None

    physio = assessment.physio
    if physio is None:
        physio = PhysioAssessment(assessment_id=assessment_id, dynamometry_symmetry_pct=sym, **data)
        db.add(physio)
    else:
        for k, v in data.items():
            setattr(physio, k, v)
        physio.dynamometry_symmetry_pct = sym

    db.add(
        AuditLog(
            case_id=assessment.case_id,
            assessment_id=assessment.id,
            actor="physiotherapist",
            action="physio_assessment_saved",
            details_json={"lefs_score": data.get("lefs_score"), "pain_vas": data.get("pain_vas")},
        )
    )
    db.commit()
    db.refresh(physio)
    return _serialize_physio(physio)


@app.get("/api/cases/{case_id}/compare")
def compare_longitudinal(
    case_id: str,
    baseline_assessment_id: int | None = Query(None),
    followup_assessment_id: int | None = Query(None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    case = (
        db.query(PatientCase)
        .options(
            selectinload(PatientCase.assessments).selectinload(Assessment.ct_runs),
            selectinload(PatientCase.assessments).selectinload(Assessment.physio),
        )
        .filter(PatientCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")

    assessments = sorted(case.assessments, key=lambda a: a.days_post_injury)

    # Timeline unifying Track A (CT), Track B (X-ray mRUST), and Track C (Physiotherapy)
    timeline = []
    ct_candidates: list[tuple[Assessment, CTScanRun]] = []
    for a in assessments:
        done_ct = next((r for r in a.ct_runs if r.status == "completed" and r.metrics_json), None)
        if done_ct:
            ct_candidates.append((a, done_ct))
        timeline.append(
            {
                "assessment_id": a.id,
                "timepoint_label": a.timepoint_label,
                "days_post_injury": a.days_post_injury,
                "assessment_date": a.assessment_date,
                "modality": a.modality,
                "healing_phase": a.healing_phase,
                "ct_metrics": done_ct.metrics_json if done_ct else None,
                "mrust_total": a.mrust_total,
                "physio": _serialize_physio(a.physio) if a.physio else None,
            }
        )

    ct_comparison: dict[str, Any] | None = None
    if len(ct_candidates) >= 2:
        base_pair = (
            next((p for p in ct_candidates if p[0].id == baseline_assessment_id), ct_candidates[0])
            if baseline_assessment_id
            else ct_candidates[0]
        )
        fup_pair = (
            next((p for p in ct_candidates if p[0].id == followup_assessment_id), ct_candidates[-1])
            if followup_assessment_id
            else ct_candidates[-1]
        )
        if base_pair[0].id != fup_pair[0].id:
            dice = 0.0
            converged = False
            try:
                b_lbl_rel = (base_pair[1].assets_json or {}).get("label_nifti")
                f_lbl_rel = (fup_pair[1].assets_json or {}).get("label_nifti")
                if b_lbl_rel and f_lbl_rel:
                    b_img = sitk.ReadImage(str(DATA_DIR / b_lbl_rel), sitk.sitkUInt8) == 1
                    f_img = sitk.ReadImage(str(DATA_DIR / f_lbl_rel), sitk.sitkUInt8) == 1
                    _, dice = register_ct_masks_rigid(b_img, f_img)
                    converged = True
            except Exception:
                converged = False

            delta = compute_longitudinal_ct_delta(
                baseline_metrics=base_pair[1].metrics_json or {},
                followup_metrics=fup_pair[1].metrics_json or {},
                dice_overlap=dice,
                registration_converged=converged,
            )
            ct_comparison = {
                "baseline_timepoint": base_pair[0].timepoint_label,
                "followup_timepoint": fup_pair[0].timepoint_label,
                "baseline_run_id": base_pair[1].id,
                "followup_run_id": fup_pair[1].id,
                "deltas": delta.to_dict(),
            }

    return {
        "case_id": case.id,
        "timeline": timeline,
        "ct_comparison": ct_comparison,
        "modality_note": (
            "CT-derived 3D parameters (Track A) and radiograph mRUST scores (Track B) are tracked separately "
            "and never cross-compared as equivalent measurements."
        ),
    }


@app.get("/api/cases/{case_id}/export/csv")
def export_case_csv(case_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    case = (
        db.query(PatientCase)
        .options(
            selectinload(PatientCase.assessments).selectinload(Assessment.ct_runs),
            selectinload(PatientCase.assessments).selectinload(Assessment.physio),
        )
        .filter(PatientCase.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "case_id",
            "ao_classification",
            "fixation_type",
            "timepoint",
            "days_post_injury",
            "modality",
            "healing_phase",
            "ct_cortical_thickness_mean_mm",
            "ct_cortical_hu_mean",
            "ct_callus_volume_cm3",
            "ct_fracture_gap_mm",
            "ct_fragment_displacement_mm",
            "ct_bridged_quadrants",
            "xray_mrust_total",
            "physio_lefs_0_80",
            "physio_pain_vas_0_10",
            "physio_tug_sec",
            "physio_dynamometry_symmetry_pct",
            "physio_gait_speed_ms",
            "physio_mmt_0_5",
        ]
    )
    for a in sorted(case.assessments, key=lambda x: x.days_post_injury):
        done_ct = next((r for r in a.ct_runs if r.status == "completed" and r.metrics_json), None)
        m = done_ct.metrics_json if done_ct else {}
        p = a.physio
        writer.writerow(
            [
                _csv_safe(case.id),
                _csv_safe(case.ao_classification),
                _csv_safe(case.fixation_type),
                _csv_safe(a.timepoint_label),
                a.days_post_injury,
                _csv_safe(a.modality),
                _csv_safe(a.healing_phase),
                m.get("cortical_thickness_mean_mm"),
                m.get("cortical_hu_mean"),
                m.get("total_callus_volume_cm3"),
                m.get("fracture_gap_mm"),
                m.get("fragment_displacement_mm"),
                m.get("bridged_quadrants_count"),
                a.mrust_total,
                p.lefs_score if p else None,
                p.pain_vas if p else None,
                p.tug_seconds if p else None,
                p.dynamometry_symmetry_pct if p else None,
                p.gait_speed_ms if p else None,
                p.mmt_score if p else None,
            ]
        )

    buf.seek(0)
    safe_csv_id = _safe_filename(case.id, "case")
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_csv_id}_bonemap_longitudinal.csv"'},
    )


@app.post("/api/datasets/seed-real")
@app.post("/api/demo/seed")
def import_real_public_datasets(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Import real public clinical tibia datasets (VSDFullBody + PlaTiF). No synthetic data."""
    return seed_real_public_cases(db)


@app.get("/api/analytics/cohort")
def cohort_analytics(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Cross-cohort descriptive statistics across all real cases & visits."""
    cases = (
        db.query(PatientCase)
        .options(
            selectinload(PatientCase.assessments).selectinload(Assessment.ct_runs),
            selectinload(PatientCase.assessments).selectinload(Assessment.physio),
        )
        .all()
    )
    cort_means: list[float] = []
    callus_vols: list[float] = []
    mrust_totals: list[int] = []
    lefs_scores: list[float] = []
    for c in cases:
        for a in c.assessments:
            if a.mrust_total is not None:
                mrust_totals.append(a.mrust_total)
            if a.physio and a.physio.lefs_score is not None:
                lefs_scores.append(a.physio.lefs_score)
            done = next((r for r in a.ct_runs if r.status == "completed" and r.metrics_json), None)
            if done and done.metrics_json:
                cort_means.append(float(done.metrics_json.get("cortical_thickness_mean_mm", 0.0)))
                if not c.is_intact_reference:
                    callus_vols.append(float(done.metrics_json.get("total_callus_volume_cm3", 0.0)))

    return {
        "total_cases": len(cases),
        "ct_quantified_visits": len(cort_means),
        "xray_mrust_scored_visits": len(mrust_totals),
        "physio_visits": len(lefs_scores),
        "mean_cortical_thickness_mm": round(float(np.mean(cort_means)), 2) if cort_means else None,
        "mean_callus_volume_cm3": round(float(np.mean(callus_vols)), 2) if callus_vols else None,
        "mean_mrust_total": round(float(np.mean(mrust_totals)), 1) if mrust_totals else None,
        "mean_lefs_score": round(float(np.mean(lefs_scores)), 1) if lefs_scores else None,
    }


@app.get("/api/files/{relpath:path}")
def serve_data_file(relpath: str) -> FileResponse:
    target = (DATA_DIR / relpath).resolve()
    allowed_roots = (CASES_DIR.resolve(), SAMPLES_DIR.resolve())
    if not any(target.is_relative_to(root) for root in allowed_roots) or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    if target.suffix.lower() not in ALLOWED_SERVE_EXTS:
        raise HTTPException(status_code=403, detail="File type not permitted.")
    media = None
    if target.suffix == ".glb":
        media = "model/gltf-binary"
    elif target.suffix == ".png":
        media = "image/png"
    elif target.name.endswith(".nii.gz"):
        media = "application/gzip"
    return FileResponse(target, media_type=media, headers={"X-Content-Type-Options": "nosniff"})
