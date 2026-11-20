# BONE-MAP — Bone Architecture Quantification & Fracture Recovery Monitoring

Local-first research platform grounded in `Medical overview for BONE-MAP project-research.docx`.

## Quick Start (Windows)

Run the one-click launcher from PowerShell:

```powershell
.\start-bonemap.ps1
```

Or launch manually in two terminals:

1. **Backend (FastAPI + Python 3.12 Imaging & AI Engine):**
   ```powershell
   cd backend
   .\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
2. **Frontend (Next.js + Three.js 3D Viewer):**
   ```powershell
   cd frontend
   npm run dev
   ```
3. Open **http://localhost:3000**.

## Automated Verification (`pytest`)

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests\ -v
```

## Segmentation Engines

- **TotalSegmentator AI (`appendicular_bones`):** Licensed non-commercial GPU AI segmentation (`tibia`, `fibula`, etc.). Configure via `totalseg_set_license -l <KEY>`.
- **Fast Lower-Limb HU + Morphology (`auto_lower_limb`):** Zero-dependency CPU fallback with metal implant (`>= 2500 HU`) exclusion ring.
- **3D Slicer Mask Round-Trip:** Export `segmentation_labels.nii.gz` and re-import corrected masks directly in **Data & Tools**.

## Public Clinical Datasets (Zenodo)

Download or inspect open-access datasets into `data/samples/`:

```powershell
cd backend
# PlaTiF (Tibial plateau fracture radiographs + 2D coronal CT slices + metadata)
.\.venv\Scripts\python.exe ..\scripts\fetch_public_tibia.py --dataset platif --list-only

# VSDFullBody (Real 3D full-body human CT NIfTI scans)
.\.venv\Scripts\python.exe ..\scripts\fetch_public_tibia.py --dataset vsdfullbody --min-mb 100 --list-only

# Validation Suite (PENGWIN clinical fractures, ORMIR HR-pQCT .AIM, matched VSDFullBody CT + GT masks)
.\.venv\Scripts\python.exe ..\scripts\download_validation_suite.py
```
