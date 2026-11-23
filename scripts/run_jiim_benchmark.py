"""Q1 JIIM multi-subject benchmark runner with HD95, ASSD, Bland-Altman cortical stats, and streaming zip cleanup."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

import httpx
import numpy as np
import scipy.io
import SimpleITK as sitk
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.imaging.loader import load_ct_volume  # noqa: E402
from app.imaging.segmentor import _needs_resample, segment_tibia_ct  # noqa: E402
from app.quantification.architecture import quantify_bone_architecture  # noqa: E402
from app.real_datasets import _read_platif_metadata  # noqa: E402

SAMPLES_DIR = ROOT / "data" / "samples"
OUT_DIR = ROOT / "paper" / "jiim"

# Note: Zenodo 8302449 archives already contain BOTH Shanks-Feet CT (.nrrd) AND Slicer GT (.seg.nrrd),
# cutting download bandwidth by ~60% vs downloading DICOMs from 8270365.
EXCLUDED_SUBJECTS = {"Phantom001.zip"}


def _parse_slicer_label_map(seg_img: sitk.Image) -> dict[str, tuple[int, int]]:
    """Map Slicer segment names (e.g. Tibia_R, Fibula_R) -> (layer, label_value)."""
    by_idx: dict[str, dict[str, str]] = {}
    for k in seg_img.GetMetaDataKeys():
        if k.startswith("Segment") and "_" in k:
            seg_idx, prop = k.split("_", 1)
            by_idx.setdefault(seg_idx, {})[prop] = seg_img.GetMetaData(k).strip()
    out: dict[str, tuple[int, int]] = {}
    for props in by_idx.values():
        name = props.get("Name")
        if name and "LabelValue" in props:
            out[name] = (int(props.get("Layer", "0")), int(props["LabelValue"]))
    return out


def _extract_layer_mask(seg_arr: np.ndarray, layer: int, label_val: int) -> np.ndarray:
    if seg_arr.ndim == 4:
        # SimpleITK 4D vector/component seg.nrrd puts vector components along axis -1 or 0
        if seg_arr.shape[-1] <= 8:
            return seg_arr[..., layer] == label_val
        return seg_arr[layer] == label_val
    return seg_arr == label_val


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    denom = int(a.sum()) + int(b.sum())
    return round((2.0 * int(np.sum(a & b)) / denom), 4) if denom > 0 else 0.0


def _surface_distances_mm(pred: np.ndarray, gt: np.ndarray, spacing_xyz: tuple[float, float, float]) -> dict[str, float]:
    """Compute HD95 and ASSD in mm using morphological surface boundaries + anisotropic EDT."""
    if not np.any(pred) or not np.any(gt):
        return {"hd95_mm": float("nan"), "assd_mm": float("nan")}
    dx, dy, dz = spacing_xyz
    struct = ndimage.generate_binary_structure(3, 1)
    surf_p = pred ^ ndimage.binary_erosion(pred, structure=struct, border_value=0)
    surf_g = gt ^ ndimage.binary_erosion(gt, structure=struct, border_value=0)
    edt_to_g = ndimage.distance_transform_edt(~surf_g, sampling=(dz, dy, dx))
    edt_to_p = ndimage.distance_transform_edt(~surf_p, sampling=(dz, dy, dx))
    d_p2g = edt_to_g[surf_p]
    d_g2p = edt_to_p[surf_g]
    all_d = np.concatenate([d_p2g, d_g2p])
    return {
        "hd95_mm": round(float(np.percentile(all_d, 95)), 2),
        "assd_mm": round(float(np.mean(all_d)), 2),
    }


def _download_file(url: str, dest: Path, expected_size: int | None = None) -> None:
    """Resumable HTTP Range downloader with retries and atomic .part -> dest rename."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest.with_suffix(dest.suffix + ".part")
    if dest.exists():
        if expected_size is not None and dest.stat().st_size < expected_size and not part_path.exists():
            dest.replace(part_path)
        elif expected_size is None or dest.stat().st_size == expected_size:
            return

    for attempt in range(1, 10):
        offset = part_path.stat().st_size if part_path.exists() else 0
        if expected_size is not None and offset == expected_size:
            part_path.replace(dest)
            return
        headers = {"Range": f"bytes={offset}-"} if offset > 0 else {}
        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, read=120.0), follow_redirects=True) as client:
                with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 416 and expected_size is not None and offset == expected_size:
                        part_path.replace(dest)
                        return
                    resp.raise_for_status()
                    mode = "ab" if resp.status_code == 206 and offset > 0 else "wb"
                    with part_path.open(mode) as f:
                        for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
            if expected_size is None or part_path.stat().st_size == expected_size:
                part_path.replace(dest)
                return
        except (httpx.HTTPError, OSError) as exc:
            print(f"[RETRY {attempt}/9] Download interrupted ({exc}); resuming...")
            time.sleep(min(15, 2 * attempt))
    raise RuntimeError(f"Failed to complete download after retries: {dest}")


