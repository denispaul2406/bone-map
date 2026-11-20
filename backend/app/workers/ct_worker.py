from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db import DATA_DIR, SessionLocal
from app.imaging.loader import load_ct_volume, window_ct_slice_to_png
from app.imaging.mesh_export import export_reconstruction_glb
from app.imaging.segmentor import SegmentationBackend, segment_tibia_ct
from app.models import AuditLog, CTScanRun
from app.quantification.architecture import quantify_bone_architecture

logger = logging.getLogger(__name__)

# Single-worker executor guarantees at most 1 CT job touches the 6 GB GPU / 16 GB RAM at a time.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bonemap-ct")


def enqueue_ct_job(
    run_id: int,
    backend: SegmentationBackend = "auto_lower_limb",
    manual_mask_path: Path | None = None,
) -> None:
    _executor.submit(_process_ct_run, run_id, backend, manual_mask_path)


def process_ct_run_sync(
    run_id: int,
    backend: SegmentationBackend = "auto_lower_limb",
    manual_mask_path: Path | None = None,
) -> None:
    _process_ct_run(run_id, backend, manual_mask_path)


def _process_ct_run(
    run_id: int,
    backend: SegmentationBackend,
    manual_mask_path: Path | None,
) -> None:
    db = SessionLocal()
    try:
        run = db.get(CTScanRun, run_id)
        if run is None:
            return
        run.status = "running"
        db.commit()

        input_path = DATA_DIR / run.input_relpath
        out_dir = DATA_DIR / "cases" / run.assessment.case_id / f"assessment_{run.assessment_id}" / f"run_{run.id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        volume = load_ct_volume(input_path, work_dir=out_dir)
        is_intact = bool(run.assessment.case.is_intact_reference)
        seg = segment_tibia_ct(
            volume=volume,
            out_dir=out_dir,
            backend=backend,
            manual_mask_path=manual_mask_path,
            is_intact_reference=is_intact,
        )
        metrics, thickness_map = quantify_bone_architecture(volume, seg)
        glb_outputs = export_reconstruction_glb(volume, seg, thickness_map, out_dir=out_dir)

        # Render 3 canonical mid-slices for instant 2D inspection
        arr = volume.array_zyx
        lbl = seg.label_map_zyx
        z_mid = (
            int((seg.fracture_z_range[0] + seg.fracture_z_range[1]) // 2)
            if seg.fracture_z_range
            else arr.shape[0] // 2
        )
        y_mid = arr.shape[1] // 2
        x_mid = arr.shape[2] // 2

        axial_png = window_ct_slice_to_png(arr[z_mid], out_dir / "slice_axial.png", overlay_mask=lbl[z_mid])
        coronal_png = window_ct_slice_to_png(arr[:, y_mid, :], out_dir / "slice_coronal.png", overlay_mask=lbl[:, y_mid, :])
        sagittal_png = window_ct_slice_to_png(arr[:, :, x_mid], out_dir / "slice_sagittal.png", overlay_mask=lbl[:, :, x_mid])

        assets: dict[str, Any] = {}
        for k, p in glb_outputs.items():
            assets[k] = p.relative_to(DATA_DIR).as_posix()
        if volume.nifti_path:
            assets["ct_nifti"] = volume.nifti_path.relative_to(DATA_DIR).as_posix()
        if seg.label_nifti_path:
            assets["label_nifti"] = seg.label_nifti_path.relative_to(DATA_DIR).as_posix()
        assets["slice_axial_png"] = axial_png.relative_to(DATA_DIR).as_posix()
        assets["slice_coronal_png"] = coronal_png.relative_to(DATA_DIR).as_posix()
        assets["slice_sagittal_png"] = sagittal_png.relative_to(DATA_DIR).as_posix()
        assets["default_slice_indices"] = {"axial": z_mid, "coronal": y_mid, "sagittal": x_mid}

        run.source_hash = volume.source_hash
        run.segmentation_backend = seg.method_used
        run.metadata_json = volume.metadata
        run.metrics_json = metrics.to_dict()
        run.assets_json = assets
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)

        db.add(
            AuditLog(
                case_id=run.assessment.case_id,
                assessment_id=run.assessment_id,
                actor="pipeline",
                action="ct_quantification_completed",
                details_json={
                    "run_id": run.id,
                    "source_hash": volume.source_hash,
                    "segmentation_method": seg.method_used,
                    "voxel_spacing_mm": volume.metadata.get("voxel_spacing_mm"),
                },
            )
        )
        db.commit()
    except Exception as exc:
        logger.exception("CT processing failed for run_id=%s", run_id)
        db.rollback()
        run = db.get(CTScanRun, run_id)
        if run is not None:
            run.status = "failed"
            run.error_message = str(exc)
            db.commit()
    finally:
        db.close()
