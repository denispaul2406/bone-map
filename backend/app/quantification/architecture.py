from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy import ndimage
from skimage import measure

from app.imaging.loader import LoadedCTVolume
from app.imaging.segmentor import SegmentationResult


@dataclass
class BoneArchitectureMetrics:
    """Structured bone architecture report mapped to the BONE-MAP medical framework."""

    # 1. Cortical thickness
    cortical_thickness_mean_mm: float
    cortical_thickness_median_mm: float
    cortical_thickness_std_mm: float
    cortical_thickness_min_mm: float
    cortical_thickness_p90_mm: float

    # 2. Bone density (uncalibrated CT attenuation in HU)
    cortical_hu_mean: float
    cortical_hu_median: float
    cortical_hu_iqr: float
    callus_hu_mean: float | None
    bmd_calibrated: bool

    # 3. Trabecular microarchitecture (resolution-gated)
    trabecular_status: str
    trabecular_thickness_mm: float | None
    trabecular_separation_mm: float | None
    voxel_spacing_mm: list[float]

    # 4. Callus volume
    early_callus_volume_cm3: float
    hard_callus_volume_cm3: float
    total_callus_volume_cm3: float

    # 5. Bone geometry & alignment
    bone_length_mm: float
    coronal_angulation_deg: float
    sagittal_angulation_deg: float
    total_bone_volume_cm3: float

    # 6. Cortical continuity & 4-quadrant bridging
    bridged_quadrants_count: int
    quadrant_continuity_pct: dict[str, float]
    overall_cortical_continuity_pct: float

    # 7. Derived fracture metrics
    fracture_gap_mm: float
    fragment_displacement_mm: float
    fragment_count: int

    # Guardrails & audit metadata
    metal_present: bool
    metal_volume_cm3: float
    metal_excluded_voxels: int
    segmentation_method: str
    warnings: list[str]
    axial_thickness_profile: list[dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def quantify_bone_architecture(
    volume: LoadedCTVolume,
    seg: SegmentationResult,
) -> tuple[BoneArchitectureMetrics, np.ndarray]:
    """Compute quantitative bone architecture metrics and return 3D cortical thickness map."""
    hu = volume.array_zyx
    spacing = volume.spacing_xyz  # (dx, dy, dz)
    dx, dy, dz = spacing
    voxel_vol_cm3 = (dx * dy * dz) / 1000.0
    warnings = list(seg.warnings)

    tibia_mask = seg.tibia_mask
    cortical_mask = seg.cortical_mask
    callus_mask = seg.callus_mask
    metal_mask = seg.metal_mask

    # --- 1. Cortical thickness via 3D Euclidean Distance Transform ---
    thickness_map_mm = np.zeros_like(hu, dtype=np.float32)
    if np.any(cortical_mask):
        # Distance from each cortical voxel to nearest non-cortical voxel (periosteum or endosteum)
        # Full wall thickness ~ 2 * max medial-axis distance; estimate robustly via outer-to-inner shell EDT
        edt = ndimage.distance_transform_edt(cortical_mask, sampling=(dz, dy, dx))
        # Local maximum / ridge proxy * 2 gives true cortical wall thickness across a shell
        # Use local 3x3x3 max on cortical voxels for wall thickness, avoiding edge-voxel underestimation
        local_ridge = ndimage.maximum_filter(edt, size=3)
        thickness_map_mm[cortical_mask] = (2.0 * edt[cortical_mask]).astype(np.float32)
        # Sample interior/ridge values (> 0.5 * local_ridge) so boundary voxels don't pull mean down
        core_voxels = cortical_mask & (edt >= 0.45 * local_ridge) & (edt > 0)
        vals = (2.0 * edt[core_voxels]) if np.any(core_voxels) else thickness_map_mm[cortical_mask]
        cort_mean = float(np.mean(vals))
        cort_median = float(np.median(vals))
        cort_std = float(np.std(vals))
        cort_min = float(np.percentile(vals, 5))
        cort_p90 = float(np.percentile(vals, 90))
    else:
        cort_mean = cort_median = cort_std = cort_min = cort_p90 = 0.0

    # --- 2. CT Attenuation (HU) ---
    clean_cort = cortical_mask & (~seg.metal_exclusion_mask)
    if np.any(clean_cort):
        cort_hu_vals = hu[clean_cort]
        cort_hu_mean = float(np.mean(cort_hu_vals))
        cort_hu_median = float(np.median(cort_hu_vals))
        q75, q25 = np.percentile(cort_hu_vals, [75, 25])
        cort_hu_iqr = float(q75 - q25)
    else:
        cort_hu_mean = cort_hu_median = cort_hu_iqr = 0.0

    clean_callus = callus_mask & (~seg.metal_exclusion_mask)
    callus_hu_mean = float(np.mean(hu[clean_callus])) if np.any(clean_callus) else None

    # --- 3. Trabecular microarchitecture (Resolution-gated!) ---
    max_spacing = max(spacing)
    if max_spacing <= 0.25:
        if np.any(tibia_mask):
            trab_status = "measured_high_resolution"
            medullary = tibia_mask & (~cortical_mask) & (~seg.metal_exclusion_mask)
            trab_bone = medullary & (hu >= 180.0)
            trab_marrow = medullary & (hu < 180.0)
            tb_th = (
                float(2.0 * np.mean(ndimage.distance_transform_edt(trab_bone, sampling=(dz, dy, dx))[trab_bone]))
                if np.any(trab_bone)
                else None
            )
            tb_sp = (
                float(2.0 * np.mean(ndimage.distance_transform_edt(trab_marrow, sampling=(dz, dy, dx))[trab_marrow]))
                if np.any(trab_marrow)
                else None
            )
        else:
            trab_status = "no_tibial_mask_for_trabecular_roi"
            tb_th = None
            tb_sp = None
    else:
        trab_status = "unavailable_clinical_ct_resolution"
        tb_th = None
        tb_sp = None
        warnings.append(
            f"Trabecular thickness/separation gated off: voxel spacing {round(max_spacing, 2)} mm > 0.25 mm threshold."
        )

    # --- 4. Callus volume ---
    early_cm3 = float(np.sum(seg.early_callus_mask) * voxel_vol_cm3)
    hard_cm3 = float(np.sum(seg.hard_callus_mask) * voxel_vol_cm3)
    total_callus_cm3 = early_cm3 + hard_cm3

    # --- 5. Bone geometry & fragment alignment ---
    z_indices = np.where(np.any(tibia_mask, axis=(1, 2)))[0]
    bone_length_mm = float((int(z_indices[-1]) - int(z_indices[0]) + 1) * dz) if len(z_indices) else 0.0
    total_bone_cm3 = float(np.sum(tibia_mask) * voxel_vol_cm3)

    coronal_deg, sagittal_deg, frag_gap_mm, frag_disp_mm, frag_count = _compute_fragment_geometry(
        tibia_mask=tibia_mask,
        cortical_mask=cortical_mask,
        spacing_xyz=spacing,
    )

    # --- 6. Cortical continuity & 4-quadrant bridging ---
    eval_z_range = seg.fracture_z_range
    if eval_z_range is None and np.any(tibia_mask):
        z_t = np.where(np.any(tibia_mask, axis=(1, 2)))[0]
        if len(z_t) >= 10:
            mid = int((z_t[0] + z_t[-1]) // 2)
            eval_z_range = (max(int(z_t[0]), mid - 6), min(int(z_t[-1]), mid + 6))
    quad_pct, bridged_count, overall_cont = _compute_quadrant_continuity(
        cortical_mask=cortical_mask,
        callus_mask=seg.hard_callus_mask,
        tibia_mask=tibia_mask,
        fibula_mask=seg.fibula_mask,
        fracture_z_range=eval_z_range,
    )

    # --- 7. Slice-wise axial thickness profile (downsampled to ~30 points for charting) ---
    profile = _build_axial_profile(thickness_map_mm, cortical_mask, callus_mask, dz)

    metal_present = bool(np.any(metal_mask))
    metal_vol_cm3 = float(np.sum(metal_mask) * voxel_vol_cm3)
    metal_excl_voxels = int(np.sum(seg.metal_exclusion_mask))

    metrics = BoneArchitectureMetrics(
        cortical_thickness_mean_mm=round(cort_mean, 2),
        cortical_thickness_median_mm=round(cort_median, 2),
        cortical_thickness_std_mm=round(cort_std, 2),
        cortical_thickness_min_mm=round(cort_min, 2),
        cortical_thickness_p90_mm=round(cort_p90, 2),
        cortical_hu_mean=round(cort_hu_mean, 1),
        cortical_hu_median=round(cort_hu_median, 1),
        cortical_hu_iqr=round(cort_hu_iqr, 1),
        callus_hu_mean=round(callus_hu_mean, 1) if callus_hu_mean is not None else None,
        bmd_calibrated=False,
        trabecular_status=trab_status,
        trabecular_thickness_mm=round(tb_th, 3) if tb_th is not None else None,
        trabecular_separation_mm=round(tb_sp, 3) if tb_sp is not None else None,
        voxel_spacing_mm=[round(dx, 3), round(dy, 3), round(dz, 3)],
        early_callus_volume_cm3=round(early_cm3, 2),
        hard_callus_volume_cm3=round(hard_cm3, 2),
        total_callus_volume_cm3=round(total_callus_cm3, 2),
        bone_length_mm=round(bone_length_mm, 1),
        coronal_angulation_deg=round(coronal_deg, 1),
        sagittal_angulation_deg=round(sagittal_deg, 1),
        total_bone_volume_cm3=round(total_bone_cm3, 2),
        bridged_quadrants_count=bridged_count,
        quadrant_continuity_pct=quad_pct,
        overall_cortical_continuity_pct=round(overall_cont, 1),
        fracture_gap_mm=round(frag_gap_mm, 2),
        fragment_displacement_mm=round(frag_disp_mm, 2),
        fragment_count=frag_count,
        metal_present=metal_present,
        metal_volume_cm3=round(metal_vol_cm3, 2),
        metal_excluded_voxels=metal_excl_voxels,
        segmentation_method=seg.method_used,
        warnings=warnings,
        axial_thickness_profile=profile,
    )
    return metrics, thickness_map_mm


def _principal_axis_mm(mask: np.ndarray, spacing_xyz: tuple[float, float, float]) -> np.ndarray | None:
    coords = np.argwhere(mask)
    if len(coords) < 20:
        return None
    # Subsample for speed
    if len(coords) > 25000:
        step = len(coords) // 25000
        coords = coords[::step]
    dx, dy, dz = spacing_xyz
    pts = np.column_stack([coords[:, 2] * dx, coords[:, 1] * dy, coords[:, 0] * dz])
    pts -= pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts, full_matrices=False)
    axis = vt[0]
    if axis[2] < 0:
        axis = -axis
    return axis / max(np.linalg.norm(axis), 1e-8)


def _compute_fragment_geometry(
    tibia_mask: np.ndarray,
    cortical_mask: np.ndarray,
    spacing_xyz: tuple[float, float, float],
) -> tuple[float, float, float, float, int]:
    """Compute coronal/sagittal angulation, fracture gap, and displacement across fragments."""
    dx, dy, dz = spacing_xyz
    voxel_vol_mm3 = dx * dy * dz

    labeled = measure.label(tibia_mask, connectivity=2)
    props = sorted(measure.regionprops(labeled), key=lambda p: p.area, reverse=True)
    major = [p for p in props if p.area * voxel_vol_mm3 >= 2000.0]
    frag_count = max(1, len(major))

    if len(major) >= 2:
        # Compare top 2 major fragments sorted inferior-to-superior along Z
        f_inf, f_sup = sorted(major[:2], key=lambda p: p.centroid[0])
        m1 = labeled == f_inf.label
        m2 = labeled == f_sup.label
        a1 = _principal_axis_mm(m1, spacing_xyz)
        a2 = _principal_axis_mm(m2, spacing_xyz)

        if a1 is not None and a2 is not None:
            # LPS: X=coronal(L-R), Y=sagittal(P-A), Z=axial
            c_diff = abs(float(np.degrees(np.arctan2(a2[0], a2[2]) - np.arctan2(a1[0], a1[2]))))
            s_diff = abs(float(np.degrees(np.arctan2(a2[1], a2[2]) - np.arctan2(a1[1], a1[2]))))
            coronal_deg = 180.0 - c_diff if c_diff > 90.0 else c_diff
            sagittal_deg = 180.0 - s_diff if s_diff > 90.0 else s_diff
        else:
            coronal_deg = sagittal_deg = 0.0

        # Fracture gap: minimum Euclidean distance between facing cortical fragment ends (within ~3 mm of tip)
        c1 = np.argwhere(m1 & cortical_mask)
        c2 = np.argwhere(m2 & cortical_mask)
        if len(c1) > 0 and len(c2) > 0:
            z1_max = int(c1[:, 0].max())
            z2_min = int(c2[:, 0].min())
            end1 = c1[c1[:, 0] >= (z1_max - 2)]
            end2 = c2[c2[:, 0] <= (z2_min + 2)]
            p1 = np.column_stack([end1[:, 2] * dx, end1[:, 1] * dy, end1[:, 0] * dz])[:1500]
            p2 = np.column_stack([end2[:, 2] * dx, end2[:, 1] * dy, end2[:, 0] * dz])[:1500]
            dists = np.linalg.norm(p1[:, None, :] - p2[None, :, :], axis=2)
            frag_gap_mm = float(np.percentile(dists.min(axis=1), 15))
            # Transverse centroid displacement at facing ends
            xy1 = p1[:, :2].mean(axis=0)
            xy2 = p2[:, :2].mean(axis=0)
            frag_disp_mm = float(np.linalg.norm(xy1 - xy2))
        else:
            frag_gap_mm = frag_disp_mm = 0.0

        return abs(coronal_deg), abs(sagittal_deg), frag_gap_mm, frag_disp_mm, frag_count

    # Single connected component: compare proximal half vs distal half axis angulation
    z_any = np.where(np.any(tibia_mask, axis=(1, 2)))[0]
    if len(z_any) < 12:
        return 0.0, 0.0, 0.0, 0.0, frag_count
    z_mid = int((z_any[0] + z_any[-1]) // 2)
    m_low = tibia_mask.copy()
    m_low[z_mid:] = False
    m_high = tibia_mask.copy()
    m_high[:z_mid] = False
    a1 = _principal_axis_mm(m_low, spacing_xyz)
    a2 = _principal_axis_mm(m_high, spacing_xyz)
    if a1 is not None and a2 is not None:
        coronal_deg = abs(float(np.degrees(np.arctan2(a2[0], a2[2]) - np.arctan2(a1[0], a1[2]))))
        sagittal_deg = abs(float(np.degrees(np.arctan2(a2[1], a2[2]) - np.arctan2(a1[1], a1[2]))))
    else:
        coronal_deg = sagittal_deg = 0.0

    return coronal_deg, sagittal_deg, 0.0, 0.0, frag_count


def _compute_quadrant_continuity(
    cortical_mask: np.ndarray,
    callus_mask: np.ndarray,
    tibia_mask: np.ndarray,
    fibula_mask: np.ndarray,
    fracture_z_range: tuple[int, int] | None,
) -> tuple[dict[str, float], int, float]:
    """Assess Anterior/Posterior/Medial/Lateral cortical bridging across the fracture Z-band."""
    default_quads = {"anterior": 0.0, "posterior": 0.0, "medial": 0.0, "lateral": 0.0}
    if fracture_z_range is None or not np.any(tibia_mask):
        return default_quads, 0, 0.0

    bridged_bone = cortical_mask | callus_mask
    z0, z1 = fracture_z_range
    z0 = max(0, z0)
    z1 = min(bridged_bone.shape[0] - 1, z1)
    if z1 <= z0:
        return default_quads, 0, 0.0

    # Focus on the inner central core of the fracture band so intact margin slices don't inflate bridging
    span = z1 - z0
    if span >= 8:
        inner_pad = max(1, int(span * 0.32))
        z0 = z0 + inner_pad
        z1 = z1 - inner_pad
    if z1 < z0:
        z1 = z0

    # Isolate the primary tibial shaft cluster (prevents bilateral leg midpoints falling in empty space)
    labeled_tib = measure.label(tibia_mask, connectivity=2)
    props_tib = sorted(measure.regionprops(labeled_tib), key=lambda p: p.area, reverse=True)
    primary_tib = labeled_tib == props_tib[0].label
    tib_coords = np.argwhere(primary_tib)
    global_cy = float(np.mean(tib_coords[:, 1]))
    global_cx = float(np.mean(tib_coords[:, 2]))

    # Determine anatomical lateral direction from fibula centroid relative to tibia (fibula is always lateral)
    lateral_is_pos_x = False
    if np.any(fibula_mask):
        fib_coords = np.argwhere(fibula_mask)
        # Pick fibula points nearest to primary tibia in XY
        fib_x = float(np.median(fib_coords[:, 2]))
        lateral_is_pos_x = fib_x > global_cx

    # Fit centerline (cy(z), cx(z)) from intact tibia slices outside the fracture band
    # so a missing cortex on a fracture slice never pulls the origin into the intact side.
    z_all = np.where(np.any(primary_tib, axis=(1, 2)))[0]
    intact_zs: list[int] = []
    intact_cys: list[float] = []
    intact_cxs: list[float] = []
    for z_i in z_all:
        if z0 <= int(z_i) <= z1:
            continue
        pts_i = np.argwhere(primary_tib[int(z_i)])
        if len(pts_i) > 0:
            intact_zs.append(int(z_i))
            intact_cys.append(float(np.mean(pts_i[:, 0])))
            intact_cxs.append(float(np.mean(pts_i[:, 1])))

    quad_slices: dict[str, list[bool]] = {
        "anterior": [],
        "posterior": [],
        "medial": [],
        "lateral": [],
    }

    for z in range(z0, z1 + 1):
        sl = bridged_bone[z]
        if not np.any(sl):
            for k in quad_slices:
                quad_slices[k].append(False)
            continue
        pts = np.argwhere(sl)  # (y, x)
        if len(intact_zs) >= 2:
            cy = float(np.interp(z, intact_zs, intact_cys))
            cx = float(np.interp(z, intact_zs, intact_cxs))
        else:
            cy, cx = global_cy, global_cx

        dy_pts = pts[:, 0] - cy
        dx_pts = pts[:, 1] - cx
        angles = np.degrees(np.arctan2(dy_pts, dx_pts))  # -180..180
        # LPS convention: -Y = Anterior (-90 deg), +Y = Posterior (+90 deg)
        quad_slices["anterior"].append(bool(np.any((angles >= -135) & (angles < -45))))
        quad_slices["posterior"].append(bool(np.any((angles >= 45) & (angles < 135))))
        pos_x_hit = bool(np.any((angles >= -45) & (angles < 45)))
        neg_x_hit = bool(np.any((angles >= 135) | (angles < -135)))
        if lateral_is_pos_x:
            quad_slices["lateral"].append(pos_x_hit)
            quad_slices["medial"].append(neg_x_hit)
        else:
            quad_slices["medial"].append(pos_x_hit)
            quad_slices["lateral"].append(neg_x_hit)

    quad_pct = {
        k: round(100.0 * sum(v) / max(len(v), 1), 1) for k, v in quad_slices.items()
    }
    bridged_count = sum(1 for pct in quad_pct.values() if pct >= 75.0)
    overall = sum(quad_pct.values()) / 4.0
    return quad_pct, bridged_count, overall


def _build_axial_profile(
    thickness_map_mm: np.ndarray,
    cortical_mask: np.ndarray,
    callus_mask: np.ndarray,
    dz: float,
    bins: int = 28,
) -> list[dict[str, float]]:
    z_any = np.where(np.any(cortical_mask | callus_mask, axis=(1, 2)))[0]
    if len(z_any) == 0:
        return []
    z_min, z_max = int(z_any[0]), int(z_any[-1])
    edges = np.linspace(z_min, z_max + 1, bins + 1, dtype=int)
    profile: list[dict[str, float]] = []
    for i in range(bins):
        a, b = int(edges[i]), int(edges[i + 1])
        if b <= a:
            continue
        sub_cort = cortical_mask[a:b]
        sub_thick = thickness_map_mm[a:b][sub_cort]
        mean_th = float(np.mean(sub_thick)) if len(sub_thick) > 0 else 0.0
        callus_vox = int(np.sum(callus_mask[a:b]))
        profile.append(
            {
                "position_mm": round(((a + b) / 2.0 - z_min) * dz, 1),
                "mean_thickness_mm": round(mean_th, 2),
                "callus_voxels": float(callus_vox),
            }
        )
    return profile