def evaluate_platif_all(download_missing: bool) -> dict:
    platif_dir = SAMPLES_DIR / "platif"
    platif_dir.mkdir(parents=True, exist_ok=True)
    rec_files = {f["key"]: f for f in httpx.get("https://zenodo.org/api/records/18007397", timeout=30).json()["files"]}

    xlsx_path = platif_dir / "Tibial Plateau Fracture Metadata.xlsx"
    if not xlsx_path.exists() and "Tibial Plateau Fracture Metadata.xlsx" in rec_files:
        _download_file(rec_files["Tibial Plateau Fracture Metadata.xlsx"]["links"]["self"], xlsx_path)

    part_zips = [f"Patient Data_Part {i}.zip" for i in range(1, 6)]
    if download_missing:
        for name in part_zips:
            zp = platif_dir / name
            info = rec_files.get(name)
            if info and (not zp.exists() or zp.stat().st_size != info["size"]):
                print(f"[DL] PlaTiF {name} ({info['size']/1048576:.1f} MB)...")
                _download_file(info["links"]["self"], zp, expected_size=info["size"])

    meta = _read_platif_metadata()
    rows = []
    extract_dir = platif_dir / "extracted_all"
    extract_dir.mkdir(parents=True, exist_ok=True)

    for name in part_zips:
        zp = platif_dir / name
        if not zp.exists():
            continue
        with zipfile.ZipFile(zp) as z:
            mats = sorted([m for m in z.namelist() if m.endswith(".mat")])
            for m in mats:
                pid = Path(m).stem.replace("Patient_ID_", "")
                try:
                    out_m = extract_dir / Path(m).name
                    if not out_m.exists():
                        out_m.write_bytes(z.read(m))
                    mat = scipy.io.loadmat(out_m)
                    rec_key = f"Patient_ID_{pid}" if f"Patient_ID_{pid}" in mat else [k for k in mat if not k.startswith("__")][0]
                    rec = mat[rec_key][0, 0]
                    fields = rec.dtype.names or ()
                    im0 = rec["im0"][0, 0]
                    orig = im0["OriginalImage"].astype(np.float32)
                    bw = im0["BW"] > 0
                    has_ct = "Coronal_CT" in fields
                    ct2d = rec["Coronal_CT"].astype(np.float32) if has_ct else None
                    num_views = sum(1 for f in fields if f.startswith("im"))

                    ys, xs = np.where(bw)
                    mask_h_px = int(ys.max() - ys.min() + 1) if len(ys) else 0
                    mask_w_px = int(xs.max() - xs.min() + 1) if len(xs) else 0
                    pmeta = meta.get(pid, {})
                    age_s = pmeta.get("Age", "").strip()
                    rows.append(
                        {
                            "patient_id": f"PLATIF-{pid}",
                            "part": name,
                            "age": int(age_s) if age_s.isdigit() else None,
                            "gender": pmeta.get("Gender", "").strip(),
                            "side": pmeta.get("Fracture of the Right (R) or Left (L) Tibia", "").strip(),
                            "schatzker": pmeta.get("Fracture Type of  Schatzker Classification", "").strip(),
                            "num_xray_views": num_views,
                            "has_coronal_ct": has_ct,
                            "tibia_mask_pct": round(float(bw.mean() * 100.0), 2),
                            "mask_bbox_h_px": mask_h_px,
                            "mask_bbox_w_px": mask_w_px,
                            "xray_mean_norm": round(float(orig.mean()), 4),
                            "coronal_ct_mean": round(float(ct2d.mean()), 2) if ct2d is not None else None,
                        }
                    )
                except Exception as exc:
                    print(f"[SKIP] PlaTiF {pid} ({name}): {exc}")
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "platif_full_cohort.csv"
    if rows:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    ages = [r["age"] for r in rows if r["age"] is not None]
    return {
        "n_patients": len(rows),
        "n_with_coronal_ct": sum(1 for r in rows if r["has_coronal_ct"]),
        "age_mean": round(float(np.mean(ages)), 1) if ages else None,
        "age_std": round(float(np.std(ages)), 1) if ages else None,
        "schatzker_counts": dict(sorted(Counter(r["schatzker"] for r in rows).items())),
        "gender_counts": dict(Counter(r["gender"] for r in rows)),
    }


