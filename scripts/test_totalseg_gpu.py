"""Verify TotalSegmentator appendicular_bones GPU execution on RTX 4050."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import torch

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.imaging.loader import load_ct_volume  # noqa: E402
from app.imaging.segmentor import segment_tibia_ct  # noqa: E402
from app.quantification.architecture import quantify_bone_architecture  # noqa: E402


def main() -> None:
    t0 = time.time()
    out_dir = Path(__file__).resolve().parents[1] / "data" / "test_totalseg"
    ct_path = Path(__file__).resolve().parents[1] / "data" / "samples" / "VSD_z025_real_lower_legs_ct.nii.gz"
    vol = load_ct_volume(ct_path, out_dir)
    seg = segment_tibia_ct(vol, out_dir, backend="totalsegmentator", is_intact_reference=True)
    m, _ = quantify_bone_architecture(vol, seg)
    print(f"Elapsed: {time.time() - t0:.1f}s | Method: {seg.method_used} | Warnings: {seg.warnings}")
    print(
        "TotalSeg Metrics:",
        {
            k: getattr(m, k)
            for k in [
                "cortical_thickness_mean_mm",
                "cortical_hu_mean",
                "bone_length_mm",
                "total_bone_volume_cm3",
                "bridged_quadrants_count",
            ]
        },
    )
    if torch.cuda.is_available():
        print("Peak VRAM MB:", round(torch.cuda.max_memory_allocated() / 1048576, 1))


if __name__ == "__main__":
    main()
