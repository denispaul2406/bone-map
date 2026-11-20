from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import scipy.io
from PIL import Image
from sqlalchemy.orm import Session

from app.db import CASES_DIR, DATA_DIR, SAMPLES_DIR
from app.models import Assessment, AuditLog, CTScanRun, PatientCase
from app.workers.ct_worker import process_ct_run_sync

VSD_CT_PATH = SAMPLES_DIR / "VSD_z025_real_lower_legs_ct.nii.gz"
VSD_016_CT_PATH = SAMPLES_DIR / "VSD_016_right_tibia_ct.nii.gz"
PLATIF_ZIP = SAMPLES_DIR / "platif" / "Patient Data_Part 3.zip"
PLATIF_XLSX = SAMPLES_DIR / "platif" / "Tibial Plateau Fracture Metadata.xlsx"


def _read_platif_metadata() -> dict[str, dict[str, str]]:
    """Parse real clinical metadata from PlaTiF Tibial Plateau Fracture Metadata.xlsx."""
    if not PLATIF_XLSX.exists():
        return {}
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(PLATIF_XLSX) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            st = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in st.findall("s:si", ns):
                shared.append("".join(t.text or "" for t in si.findall(".//s:t", ns)))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in sheet.findall(".//s:row", ns):
            vals: list[str] = []
            for c in row.findall("s:c", ns):
                t = c.attrib.get("t")
                v = c.find("s:v", ns)
                if v is None or v.text is None:
                    vals.append("")
                elif t == "s":
                    vals.append(shared[int(v.text)])
                else:
                    vals.append(v.text)
            rows.append(vals)

    if len(rows) < 2:
        return {}
    headers = rows[0]
    by_pid: dict[str, dict[str, str]] = {}
    for r in rows[1:]:
        padded = r + [""] * max(0, len(headers) - len(r))
        rec = dict(zip(headers, padded))
        pid = rec.get("Patient ID", "").strip()
        if pid:
            by_pid[pid] = rec
    return by_pid


def _extract_platif_case_images(patient_id: str, case_id: str, assessment_id: int) -> dict[str, str]:
    """Extract real radiograph, expert tibia mask overlay, and 2D coronal CT slice from PlaTiF .mat."""
    if not PLATIF_ZIP.exists():
        return {}
    member = f"Patient Data_Part 3/Patient_ID_{patient_id}.mat"
    extract_dir = SAMPLES_DIR / "platif" / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PLATIF_ZIP) as z:
        if member not in z.namelist():
            return {}
        z.extract(member, extract_dir)

    mat_path = extract_dir / member
    mat = scipy.io.loadmat(mat_path)
    rec = mat[f"Patient_ID_{patient_id}"][0, 0]
    im0 = rec["im0"][0, 0]
    orig = im0["OriginalImage"]
    bw = im0["BW"]
    ct2d = rec["Coronal_CT"]

    out_dir = CASES_DIR / case_id / f"assessment_{assessment_id}" / "real_platif"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Original AP radiograph
    xray_norm = np.clip(orig, 0, 1) if orig.max() <= 1.0 else np.clip(orig / max(orig.max(), 1e-6), 0, 1)
    ap_u8 = (xray_norm * 255).astype(np.uint8)
    ap_path = out_dir / f"PLATIF_{patient_id}_xray_ap.png"
    Image.fromarray(ap_u8).save(ap_path)

    # 2. Radiograph + Expert Tibia Mask Overlay (BW)
    rgb = np.stack([ap_u8, ap_u8, ap_u8], axis=-1)
    mask_bool = bw > 0
    rgb[mask_bool] = (rgb[mask_bool] * 0.65 + np.array([0, 113, 227]) * 0.35).astype(np.uint8)
    mask_path = out_dir / f"PLATIF_{patient_id}_xray_mask.png"
    Image.fromarray(rgb).save(mask_path)

    # 3. 2D Coronal CT Slice
    ct_min, ct_max = float(np.min(ct2d)), float(np.max(ct2d))
    ct_norm = (ct2d - ct_min) / max(ct_max - ct_min, 1e-6)
    ct_path = out_dir / f"PLATIF_{patient_id}_coronal_ct2d.png"
    Image.fromarray((ct_norm * 255).astype(np.uint8)).save(ct_path)

    return {
        "xray_ap_relpath": ap_path.relative_to(DATA_DIR).as_posix(),
        "xray_mask_relpath": mask_path.relative_to(DATA_DIR).as_posix(),
        "coronal_ct_2d_relpath": ct_path.relative_to(DATA_DIR).as_posix(),
    }


