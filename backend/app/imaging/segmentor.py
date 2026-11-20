from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import SimpleITK as sitk
from scipy import ndimage
from skimage import measure, morphology

from app.imaging.loader import LoadedCTVolume

logger = logging.getLogger(__name__)

SegmentationBackend = Literal["auto_lower_limb", "totalsegmentator", "manual_nifti"]


@dataclass
class SegmentationResult:
    """Voxel-aligned anatomical and fracture segmentation masks."""

    label_map_zyx: np.ndarray  # 0=bg, 1=tibia, 2=callus, 3=metal, 4=fibula
    tibia_mask: np.ndarray
    cortical_mask: np.ndarray
    callus_mask: np.ndarray
    early_callus_mask: np.ndarray
    hard_callus_mask: np.ndarray
    metal_mask: np.ndarray
    metal_exclusion_mask: np.ndarray
    fibula_mask: np.ndarray
    fracture_z_range: tuple[int, int] | None
    method_used: str
    warnings: list[str]
    label_nifti_path: Path | None = None


CORTICAL_HU_THRESHOLD = 750.0


def segment_tibia_ct(
    volume: LoadedCTVolume,
    out_dir: Path,
    backend: SegmentationBackend = "auto_lower_limb",
    manual_mask_path: Path | None = None,
    is_intact_reference: bool = False,
) -> SegmentationResult:
    """Segment tibia, fibula, metal hardware, and fracture callus from CT."""
    out_dir.mkdir(parents=True, exist_ok=True)
    hu = volume.array_zyx
    spacing = volume.spacing_xyz  # (dx, dy, dz)
    voxel_vol_mm3 = spacing[0] * spacing[1] * spacing[2]
    warnings: list[str] = []

    if manual_mask_path is not None and manual_mask_path.exists():
        return _from_manual_label_map(volume, manual_mask_path, out_dir, is_intact_reference=is_intact_reference)

    if backend == "totalsegmentator":
        try:
            return _run_totalsegmentator_backend(volume, out_dir, is_intact_reference=is_intact_reference)
        except Exception as exc:
            logger.warning("TotalSegmentator unavailable/failed (%s); falling back to lower-limb HU engine.", exc)
            warnings.append(f"TotalSegmentator fallback triggered: {exc}")

    # 1. Metal hardware segmentation (IM nails, plates, screws >= 120 mm^3)
    metal_raw = hu >= 2500.0
    metal_mask = _keep_min_volume_components(metal_raw, voxel_vol_mm3, min_mm3=120.0)
    if np.any(metal_mask):
        metal_exclusion_mask = ndimage.binary_dilation(metal_mask, iterations=2)
        warnings.append(
            "Metallic fixation hardware detected (HU >= 2500); artifact exclusion ring applied around implants."
        )
    else:
        metal_exclusion_mask = np.zeros_like(metal_mask, dtype=bool)

    # 2. Body foreground mask (removes CT scanner table & external air)
    body_raw = hu > -350.0
    body_mask = _keep_largest_component(body_raw)
    if not np.any(body_mask):
        body_mask = np.ones_like(hu, dtype=bool)

    # 3. Dense cortical bone fragments (HU >= 750) vs lower-density callus (150-750 HU)
    core_bone_raw = (hu >= 750.0) & body_mask & (~metal_exclusion_mask)
    mineral_clean = _keep_min_volume_components(core_bone_raw, voxel_vol_mm3, min_mm3=150.0)

    # Fill enclosed marrow cavities slice-by-slice to form solid anatomical bone envelopes
    solid_bones = _fill_medullary_cavities_2d(mineral_clean)

    # 4. Separate Tibia (larger diaphyseal cross-section) vs Fibula (smaller lateral bone)
    tibia_mask, fibula_mask = _separate_tibia_and_fibula(
        solid_bones=solid_bones,
        spacing_xyz=spacing,
        voxel_vol_mm3=voxel_vol_mm3,
    )

    if not np.any(tibia_mask):
        warnings.append("No primary tibial volume isolated; check CT field-of-view or upload a 3D Slicer mask.")

    # 5. Cortical shell inside tibia (HU >= 750 and excluding metal)
    cortical_mask = tibia_mask & (hu >= 750.0) & (~metal_exclusion_mask)

    # 6. Identify fracture zone along Z and extract peri-fracture mineralised callus
    if is_intact_reference:
        fracture_z_range = None
        early_callus_mask = np.zeros_like(hu, dtype=bool)
        hard_callus_mask = np.zeros_like(hu, dtype=bool)
    else:
        fracture_z_range = _detect_fracture_z_band(tibia_mask, cortical_mask, spacing)
        early_callus_mask, hard_callus_mask = _extract_callus_masks(
            hu=hu,
            tibia_mask=tibia_mask,
            cortical_mask=cortical_mask,
            fibula_mask=fibula_mask,
            metal_exclusion_mask=metal_exclusion_mask,
            body_mask=body_mask,
            fracture_z_range=fracture_z_range,
            spacing_xyz=spacing,
        )
    callus_mask = early_callus_mask | hard_callus_mask

    # Compose standard multi-label volume (compatible with 3D Slicer)
    label_map = np.zeros(hu.shape, dtype=np.uint8)
    label_map[fibula_mask] = 4
    label_map[tibia_mask] = 1
    label_map[callus_mask] = 2
    label_map[metal_mask] = 3

    label_nifti_path = out_dir / "segmentation_labels.nii.gz"
    _save_label_nifti(label_map, volume.image, label_nifti_path)

    return SegmentationResult(
        label_map_zyx=label_map,
        tibia_mask=tibia_mask,
        cortical_mask=cortical_mask,
        callus_mask=callus_mask,
        early_callus_mask=early_callus_mask,
        hard_callus_mask=hard_callus_mask,
        metal_mask=metal_mask,
        metal_exclusion_mask=metal_exclusion_mask,
        fibula_mask=fibula_mask,
        fracture_z_range=fracture_z_range,
        method_used="auto_lower_limb_hu_v1",
        warnings=warnings,
        label_nifti_path=label_nifti_path,
    )


