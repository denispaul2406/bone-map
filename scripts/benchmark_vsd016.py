"""Benchmark Fast HU Engine vs TotalSegmentator AI against published VSD 016 ground-truth masks."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import SimpleITK as sitk

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.imaging.loader import load_ct_volume  # noqa: E402
from app.imaging.segmentor import segment_tibia_ct  # noqa: E402
from app.quantification.architecture import quantify_bone_architecture  # noqa: E402


def dice(a: np.ndarray, b: np.ndarray) -> float:
    denom = int(a.sum()) + int(b.sum())
    return round((2.0 * int(np.sum(a & b)) / denom), 4) if denom > 0 else 0.0


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    base = root / "data" / "samples" / "vsd_gt_seg" / "extracted_481" / "016" / "SMIR.Lower_limb.095Y.F.CT.481"
    ct_img = sitk.DICOMOrient(sitk.ReadImage(str(base / "SMIR.Lower_limb.095Y.F.CT.481.nrrd")), "LPS")
    seg_img = sitk.DICOMOrient(
        sitk.ReadImage(str(base / "SMIR.Lower_limb.095Y.F.CT.481-Shanks-Feet_Segmentation.seg.nrrd")), "LPS"
    )

    ct_arr = sitk.GetArrayFromImage(ct_img)
    seg_arr = sitk.GetArrayFromImage(seg_img)

    rt_mask = (seg_arr == 2) | (seg_arr == 3)
    zs, ys, xs = np.where(rt_mask)
    z0, z1 = max(0, int(zs.min()) - 10), min(ct_arr.shape[0], int(zs.max()) + 10)
    y0, y1 = max(0, int(ys.min()) - 25), min(ct_arr.shape[1], int(ys.max()) + 25)
    x0, x1 = max(0, int(xs.min()) - 25), min(ct_arr.shape[2], int(xs.max()) + 25)

    crop_ct = sitk.GetImageFromArray(ct_arr[z0:z1, y0:y1, x0:x1].astype(np.float32))
    crop_ct.SetSpacing(ct_img.GetSpacing())
    crop_gt = sitk.GetImageFromArray(seg_arr[z0:z1, y0:y1, x0:x1].astype(np.uint8))
    crop_gt.SetSpacing(ct_img.GetSpacing())

    sample_ct = root / "data" / "samples" / "VSD_016_right_tibia_ct.nii.gz"
    sitk.WriteImage(crop_ct, str(sample_ct))
    gt_arr = sitk.GetArrayFromImage(crop_gt)
    gt_tibia = gt_arr == 2
    gt_fibula = gt_arr == 3

    gt_bm = np.zeros_like(gt_arr, dtype=np.uint8)
    gt_bm[gt_tibia] = 1
    gt_bm[gt_fibula] = 4
    gt_bm_path = root / "data" / "test_vsd016_gt" / "gt_labels.nii.gz"
    gt_bm_path.parent.mkdir(parents=True, exist_ok=True)
    gt_bm_img = sitk.GetImageFromArray(gt_bm)
    gt_bm_img.CopyInformation(crop_ct)
    sitk.WriteImage(gt_bm_img, str(gt_bm_path))

    vol = load_ct_volume(sample_ct, root / "data" / "test_vsd016_gt")
    seg_gt = segment_tibia_ct(vol, root / "data" / "test_vsd016_gt", manual_mask_path=gt_bm_path, is_intact_reference=True)
    m_gt, _ = quantify_bone_architecture(vol, seg_gt)

    t1 = time.time()
    seg_hu = segment_tibia_ct(vol, root / "data" / "test_vsd016_hu", backend="auto_lower_limb", is_intact_reference=True)
    m_hu, _ = quantify_bone_architecture(vol, seg_hu)
    dt_hu = time.time() - t1

    t2 = time.time()
    seg_ts = segment_tibia_ct(vol, root / "data" / "test_vsd016_ts", backend="totalsegmentator", is_intact_reference=True)
    m_ts, _ = quantify_bone_architecture(vol, seg_ts)
    dt_ts = time.time() - t2

    print("=== REAL PUBLISHED GROUND TRUTH BENCHMARK (VSD 016 Right Tibia/Fibula, 0.75x0.75x0.6 mm) ===")
    print(f"GT Reference  : CorticalThick={m_gt.cortical_thickness_mean_mm}mm, Vol={m_gt.total_bone_volume_cm3}cm3, Len={m_gt.bone_length_mm}mm")
    print(f"HU Engine     : Tibia Dice={dice(seg_hu.tibia_mask, gt_tibia)}, Fibula Dice={dice(seg_hu.fibula_mask, gt_fibula)}, CorticalThick={m_hu.cortical_thickness_mean_mm}mm, Vol={m_hu.total_bone_volume_cm3}cm3, Time={dt_hu:.1f}s")
    print(f"TotalSeg AI   : Tibia Dice={dice(seg_ts.tibia_mask, gt_tibia)}, Fibula Dice={dice(seg_ts.fibula_mask, gt_fibula)}, CorticalThick={m_ts.cortical_thickness_mean_mm}mm, Vol={m_ts.total_bone_volume_cm3}cm3, Time={dt_ts:.1f}s, Method={seg_ts.method_used}")


if __name__ == "__main__":
    main()