def seed_real_public_cases(db: Session) -> dict[str, Any]:
    """Import real public clinical datasets from Zenodo (VSDFullBody + PlaTiF). Zero synthetic data."""
    imported: list[str] = []

    # 1A. Real Single-Leg Lower-Limb CT with Published GT Benchmark (Zenodo 8270365 + 8302449, Subject 016)
    if VSD_016_CT_PATH.exists() and db.get(PatientCase, "VSD-016") is None:
        c_016 = PatientCase(
            id="VSD-016",
            age=95,
            sex="F",
            fracture_location="Right lower limb (Tibia & Fibula) — Intact Reference",
            ao_classification="Intact Control (GT Validated)",
            open_closed="N/A",
            surgical_intervention="None (Anatomical reference CT)",
            fixation_type="None",
            notes=(
                "Real human CT from VSDFullBody (Zenodo 8270365 / 8302449, Subject 016, 0.75 x 0.75 x 0.6 mm). "
                "Segmented via TotalSegmentator AI (appendicular_bones, Dice 0.917 vs published GT)."
            ),
            is_intact_reference=1,
            data_source="VSDFullBody (Zenodo 8270365)",
        )
        db.add(c_016)
        db.flush()

        t0_016 = Assessment(
            case_id="VSD-016",
            timepoint_label="T0",
            days_post_injury=0,
            modality="CT",
            healing_phase="Intact Reference",
            clinical_notes="Unilateral 0.6 mm clinical lower-leg CT benchmarked against published 3D Slicer GT.",
        )
        db.add(t0_016)
        db.flush()

        run_016 = CTScanRun(
            assessment_id=t0_016.id,
            status="queued",
            input_relpath=VSD_016_CT_PATH.relative_to(DATA_DIR).as_posix(),
            segmentation_backend="totalsegmentator",
        )
        db.add(run_016)
        db.add(
            AuditLog(
                case_id="VSD-016",
                assessment_id=t0_016.id,
                actor="dataset_importer",
                action="real_public_ct_imported",
                details_json={"source": "Zenodo 8270365/8302449 (016)", "backend": "totalsegmentator"},
            )
        )
        db.commit()
        db.refresh(run_016)
        process_ct_run_sync(run_016.id, backend="totalsegmentator")
        imported.append("VSD-016")

    # 1B. Real 3D Human Lower-Limb CT Reference (Zenodo VSDFullBody 8270365, z025)
    if VSD_CT_PATH.exists() and db.get(PatientCase, "VSD-025") is None:
        c_vsd = PatientCase(
            id="VSD-025",
            age=95,
            sex="M",
            fracture_location="Lower extremity (Tibia & Fibula) — Intact Reference",
            ao_classification="Intact Control",
            open_closed="N/A",
            surgical_intervention="None (Anatomical reference CT)",
            fixation_type="None",
            notes="Real human CT from VSDFullBody (Zenodo 8270365, Subject z025, CC BY-NC 3.0). 0.977 x 0.977 x 1.0 mm.",
            is_intact_reference=1,
            data_source="VSDFullBody (Zenodo 8270365)",
        )
        db.add(c_vsd)
        db.flush()

        t0 = Assessment(
            case_id="VSD-025",
            timepoint_label="T0",
            days_post_injury=0,
            modality="CT",
            healing_phase="Intact Reference",
            clinical_notes="Real 3D lower-limb CT benchmark for cortical thickness and HU distribution.",
        )
        db.add(t0)
        db.flush()

        run = CTScanRun(
            assessment_id=t0.id,
            status="queued",
            input_relpath=VSD_CT_PATH.relative_to(DATA_DIR).as_posix(),
            segmentation_backend="auto_lower_limb",
        )
        db.add(run)
        db.add(
            AuditLog(
                case_id="VSD-025",
                assessment_id=t0.id,
                actor="dataset_importer",
                action="real_public_ct_imported",
                details_json={"source": "Zenodo 8270365 (z025)", "license": "CC BY-NC 3.0"},
            )
        )
        db.commit()
        db.refresh(run)
        process_ct_run_sync(run.id)
        imported.append("VSD-025")

    # 2. Real Clinical Fracture Cases from PlaTiF (Zenodo 18007397)
    meta_by_pid = _read_platif_metadata()
    for pid in ("190", "191", "192"):
        case_id = f"PLATIF-{pid}"
        if db.get(PatientCase, case_id) is not None or not PLATIF_ZIP.exists():
            continue
        meta = meta_by_pid.get(pid, {})
        age_str = meta.get("Age", "").strip()
        age = int(age_str) if age_str.isdigit() else None
        gender_raw = meta.get("Gender", "").strip()
        sex = "M" if gender_raw.lower().startswith("m") else ("F" if gender_raw.lower().startswith("f") else None)
        side = meta.get("Fracture of the Right (R) or Left (L) Tibia", "").strip()
        side_label = "Right" if side == "R" else ("Left" if side == "L" else "")
        schatzker = meta.get("Fracture Type of  Schatzker Classification", "").strip() or "Unclassified"
        diag = meta.get("Diagnosis Title", "Tibial plateau fracture").replace("\n", " ").strip()

        c = PatientCase(
            id=case_id,
            age=age,
            sex=sex,
            fracture_location=f"{side_label} proximal tibia (Plateau)".strip(),
            ao_classification=f"Schatzker {schatzker}",
            open_closed="Closed",
            surgical_intervention="Clinical trauma admission",
            fixation_type="Pre-op / Admission",
            notes=f"{diag}. Real clinical case from PlaTiF (Zenodo 18007397, CC BY 4.0).",
            is_intact_reference=0,
            data_source="PlaTiF (Zenodo 18007397)",
        )
        db.add(c)
        db.flush()

        a = Assessment(
            case_id=case_id,
            timepoint_label="T0",
            days_post_injury=0,
            modality="XRAY",
            healing_phase="Inflammatory",
            clinical_notes=(
                f"Real PlaTiF radiograph + expert tibia mask + 2D coronal CT slice (Schatzker {schatzker}). "
                "mRUST and physiotherapy scores intentionally blank until clinician evaluation."
            ),
        )
        db.add(a)
        db.flush()

        img_paths = _extract_platif_case_images(pid, case_id, a.id)
        for k, v in img_paths.items():
            setattr(a, k, v)

        db.add(
            AuditLog(
                case_id=case_id,
                assessment_id=a.id,
                actor="dataset_importer",
                action="real_platif_case_imported",
                details_json={"patient_id": pid, "schatzker": schatzker, "source": "Zenodo 18007397"},
            )
        )
        db.commit()
        imported.append(case_id)

    return {"status": "imported_real_public_data", "cases": imported}