def _needs_resample(img: sitk.Image, ref: sitk.Image) -> bool:
    if img.GetSize() != ref.GetSize():
        return True
    if not np.allclose(img.GetSpacing(), ref.GetSpacing(), atol=1e-3):
        return True
    if not np.allclose(img.GetOrigin(), ref.GetOrigin(), atol=1e-2):
        return True
    if not np.allclose(img.GetDirection(), ref.GetDirection(), atol=1e-3):
        return True
    return False


def _from_manual_label_map(
    volume: LoadedCTVolume,
    manual_mask_path: Path,
    out_dir: Path,
    is_intact_reference: bool = False,
) -> SegmentationResult:
    """Re-ingest a researcher-corrected 3D Slicer NIfTI label map."""
    mask_img = sitk.ReadImage(str(manual_mask_path), sitk.sitkUInt8)
    mask_img = sitk.DICOMOrient(mask_img, "LPS")
    if _needs_resample(mask_img, volume.image):
        mask_img = sitk.Resample(
            mask_img,
            volume.image,
            sitk.Transform(),
            sitk.sitkNearestNeighbor,
            0,
            sitk.sitkUInt8,
        )
    label_map = sitk.GetArrayFromImage(mask_img)
    hu = volume.array_zyx
    tibia_mask = label_map == 1
    callus_mask = np.zeros_like(tibia_mask, dtype=bool) if is_intact_reference else (label_map == 2)
    metal_mask = label_map == 3
    fibula_mask = label_map == 4
    metal_exclusion = (
        ndimage.binary_dilation(metal_mask, iterations=2)
        if np.any(metal_mask)
        else np.zeros_like(metal_mask, dtype=bool)
    )
    cortical_mask = tibia_mask & (hu >= CORTICAL_HU_THRESHOLD) & (~metal_exclusion)
    early_callus = callus_mask & (hu < 450.0)
    hard_callus = callus_mask & (hu >= 450.0)
    fracture_z = None if is_intact_reference else _detect_fracture_z_band(tibia_mask, cortical_mask, volume.spacing_xyz)

    out_label_path = out_dir / "segmentation_labels.nii.gz"
    _save_label_nifti(label_map, volume.image, out_label_path)

    return SegmentationResult(
        label_map_zyx=label_map,
        tibia_mask=tibia_mask,
        cortical_mask=cortical_mask,
        callus_mask=callus_mask,
        early_callus_mask=early_callus,
        hard_callus_mask=hard_callus,
        metal_mask=metal_mask,
        metal_exclusion_mask=metal_exclusion,
        fibula_mask=fibula_mask,
        fracture_z_range=fracture_z,
        method_used="manual_slicer_nifti",
        warnings=["Using researcher-corrected segmentation mask."],
        label_nifti_path=out_label_path,
    )


