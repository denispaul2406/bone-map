from __future__ import annotations

import hashlib
import os
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pydicom
import SimpleITK as sitk
from PIL import Image


@dataclass
class LoadedCTVolume:
    """Standardized CT volume in canonical LPS orientation with anonymised metadata."""

    image: sitk.Image
    array_zyx: np.ndarray
    spacing_xyz: tuple[float, float, float]
    origin_xyz: tuple[float, float, float]
    source_hash: str
    metadata: dict[str, Any]
    nifti_path: Path | None = None


def _compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    else:
        for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
            h.update(file_path.name.encode("utf-8"))
            h.update(str(file_path.stat().st_size).encode("utf-8"))
    return h.hexdigest()[:16]


def _extract_anonymised_dicom_meta(dcm_path: Path) -> dict[str, Any]:
    """Read technical scan parameters while stripping all PHI fields."""
    ds = pydicom.dcmread(str(dcm_path), stop_before_pixels=True, force=True)
    return {
        "modality": str(getattr(ds, "Modality", "CT")),
        "slice_thickness_mm": _safe_float(getattr(ds, "SliceThickness", None)),
        "kvp": _safe_float(getattr(ds, "KVP", None)),
        "convolution_kernel": str(getattr(ds, "ConvolutionKernel", "")).strip() or None,
        "manufacturer": str(getattr(ds, "Manufacturer", "")).strip() or None,
        "study_year": str(getattr(ds, "StudyDate", ""))[:4] or None,
        "phi_stripped": True,
    }


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_ct_volume(input_path: Path, work_dir: Path | None = None) -> LoadedCTVolume:
    """Load a CT volume from NIfTI (.nii/.nii.gz), a DICOM directory, or a DICOM .zip."""
    input_path = Path(input_path)
    source_hash = _compute_file_sha256(input_path)
    meta: dict[str, Any] = {"modality": "CT", "phi_stripped": True}

    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        if work_dir is None:
            work_dir = input_path.parent / f"unzipped_{source_hash}"
        work_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(input_path, "r") as zf:
            _safe_extract_zip(zf, work_dir)
        dicom_dir = _find_dicom_series_dir(work_dir)
        image, dcm_meta = _read_dicom_series(dicom_dir)
        meta.update(dcm_meta)
    elif input_path.is_dir():
        dicom_dir = _find_dicom_series_dir(input_path)
        image, dcm_meta = _read_dicom_series(dicom_dir)
        meta.update(dcm_meta)
    elif input_path.is_file() and (
        input_path.name.endswith(".nii.gz") or input_path.suffix.lower() == ".nii"
    ):
        image = sitk.ReadImage(str(input_path), sitk.sitkFloat32)
        meta["source_format"] = "NIfTI"
    else:
        raise ValueError(f"Unsupported CT input format: {input_path}")

    # Reorient to canonical LPS for consistent anatomical Left/Right/Anterior/Posterior axes
    image = sitk.DICOMOrient(image, "LPS")
    image = sitk.Cast(image, sitk.sitkFloat32)

    array_zyx = sitk.GetArrayFromImage(image)
    spacing = tuple(float(s) for s in image.GetSpacing())
    origin = tuple(float(o) for o in image.GetOrigin())

    meta["dimensions_zyx"] = [int(x) for x in array_zyx.shape]
    meta["voxel_spacing_mm"] = [round(s, 4) for s in spacing]

    nifti_out: Path | None = None
    if work_dir is not None:
        work_dir.mkdir(parents=True, exist_ok=True)
        nifti_out = work_dir / "ct_canonical.nii.gz"
        sitk.WriteImage(image, str(nifti_out))

    return LoadedCTVolume(
        image=image,
        array_zyx=array_zyx,
        spacing_xyz=spacing,  # type: ignore[arg-type]
        origin_xyz=origin,  # type: ignore[arg-type]
        source_hash=source_hash,
        metadata=meta,
        nifti_path=nifti_out,
    )


