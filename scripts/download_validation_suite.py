"""Download public ground-truth bone & trauma CT datasets for ECC validation."""

from __future__ import annotations

from pathlib import Path
import httpx

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"

TARGETS = [
    ("pengwin", "19734383", ["PENGWIN26_task3_clinical_fractures_train.zip"]),
    ("ormir_aim", "21284559", ["CHAR_NOCMP_020.AIM", "CHAR_NOCMP_030.AIM"]),
    ("vsd_gt_ct", "8270365", ["016.zip"]),
    ("vsd_gt_seg", "8302449", ["016.zip"]),
]


def download_record_files(subdir: str, record_id: str, wanted: list[str]) -> None:
    r = httpx.get(f"https://zenodo.org/api/records/{record_id}", timeout=30.0, follow_redirects=True)
    r.raise_for_status()
    files = {f["key"]: f for f in r.json().get("files", [])}
    for name in wanted:
        f = files.get(name)
        if not f:
            print(f"[SKIP] {name} not found in Zenodo {record_id}")
            continue
        dest = SAMPLES_DIR / subdir / name
        size = f.get("size", 0)
        if dest.exists() and dest.stat().st_size == size:
            print(f"[OK] Already exists: {dest}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"[DL] {subdir}/{name} ({size / 1048576:.1f} MB)...")
        with httpx.Client(timeout=900.0, follow_redirects=True) as client:
            with client.stream("GET", f["links"]["self"]) as resp:
                resp.raise_for_status()
                with dest.open("wb") as out:
                    for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                        out.write(chunk)
        print(f"[DONE] {dest}")


def main() -> None:
    for subdir, rec_id, wanted in TARGETS:
        download_record_files(subdir, rec_id, wanted)


if __name__ == "__main__":
    main()
