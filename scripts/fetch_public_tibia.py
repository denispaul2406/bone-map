"""Download public tibia CT / fracture datasets from Zenodo into data/samples/."""

from __future__ import annotations

import argparse
from pathlib import Path
import httpx

DATA_SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"

RECORDS = {
    "platif": {
        "record_id": "18007397",
        "description": "PlaTiF: Tibial Plateau Fracture CT + Radiograph + Segmentation Dataset (CC BY 4.0)",
    },
    "vsdfullbody": {
        "record_id": "8270365",
        "description": "VSDFullBody: Virtual Skeleton Database Full Body Human CT Collection",
    },
}


def inspect_zenodo_record(record_id: str) -> list[dict]:
    url = f"https://zenodo.org/api/records/{record_id}"
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        data = r.json()
    return sorted(data.get("files", []), key=lambda f: f.get("size", 0))


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=600.0, follow_redirects=True) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or download public tibia CT datasets from Zenodo.")
    parser.add_argument("--dataset", choices=list(RECORDS.keys()), default="platif")
    parser.add_argument("--list-only", action="store_true", help="List available files and sizes without downloading.")
    parser.add_argument("--max-files", type=int, default=2, help="Number of smallest files to download.")
    parser.add_argument("--min-mb", type=float, default=0.0, help="Skip files smaller than this size in MB.")
    args = parser.parse_args()

    info = RECORDS[args.dataset]
    print(f"Dataset: {info['description']} (Zenodo {info['record_id']})")
    files = inspect_zenodo_record(info["record_id"])
    if args.min_mb > 0:
        files = [f for f in files if f.get("size", 0) >= args.min_mb * 1048576]
    for idx, f in enumerate(files):
        mb = f.get("size", 0) / (1024 * 1024)
        print(f"  [{idx}] {f.get('key')} ({mb:.1f} MB)")

    if args.list_only:
        return

    for f in files[: args.max_files]:
        key = f["key"]
        dl_url = f["links"]["self"]
        dest = DATA_SAMPLES / args.dataset / key
        if dest.exists() and dest.stat().st_size == f.get("size", 0):
            print(f"Already downloaded: {dest}")
            continue
        print(f"Downloading {key} ({f.get('size', 0) / 1048576:.1f} MB) -> {dest}...")
        download_file(dl_url, dest)
        print("Done.")


if __name__ == "__main__":
    main()