def _run_totalsegmentator_backend(
    volume: LoadedCTVolume,
    out_dir: Path,
    is_intact_reference: bool = False,
) -> SegmentationResult:
    """Optional TotalSegmentator appendicular_bones runner via isolated subprocess for Windows spawn & 6 GB VRAM safety."""
    import torch

    if volume.nifti_path is None or not volume.nifti_path.exists():
        tmp_in = out_dir / "ct_canonical.nii.gz"
        sitk.WriteImage(volume.image, str(tmp_in))
        in_path = tmp_in
    else:
        in_path = volume.nifti_path

    ts_out = out_dir / "totalseg_appendicular.nii.gz"
    device = "gpu" if torch.cuda.is_available() else "cpu"
    cmd = [
        sys.executable,
        "-m",
        "totalsegmentator.bin.TotalSegmentator",
        "-i",
        str(in_path),
        "-o",
        str(ts_out),
        "--task",
        "appendicular_bones",
        "--device",
        device,
        "--ml",
        "--quiet",
        "--nr_thr_resamp",
        "1",
        "--nr_thr_saving",
        "1",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout or "TotalSegmentator subprocess failed").strip()[-400:])

    ts_img = sitk.ReadImage(str(ts_out), sitk.sitkUInt8)
    ts_img = sitk.DICOMOrient(ts_img, "LPS")
    if _needs_resample(ts_img, volume.image):
        ts_img = sitk.Resample(
            ts_img, volume.image, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8
        )
    ts_arr = sitk.GetArrayFromImage(ts_img)
    hu = volume.array_zyx
    # TotalSegmentator appendicular_bones class map: 2=tibia, 3=fibula
    tibia_mask = ts_arr == 2
    fibula_mask = ts_arr == 3
    metal_mask = _keep_min_volume_components(hu >= 2500.0, float(np.prod(volume.spacing_xyz)), min_mm3=120.0)
    metal_exclusion = (
        ndimage.binary_dilation(metal_mask, iterations=2)
        if np.any(metal_mask)
        else np.zeros_like(metal_mask, dtype=bool)
    )
    cortical_mask = tibia_mask & (hu >= CORTICAL_HU_THRESHOLD) & (~metal_exclusion)
    body_mask = _keep_largest_component(hu > -350.0)
    if not np.any(body_mask):
        body_mask = np.ones_like(hu, dtype=bool)
    if is_intact_reference:
        fracture_z = None
        early_callus = np.zeros_like(hu, dtype=bool)
        hard_callus = np.zeros_like(hu, dtype=bool)
    else:
        fracture_z = _detect_fracture_z_band(tibia_mask, cortical_mask, volume.spacing_xyz)
        early_callus, hard_callus = _extract_callus_masks(
            hu=hu,
            tibia_mask=tibia_mask,
            cortical_mask=cortical_mask,
            fibula_mask=fibula_mask,
            metal_exclusion_mask=metal_exclusion,
            body_mask=body_mask,
            fracture_z_range=fracture_z,
            spacing_xyz=volume.spacing_xyz,
        )
    callus_mask = early_callus | hard_callus

    label_map = np.zeros(hu.shape, dtype=np.uint8)
    label_map[fibula_mask] = 4
    label_map[tibia_mask] = 1
    label_map[callus_mask] = 2
    label_map[metal_mask] = 3
    label_nifti_path = out_dir / "segmentation_labels.nii.gz"
    _save_label_nifti(label_map, volume.image, label_nifti_path)

    return SegmentationResult(
        label_map_zyx=label_map,
        tibia_mask=tibia_mask,
        cortical_mask=cortical_mask,
        callus_mask=callus_mask,
        early_callus_mask=early_callus,
        hard_callus_mask=hard_callus,
        metal_mask=metal_mask,
        metal_exclusion_mask=metal_exclusion,
        fibula_mask=fibula_mask,
        fracture_z_range=fracture_z,
        method_used="totalsegmentator_appendicular_bones",
        warnings=[],
        label_nifti_path=label_nifti_path,
    )


