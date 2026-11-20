from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import SimpleITK as sitk


@dataclass
class LongitudinalCTDelta:
    """Registered baseline vs follow-up CT bone remodelling comparison."""

    registration_converged: bool
    dice_bone_overlap: float
    callus_volume_baseline_cm3: float
    callus_volume_followup_cm3: float
    callus_volume_change_pct: float | None
    cortical_thickness_baseline_mm: float
    cortical_thickness_followup_mm: float
    cortical_thickness_change_pct: float | None
    fracture_gap_baseline_mm: float
    fracture_gap_followup_mm: float
    fracture_gap_change_pct: float | None
    bridged_quadrants_baseline: int
    bridged_quadrants_followup: int
    bridged_quadrants_delta: int
    cortical_hu_baseline: float
    cortical_hu_followup: float
    cortical_hu_delta: float
    modality_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def register_ct_masks_rigid(
    fixed_mask_img: sitk.Image,
    moving_mask_img: sitk.Image,
) -> tuple[sitk.Image, float]:
    """Rigidly register follow-up tibial mask onto baseline CT space and return Dice overlap."""
    fixed_f = sitk.Cast(fixed_mask_img > 0, sitk.sitkFloat32)
    moving_f = sitk.Cast(moving_mask_img > 0, sitk.sitkFloat32)

    initial_tx = sitk.CenteredTransformInitializer(
        fixed_f,
        moving_f,
        sitk.Euler3DTransform(),
        sitk.CenteredTransformInitializerFilter.GEOMETRY,
    )

    reg = sitk.ImageRegistrationMethod()
    reg.SetMetricAsMeanSquares()
    reg.SetMetricSamplingStrategy(reg.RANDOM)
    reg.SetMetricSamplingPercentage(0.15)
    reg.SetInterpolator(sitk.sitkLinear)
    reg.SetOptimizerAsRegularStepGradientDescent(
        learningRate=1.5,
        minStep=0.01,
        numberOfIterations=120,
        relaxationFactor=0.5,
    )
    reg.SetOptimizerScalesFromPhysicalShift()
    reg.SetInitialTransform(initial_tx, inPlace=False)
    reg.SetShrinkFactorsPerLevel([4, 2, 1])
    reg.SetSmoothingSigmasPerLevel([2, 1, 0])

    final_tx = reg.Execute(fixed_f, moving_f)
    resampled = sitk.Resample(
        moving_mask_img,
        fixed_mask_img,
        final_tx,
        sitk.sitkNearestNeighbor,
        0,
        moving_mask_img.GetPixelID(),
    )

    f_arr = sitk.GetArrayFromImage(fixed_mask_img) > 0
    m_arr = sitk.GetArrayFromImage(resampled) > 0
    inter = float(np.sum(f_arr & m_arr))
    denom = float(np.sum(f_arr) + np.sum(m_arr))
    dice = (2.0 * inter / denom) if denom > 0 else 0.0
    return resampled, round(dice, 3)


def compute_longitudinal_ct_delta(
    baseline_metrics: dict[str, Any],
    followup_metrics: dict[str, Any],
    dice_overlap: float = 0.0,
    registration_converged: bool = True,
) -> LongitudinalCTDelta:
    """Compute structured longitudinal remodelling deltas between two CT reports."""

    def pct_delta(old: float, new: float) -> float | None:
        if abs(old) < 1e-6:
            return None
        return round(((new - old) / abs(old)) * 100.0, 1)

    c0 = float(baseline_metrics.get("total_callus_volume_cm3") or 0.0)
    c1 = float(followup_metrics.get("total_callus_volume_cm3") or 0.0)
    t0 = float(baseline_metrics.get("cortical_thickness_mean_mm") or 0.0)
    t1 = float(followup_metrics.get("cortical_thickness_mean_mm") or 0.0)
    g0 = float(baseline_metrics.get("fracture_gap_mm") or 0.0)
    g1 = float(followup_metrics.get("fracture_gap_mm") or 0.0)
    q0 = int(baseline_metrics.get("bridged_quadrants_count") or 0)
    q1 = int(followup_metrics.get("bridged_quadrants_count") or 0)
    h0 = float(baseline_metrics.get("cortical_hu_mean") or 0.0)
    h1 = float(followup_metrics.get("cortical_hu_mean") or 0.0)

    return LongitudinalCTDelta(
        registration_converged=registration_converged,
        dice_bone_overlap=dice_overlap,
        callus_volume_baseline_cm3=round(c0, 2),
        callus_volume_followup_cm3=round(c1, 2),
        callus_volume_change_pct=pct_delta(c0, c1),
        cortical_thickness_baseline_mm=round(t0, 2),
        cortical_thickness_followup_mm=round(t1, 2),
        cortical_thickness_change_pct=pct_delta(t0, t1),
        fracture_gap_baseline_mm=round(g0, 2),
        fracture_gap_followup_mm=round(g1, 2),
        fracture_gap_change_pct=pct_delta(g0, g1),
        bridged_quadrants_baseline=q0,
        bridged_quadrants_followup=q1,
        bridged_quadrants_delta=q1 - q0,
        cortical_hu_baseline=round(h0, 1),
        cortical_hu_followup=round(h1, 1),
        cortical_hu_delta=round(h1 - h0, 1),
    )