def _safe_extract_zip(zf: zipfile.ZipFile, dest_dir: Path, max_uncompressed_bytes: int = 1_500_000_000) -> None:
    """Extract zip members safely, preventing Zip-Slip path traversal and zip bombs."""
    dest_resolved = dest_dir.resolve()
    total_size = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        total_size += info.file_size
        if total_size > max_uncompressed_bytes:
            raise ValueError("ZIP archive exceeds maximum allowed uncompressed size (1.5 GB).")
        target_path = (dest_resolved / info.filename).resolve()
        if not target_path.is_relative_to(dest_resolved):
            raise ValueError(f"Unsafe path detected inside ZIP archive: {info.filename}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, target_path.open("wb") as dst:
            while chunk := src.read(1024 * 1024):
                dst.write(chunk)


def _find_dicom_series_dir(root: Path) -> Path:
    """Locate the directory containing the largest valid DICOM slice series."""
    reader = sitk.ImageSeriesReader()
    best_dir: Path | None = None
    best_count = 0
    for candidate in [root, *(p for p in root.rglob("*") if p.is_dir())]:
        try:
            series_ids = reader.GetGDCMSeriesIDs(str(candidate))
        except RuntimeError:
            series_ids = ()
        for sid in series_ids:
            files = reader.GetGDCMSeriesFileNames(str(candidate), sid)
            if len(files) > best_count:
                best_count = len(files)
                best_dir = candidate
    if best_dir is None or best_count == 0:
        raise ValueError(f"No readable DICOM series found inside {root}")
    return best_dir


def _read_dicom_series(dicom_dir: Path) -> tuple[sitk.Image, dict[str, Any]]:
    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(str(dicom_dir))
    if not series_ids:
        raise ValueError(f"No DICOM series IDs found in {dicom_dir}")
    # Pick series with the most slices
    best_files: tuple[str, ...] = ()
    for sid in series_ids:
        files = reader.GetGDCMSeriesFileNames(str(dicom_dir), sid)
        if len(files) > len(best_files):
            best_files = files
    reader.SetFileNames(best_files)
    image = reader.Execute()
    meta = _extract_anonymised_dicom_meta(Path(best_files[0]))
    meta["slice_count"] = len(best_files)
    meta["source_format"] = "DICOM"
    return image, meta


def window_ct_slice_to_png(
    slice_2d: np.ndarray,
    out_path: Path,
    window_level: float = 450.0,
    window_width: float = 1800.0,
    overlay_mask: np.ndarray | None = None,
) -> Path:
    """Render a 2D CT slice in bone window to PNG with optional semi-transparent mask overlay."""
    low = window_level - window_width / 2.0
    high = window_level + window_width / 2.0
    clipped = np.clip(slice_2d, low, high)
    norm = ((clipped - low) / max(high - low, 1e-6) * 255.0).astype(np.uint8)
    rgb = np.stack([norm, norm, norm], axis=-1)

    if overlay_mask is not None:
        # Label 1: tibia cortical/bone (apple blue), Label 2: callus (amber), Label 3: metal (cyan)
        tibia = overlay_mask == 1
        callus = overlay_mask == 2
        metal = overlay_mask == 3
        rgb[tibia] = (rgb[tibia] * 0.65 + np.array([0, 113, 227]) * 0.35).astype(np.uint8)
        rgb[callus] = (rgb[callus] * 0.45 + np.array([245, 158, 11]) * 0.55).astype(np.uint8)
        rgb[metal] = (rgb[metal] * 0.40 + np.array([56, 189, 248]) * 0.60).astype(np.uint8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.parent / f".{out_path.name}.{uuid.uuid4().hex[:8]}.tmp"
    Image.fromarray(np.flipud(rgb)).save(tmp_path, format="PNG")
    os.replace(tmp_path, out_path)
    return out_path