def _keep_largest_component(mask: np.ndarray) -> np.ndarray:
    labeled, num = ndimage.label(mask)
    if num == 0:
        return np.zeros_like(mask, dtype=bool)
    counts = np.bincount(labeled.ravel())
    counts[0] = 0
    return labeled == int(np.argmax(counts))


def _keep_min_volume_components(
    mask: np.ndarray, voxel_vol_mm3: float, min_mm3: float
) -> np.ndarray:
    labeled, num = ndimage.label(mask)
    if num == 0:
        return np.zeros_like(mask, dtype=bool)
    counts = np.bincount(labeled.ravel())
    min_voxels = max(1, int(min_mm3 / max(voxel_vol_mm3, 1e-6)))
    keep = np.where(counts >= min_voxels)[0]
    keep = keep[keep != 0]
    if len(keep) == 0:
        return np.zeros_like(mask, dtype=bool)
    return np.isin(labeled, keep)


def _fill_medullary_cavities_2d(mask: np.ndarray) -> np.ndarray:
    filled = np.zeros_like(mask, dtype=bool)
    selem = morphology.disk(1)
    for z in range(mask.shape[0]):
        sl = mask[z]
        if not np.any(sl):
            continue
        closed = morphology.closing(sl, selem)
        filled[z] = ndimage.binary_fill_holes(closed)
    return filled


