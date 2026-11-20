# BONE-MAP — `/brag` Launch Video Plan (`brag-slim`)

- **One-sentence pitch:** BONE-MAP turns medical CT scans and follow-up radiographs into 3D bone reconstructions and quantitative architecture metrics paired with physiotherapy recovery tracking.
- **Target audience:** Orthopaedic trauma researchers, radiologists, physiotherapists, and biomedical engineers.
- **Tone:** `polished` — calm, Apple-minimalist clinical workstation aesthetic, restrained motion, crisp typography (`#F5F5F7`, `#FFFFFF`, `#1D1D1F`, `#0071E3`).
- **Format:** `landscape` (`1920 × 1080`, `30 fps`, `20.0 s` = `600` frames).
- **Music & Beat Grid:** `120 BPM` (`0.5 s` / beat, `2.0 s` / 4-beat bar). Clean ambient-minimalist synth pulse in C minor / Eb major with soft sub-bass, warm Rhodes-like chords, and subtle beat-locked UI ticks/whooshes on scene transitions.
- **Data Privacy:** Uses strictly open-access public datasets (`VSDFullBody 016`, `PlaTiF 190`) — zero real patient PII, zero emails, zero internal paths.

## Scene-by-Scene Storyboard (`20.0 s`)

| Scene | Time | Beats | Visuals & Real App Material |
| :--- | :--- | :--- | :--- |
| **1. Hook** | `0.0s – 2.5s` | `0 – 5` | Studio light `#F5F5F7` canvas. `BONE-MAP` wordmark + `"CT scans to 3D bone architecture."` Assembled alongside the real rotating `VSD-016` 3D tibia mesh emerging smoothly on the right. *(Settled poster frame at `t = 1.8s`)* |
| **2. 3D AI Quantification** | `2.5s – 7.5s` | `5 – 15` | Real Apple-style BONE-MAP Overview (`VSD-016 · 0.6 mm CT`). Left: rotating `VSD-016` 3D tibia & fibula switching smoothly from `Anatomy` to `Cortical Thickness Map` at `t = 4.5s` (beat 9) + `2D Axial Slice` inset. Right: `2.50 mm` Mean Cortical Thickness (`0.00 mm` error vs GT), `4/4` Bridged, `0.917` TotalSegmentator Dice, and the real 28-bin Axial Cortical Profile sparkline. |
| **3. Fracture Radiology** | `7.5s – 12.5s` | `15 – 25` | Cut on beat 15 (`7.5s`) to obsidian clinical stage (`PLATIF-190 · Schatzker Type 5`). Real AP Radiograph + Expert Tibia Mask overlay + 2D Coronal CT side-by-side with interactive 4-cortex `mRUST` scorer. |
| **4. Structural + Physio Link** | `12.5s – 16.5s` | `25 – 33` | Cut on beat 25 (`12.5s`). Clean Dual-Track summary pairing Imaging (`3D CT` + `mRUST`) with Physiotherapy Outcomes (`LEFS /80`, `Dynamometry %`, `Gait Speed`, `Pain VAS`) + `3D Slicer` `.nii.gz` round-trip & `CSV Export`. |
| **5. Punchline Outro** | `16.5s – 20.0s` | `33 – 40` | Smooth fade to `#1D1D1F`: `"Quantify healing before you predict it."` · `"BONE-MAP · Open-Data Research Prototype"` · `"FastAPI · Next.js · TotalSegmentator AI"`. |

## Share Caption
`BONE-MAP turns clinical bone CTs and follow-up X-rays into 3D reconstructions, cortical thickness maps (0.917 Dice vs. ground truth on VSDFullBody), and physiotherapy recovery tracking — all in a minimalist local workstation.`
