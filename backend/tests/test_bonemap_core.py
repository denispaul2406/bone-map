from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.imaging.loader import LoadedCTVolume  # noqa: E402
from app.imaging.registration import compute_longitudinal_ct_delta  # noqa: E402
from app.imaging.segmentor import segment_tibia_ct  # noqa: E402
from app.main import _csv_safe, app  # noqa: E402
from app.quantification.architecture import quantify_bone_architecture  # noqa: E402


def _make_synthetic_loaded_volume(hu: np.ndarray, spacing=(0.8, 0.8, 1.0)) -> LoadedCTVolume:
    img = sitk.GetImageFromArray(hu.astype(np.float32))
    img.SetSpacing(spacing)
    return LoadedCTVolume(
        image=img,
        array_zyx=hu.astype(np.float32),
        spacing_xyz=spacing,
        origin_xyz=(0.0, 0.0, 0.0),
        source_hash="test_hash",
        metadata={"dimensions_zyx": list(hu.shape), "voxel_spacing_mm": list(spacing)},
        nifti_path=None,
    )


def test_security_and_validation_contracts():
    client = TestClient(app)
    assert client.get("/api/files/bonemap.db").status_code == 404
    assert client.get("/api/files/../backend/app/main.py").status_code == 404
    assert client.post("/api/cases", json={"id": "../evil"}).status_code == 422
    assert client.post("/api/cases", json={"id": "a"}).status_code == 422
    assert (
        client.post(
            "/api/assessments/1/ct/attach-sample",
            json={"sample_filename": "missing.nii.gz"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/assessments/1/xray",
            data={"mrust_anterior": 5, "mrust_posterior": 2, "mrust_medial": 2, "mrust_lateral": 2},
        ).status_code
        == 422
    )


def test_csv_formula_escaping():
    assert _csv_safe("=CMD()") == "'=CMD()"
    assert _csv_safe("+SUM(A1)") == "'+SUM(A1)"
    assert _csv_safe("-1+1") == "'-1+1"
    assert _csv_safe("@evil") == "'@evil"
    assert _csv_safe("BM-0001") == "BM-0001"


def test_fibula_referenced_medial_lateral_polarity(tmp_path: Path):
    """Verify lateral quadrant is placed on the fibula side for both Left and Right tibias."""
    nz, ny, nx = 60, 72, 72
    yy, xx = np.ogrid[:ny, :nx]
    for fib_x in (10, 62):
        hu = np.full((nz, ny, nx), 40.0, dtype=np.float32)
        tib_r = np.sqrt((xx - 36) ** 2 + (yy - 36) ** 2)
        fib_r = np.sqrt((xx - fib_x) ** 2 + (yy - 40) ** 2)
        tib_shell = (tib_r <= 14.0) & (tib_r >= 9.0)
        fib_shell = (fib_r <= 4.5) & (fib_r >= 2.0)
        hu[:, tib_shell] = 1150.0
        hu[:, fib_shell] = 1100.0
        # Open a cortical defect strictly in the lateral 90-degree wedge (towards fib_x)
        angles = np.degrees(np.arctan2(yy - 36, xx - 36))
        if fib_x < 36:
            wedge = (angles >= 135) | (angles < -135)
        else:
            wedge = (angles >= -45) & (angles < 45)
        defect = np.broadcast_to(tib_shell & wedge, (nz, ny, nx))
        hu[25:35][defect[25:35]] = 40.0

        vol = _make_synthetic_loaded_volume(hu)
        seg = segment_tibia_ct(vol, tmp_path / f"fib_{fib_x}", is_intact_reference=False)
        metrics, _ = quantify_bone_architecture(vol, seg)
        assert metrics.quadrant_continuity_pct["medial"] >= 90.0
        assert metrics.quadrant_continuity_pct["lateral"] < metrics.quadrant_continuity_pct["medial"]


def test_resolution_gate_high_res_vs_clinical_ct(tmp_path: Path):
    """High-res <= 0.25 mm enables trabecular metrics; 1.0 mm clinical CT gates them off."""
    nz, ny, nx = 60, 80, 80
    yy, xx = np.ogrid[:ny, :nx]
    hu = np.full((nz, ny, nx), 40.0, dtype=np.float32)
    r = np.sqrt((xx - 40) ** 2 + (yy - 40) ** 2)
    hu[:, (r <= 28) & (r >= 20)] = 1150.0
    # Add fine trabecular struts inside marrow (> 150 mm^3 total bone volume at 0.2 mm spacing)
    hu[:, ::2, ::2] = np.where(r[::2, ::2] < 19.0, 320.0, hu[:, ::2, ::2])

    vol_hi = _make_synthetic_loaded_volume(hu, spacing=(0.20, 0.20, 0.20))
    seg_hi = segment_tibia_ct(vol_hi, tmp_path / "hi", is_intact_reference=True)
    m_hi, _ = quantify_bone_architecture(vol_hi, seg_hi)
    assert m_hi.trabecular_status == "measured_high_resolution"
    assert m_hi.trabecular_thickness_mm is not None
    assert m_hi.trabecular_separation_mm is not None

    vol_lo = _make_synthetic_loaded_volume(hu, spacing=(1.0, 1.0, 1.0))
    seg_lo = segment_tibia_ct(vol_lo, tmp_path / "lo", is_intact_reference=True)
    m_lo, _ = quantify_bone_architecture(vol_lo, seg_lo)
    assert m_lo.trabecular_status == "unavailable_clinical_ct_resolution"
    assert m_lo.trabecular_thickness_mm is None


def test_longitudinal_delta_handles_missing_keys_and_zero_baseline():
    delta = compute_longitudinal_ct_delta(
        baseline_metrics={"total_callus_volume_cm3": 0.0, "cortical_thickness_mean_mm": 2.0},
        followup_metrics={"total_callus_volume_cm3": 5.0, "cortical_thickness_mean_mm": 2.5},
        dice_overlap=0.95,
    )
    assert delta.callus_volume_change_pct is None
    assert delta.cortical_thickness_change_pct == 25.0
    assert delta.bridged_quadrants_delta == 0