def evaluate_vsd_subject(subj_zip_name: str, rec_files: dict, download_missing: bool, cleanup_zip: bool) -> list[dict]:
    """Evaluate Right and/or Left tibia/fibula in one VSDFullBody subject zip from Zenodo 8302449."""
    vsd_dir = SAMPLES_DIR / "vsd_gt_seg"
    zp = vsd_dir / subj_zip_name
    if not zp.exists() or zp.stat().st_size != rec_files[subj_zip_name]["size"]:
        if not download_missing:
            return []
        info = rec_files[subj_zip_name]
        print(f"[DL] VSD {subj_zip_name} ({info['size']/1048576:.1f} MB)...")
        _download_file(info["links"]["self"], zp, expected_size=info["size"])

    subj_id = Path(subj_zip_name).stem
    work_root = ROOT / "data" / "paper_bench_work" / f"jiim_{subj_id}"
    work_root.mkdir(parents=True, exist_ok=True)
    extract_dir = work_root / "unzipped"

    rows: list[dict] = []
    try:
        with zipfile.ZipFile(zp) as z:
            shanks_segs = [m for m in z.namelist() if m.endswith("Shanks-Feet_Segmentation.seg.nrrd")]
            if not shanks_segs:
                print(f"[SKIP] {subj_id}: no Shanks-Feet_Segmentation.seg.nrrd in zip")
                return []
            target_dir_prefix = shanks_segs[0].rsplit("/", 1)[0] + "/"
            members = [
                m for m in z.namelist()
                if m.startswith(target_dir_prefix) and m.endswith(".nrrd") and "Reconstruction" not in m
            ]
            for m in members:
                z.extract(m, extract_dir)

        seg_files = list(extract_dir.rglob("*-Shanks-Feet_Segmentation.seg.nrrd"))
        if not seg_files:
            print(f"[SKIP] {subj_id}: no Shanks-Feet_Segmentation.seg.nrrd found")
            return []
        seg_path = seg_files[0]
        ct_candidates = [p for p in seg_path.parent.glob("*.nrrd") if "Segmentation" not in p.name and "Reconstruction" not in p.name]
        if not ct_candidates:
            print(f"[SKIP] {subj_id}: no matching Shanks-Feet CT .nrrd found")
            return []
        ct_path = ct_candidates[0]

        seg_raw = sitk.ReadImage(str(seg_path))
        seg_map = _parse_slicer_label_map(seg_raw)
        ct_img = sitk.DICOMOrient(sitk.ReadImage(str(ct_path)), "LPS")
        seg_img = sitk.DICOMOrient(seg_raw, "LPS")
        if _needs_resample(seg_img, ct_img):
            seg_img = sitk.Resample(
                seg_img,
                ct_img,
                sitk.Transform(),
                sitk.sitkNearestNeighbor,
                0,
                seg_img.GetPixelID(),
            )
        ct_arr = sitk.GetArrayFromImage(ct_img)
        seg_arr = sitk.GetArrayFromImage(seg_img)

        for side in ("R", "L"):
            tib_key, fib_key = f"Tibia_{side}", f"Fibula_{side}"
            if tib_key not in seg_map:
                continue
            gt_tib_full = _extract_layer_mask(seg_arr, *seg_map[tib_key])
            gt_fib_full = _extract_layer_mask(seg_arr, *seg_map[fib_key]) if fib_key in seg_map else np.zeros_like(gt_tib_full)
            rt_mask = gt_tib_full | gt_fib_full
            if int(rt_mask.sum()) < 5000:
                continue

            zs, ys, xs = np.where(rt_mask)
            z0, z1 = max(0, int(zs.min()) - 10), min(ct_arr.shape[0], int(zs.max()) + 10)
            y0, y1 = max(0, int(ys.min()) - 25), min(ct_arr.shape[1], int(ys.max()) + 25)
            x0, x1 = max(0, int(xs.min()) - 25), min(ct_arr.shape[2], int(xs.max()) + 25)

            side_dir = work_root / f"side_{side}"
            side_dir.mkdir(parents=True, exist_ok=True)
            crop_ct = sitk.GetImageFromArray(ct_arr[z0:z1, y0:y1, x0:x1].astype(np.float32))
            crop_ct.SetSpacing(ct_img.GetSpacing())
            crop_ct_path = side_dir / "crop_ct.nii.gz"
            sitk.WriteImage(crop_ct, str(crop_ct_path))

            gt_tibia_shell = gt_tib_full[z0:z1, y0:y1, x0:x1]
            gt_fib_shell = gt_fib_full[z0:z1, y0:y1, x0:x1]
            gt_tibia_fill = np.array([ndimage.binary_fill_holes(gt_tibia_shell[z]) for z in range(gt_tibia_shell.shape[0])])
            gt_fib_fill = np.array([ndimage.binary_fill_holes(gt_fib_shell[z]) for z in range(gt_fib_shell.shape[0])])

            gt_bm = np.zeros_like(gt_tibia_shell, dtype=np.uint8)
            gt_bm[gt_tibia_shell] = 1
            gt_bm[gt_fib_shell] = 4
            gt_bm_path = side_dir / "gt_labels.nii.gz"
            gt_bm_img = sitk.GetImageFromArray(gt_bm)
            gt_bm_img.CopyInformation(crop_ct)
            sitk.WriteImage(gt_bm_img, str(gt_bm_path))

            vol = load_ct_volume(crop_ct_path, side_dir)
            seg_gt = segment_tibia_ct(vol, side_dir / "gt", manual_mask_path=gt_bm_path, is_intact_reference=True)
            m_gt, _ = quantify_bone_architecture(vol, seg_gt)

            t1 = time.perf_counter()
            seg_hu = segment_tibia_ct(vol, side_dir / "hu", backend="auto_lower_limb", is_intact_reference=True)
            m_hu, _ = quantify_bone_architecture(vol, seg_hu)
            dt_hu = time.perf_counter() - t1

            t2 = time.perf_counter()
            seg_ts = segment_tibia_ct(vol, side_dir / "ts", backend="totalsegmentator", is_intact_reference=True)
            m_ts, _ = quantify_bone_architecture(vol, seg_ts)
            dt_ts = time.perf_counter() - t2

            ts_surf = _surface_distances_mm(seg_ts.tibia_mask, gt_tibia_fill, vol.spacing_xyz)
            hu_surf = _surface_distances_mm(seg_hu.tibia_mask, gt_tibia_fill, vol.spacing_xyz)

            rows.append(
                {
                    "subject_id": f"{subj_id}_{side}",
                    "spacing_xyz": [round(s, 3) for s in vol.spacing_xyz],
                    "gt_cortical_mean_mm": m_gt.cortical_thickness_mean_mm,
                    "ts_cortical_mean_mm": m_ts.cortical_thickness_mean_mm,
                    "hu_cortical_mean_mm": m_hu.cortical_thickness_mean_mm,
                    "ts_tibia_dice": _dice(seg_ts.tibia_mask, gt_tibia_fill),
                    "ts_fibula_dice": _dice(seg_ts.fibula_mask, gt_fib_fill),
                    "ts_hd95_mm": ts_surf["hd95_mm"],
                    "ts_assd_mm": ts_surf["assd_mm"],
                    "hu_tibia_dice": _dice(seg_hu.tibia_mask, gt_tibia_fill),
                    "hu_hd95_mm": hu_surf["hd95_mm"],
                    "ts_runtime_s": round(dt_ts, 2),
                    "hu_runtime_s": round(dt_hu, 2),
                }
            )
    except Exception as exc:
        print(f"[SKIP] VSD {subj_id}: {exc}")
    finally:
        shutil.rmtree(work_root, ignore_errors=True)
        if cleanup_zip and subj_zip_name != "016.zip" and zp.exists():
            zp.unlink()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-platif", action="store_true", help="Download all 5 PlaTiF zips (~4.7 GB total)")
    parser.add_argument("--vsd-count", type=int, default=1, help="Number of VSD GT zips from Zenodo 8302449 to evaluate (1..30)")
    parser.add_argument("--vsd-only", nargs="+", default=None, help="Explicit VSD zip filenames to run and merge atop existing status")
    parser.add_argument("--download-vsd", action="store_true", help="Download missing VSD GT+CT zips one-by-one")
    parser.add_argument("--cleanup-vsd-zips", action="store_true", help="Delete downloaded VSD zips (except 016) after evaluation")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    status_path = OUT_DIR / "jiim_cohort_status.json"
    if args.vsd_only and status_path.exists():
        prev = json.loads(status_path.read_text(encoding="utf-8"))
        platif_summary = prev["platif"]
    else:
        platif_summary = evaluate_platif_all(download_missing=args.download_platif)

    existing_rows: list[dict] = []
    clean_csv = OUT_DIR / "vsd_clean_10limbs.csv"
    if args.vsd_only and clean_csv.exists():
        with clean_csv.open("r", encoding="utf-8") as f:
            existing_rows = list(csv.DictReader(f))

    rec_files = {f["key"]: f for f in httpx.get("https://zenodo.org/api/records/8302449", timeout=30).json()["files"]}
    if args.vsd_only:
        selected = args.vsd_only
    else:
        candidates = ["016.zip"] + [
            f["key"]
            for f in sorted(rec_files.values(), key=lambda x: x["size"])
            if f["key"].endswith(".zip") and f["key"] not in EXCLUDED_SUBJECTS and f["key"] != "016.zip"
        ]
        selected = candidates[: max(1, args.vsd_count)]

    by_id = {r["subject_id"]: r for r in existing_rows}
    for idx, zname in enumerate(selected, start=1):
        print(f"[{idx}/{len(selected)}] Processing VSD subject {zname}...")
        new_rows = evaluate_vsd_subject(zname, rec_files, download_missing=args.download_vsd, cleanup_zip=args.cleanup_vsd_zips)
        for r in new_rows:
            by_id[r["subject_id"]] = r
        merged = list(by_id.values())
        if merged:
            csv_p = OUT_DIR / "vsd_multi_subject.csv"
            with csv_p.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(merged[0].keys()))
                w.writeheader()
                w.writerows(merged)
        summary = {"platif": platif_summary, "vsd_limbs_evaluated": len(merged), "vsd_rows": merged}
        status_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Done: PlaTiF N={platif_summary['n_patients']}, VSD limbs={len(by_id)}")


if __name__ == "__main__":
    main()