def _separate_tibia_and_fibula(
    solid_bones: np.ndarray,
    spacing_xyz: tuple[float, float, float],
    voxel_vol_mm3: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Identify tibial fragments vs fibula using cross-sectional area & volume."""
    labeled = measure.label(solid_bones, connectivity=2)
    props = measure.regionprops(labeled)
    if not props:
        return np.zeros_like(solid_bones, dtype=bool), np.zeros_like(solid_bones, dtype=bool)

    pixel_area_mm2 = spacing_xyz[0] * spacing_xyz[1]
    tibia_labels: list[int] = []
    fibula_labels: list[int] = []

    # Rank regions by volume
    props_sorted = sorted(props, key=lambda p: p.area, reverse=True)
    for idx, prop in enumerate(props_sorted):
        vol_mm3 = prop.area * voxel_vol_mm3
        if vol_mm3 < 800.0:
            continue
        comp_mask = labeled == prop.label
        slice_areas = comp_mask.sum(axis=(1, 2)) * pixel_area_mm2
        nonzero_areas = slice_areas[slice_areas > 0]
        p75_area = float(np.percentile(nonzero_areas, 75)) if len(nonzero_areas) else 0.0

        # Tibia diaphysis/metaphysis cross-section is typically > 240 mm^2; fibula is ~70-170 mm^2
        if idx == 0 or p75_area >= 230.0:
            tibia_labels.append(prop.label)
        elif p75_area >= 40.0 and vol_mm3 >= 2000.0:
            fibula_labels.append(prop.label)

    tibia_mask = np.isin(labeled, tibia_labels) if tibia_labels else np.zeros_like(solid_bones, dtype=bool)
    fibula_mask = np.isin(labeled, fibula_labels) if fibula_labels else np.zeros_like(solid_bones, dtype=bool)
    return tibia_mask, fibula_mask


def _detect_fracture_z_band(
    tibia_mask: np.ndarray,
    cortical_mask: np.ndarray,
    spacing_xyz: tuple[float, float, float],
) -> tuple[int, int] | None:
    """Locate the fracture Z-band via gap detection or cortical area irregularity."""
    z_any = np.where(np.any(tibia_mask, axis=(1, 2)))[0]
    if len(z_any) < 6:
        return None
    z_min, z_max = int(z_any[0]), int(z_any[-1])

    # Check if tibia has disconnected major proximal/distal components separated along Z
    labeled = measure.label(tibia_mask, connectivity=2)
    props = sorted(measure.regionprops(labeled), key=lambda p: p.area, reverse=True)
    major = [p for p in props if p.area * np.prod(spacing_xyz) > 3000.0]

    margin_slices = max(3, int(round(12.0 / max(spacing_xyz[2], 0.2))))
    if len(major) >= 2:
        # Sort top 2 major fragments along Z
        f1, f2 = sorted(major[:2], key=lambda p: p.centroid[0])
        gap_start = int(f1.bbox[3])  # max_z of proximal/inferior fragment
        gap_end = int(f2.bbox[0])    # min_z of second fragment
        low = max(z_min, min(gap_start, gap_end) - margin_slices)
        high = min(z_max, max(gap_start, gap_end) + margin_slices)
        return (low, high)

    # Single connected tibia (partially/fully bridged or hairline): inspect middle 60% diaphysis
    span = z_max - z_min
    inner_lo = z_min + int(0.2 * span)
    inner_hi = z_max - int(0.2 * span)
    if inner_hi <= inner_lo + 4:
        return (z_min, z_max)

    cort_areas = cortical_mask.sum(axis=(1, 2)).astype(float)
    sub = cort_areas[inner_lo:inner_hi]
    if len(sub) == 0:
        return (inner_lo, inner_hi)

    # Find local minimum in cortical area or max gradient (callus/fracture disruption)
    smooth = ndimage.gaussian_filter1d(sub, sigma=1.5)
    target_idx = int(np.argmin(smooth)) + inner_lo
    return (max(z_min, target_idx - margin_slices), min(z_max, target_idx + margin_slices))


def _extract_callus_masks(
    hu: np.ndarray,
    tibia_mask: np.ndarray,
    cortical_mask: np.ndarray,
    fibula_mask: np.ndarray,
    metal_exclusion_mask: np.ndarray,
    body_mask: np.ndarray,
    fracture_z_range: tuple[int, int] | None,
    spacing_xyz: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Segment peri-fracture mineralised callus (early 150-450 HU, hard 450-1100 HU)."""
    empty = np.zeros_like(hu, dtype=bool)
    if fracture_z_range is None or not np.any(tibia_mask):
        return empty, empty

    z0, z1 = fracture_z_range
    z_band = np.zeros_like(hu, dtype=bool)
    z_band[z0 : z1 + 1] = True

    # Peri-fracture ROI: within ~10 mm radially of tibial mask inside fracture Z-band
    rad_iters = max(2, int(round(8.0 / max(min(spacing_xyz[0], spacing_xyz[1]), 0.3))))
    roi_seed = tibia_mask & z_band
    if not np.any(roi_seed):
        return empty, empty

    peri_roi = np.zeros_like(hu, dtype=bool)
    for z in range(z0, z1 + 1):
        if np.any(roi_seed[z]):
            peri_roi[z] = ndimage.binary_dilation(roi_seed[z], iterations=rad_iters)

    # Exclude fibula, metal exclusion ring, and outside body
    peri_roi = peri_roi & body_mask & (~fibula_mask) & (~metal_exclusion_mask)

    # Early/soft mineralising callus: 150-450 HU outside dense cortex
    early_callus = peri_roi & (~cortical_mask) & (hu >= 150.0) & (hu < 450.0)
    # Hard periosteal/bridging callus: 450-750 HU (or 450-1150 HU outside original solid tibia envelope)
    hard_callus = (
        peri_roi
        & (~cortical_mask)
        & (((hu >= 450.0) & (hu < 750.0)) | ((~tibia_mask) & (hu >= 450.0) & (hu <= 1150.0)))
    )

    voxel_vol = float(np.prod(spacing_xyz))
    early_callus = _keep_min_volume_components(early_callus, voxel_vol, min_mm3=30.0)
    hard_callus = _keep_min_volume_components(hard_callus, voxel_vol, min_mm3=30.0)
    return early_callus, hard_callus


def _save_label_nifti(label_map: np.ndarray, ref_image: sitk.Image, out_path: Path) -> None:
    out_img = sitk.GetImageFromArray(label_map.astype(np.uint8))
    out_img.CopyInformation(ref_image)
    sitk.WriteImage(out_img, str(out_path))
