# Pre-Nov 25 Publishing Checklist (GitHub + Zenodo + medRxiv)

## Author Metadata (Ready to Paste on `medRxiv`)
- **Author 1 (Corresponding & Submitting):**
  - First / Given: `Denis` | Last / Family: `Paul`
  - Email: `denispaul2601@gmail.com`
  - ORCID: `0009-0008-1525-6822`
  - Affiliation: `Independent Researcher, Bengaluru, Karnataka, India`
- **Author 2 (Co-Author):**
  - First / Given: `Esha` | Last / Family: `Madapushi Deepak`
  - Email: `esha.madapushi@gmail.com`
  - Affiliation: `College of Physiotherapy, Dayananda Sagar University, Bengaluru, Karnataka, India`
  - *(Note: If Esha creates an ORCID today at orcid.org, add it in the medRxiv co-author box; optional for co-authors.)*

## Step 1: Zenodo GitHub Sync (Do BEFORE tagging `v1.0.0`)
1. Open **zenodo.org -> Account Settings -> GitHub**.
2. Toggle `denispaul2406/bone-map` **ON**.

## Step 2: Create Release `v1.0.0` on GitHub (`github.com/denispaul2406/bone-map`)
1. Once `main` is pushed to `https://github.com/denispaul2406/bone-map`, click **Releases -> Draft a new release**.
2. Tag: `v1.0.0`, Target: `main`, Title: `BONE-MAP v1.0.0 — Preprint Release`, click **Publish release**.
3. Zenodo automatically archives the release and mints a permanent DOI (`10.5281/zenodo.XXXXXXX`) in ~1–2 minutes.

## Step 3: Submit Manuscript to `medRxiv` Today (`submit.medrxiv.org`)
- **Article Type:** Original Research / Methodology
- **Subject Category:** `Health Informatics` (or `Orthopedics`)
- **Manuscript File:** Upload `paper/bonemap_preprint.pdf`
- **Ethics Statement:** *This study performed secondary technical validation solely using pre-existing, de-identified, publicly licensed open-access datasets (VSDFullBody Zenodo 8270365/8302449, PlaTiF Zenodo 18007397, ORMIR Zenodo 21284559, and PENGWIN26 Zenodo 19734383). No new human participants were recruited, no private clinical records or PHI were accessed, and IRB approval was not required.*
- **Funding Statement:** *The authors received no external funding for this work.*
- **Competing Interests:** *Software engineering and validation were conducted independently outside any commercial employer scope. The authors declare no competing interests.*
  - **Data Availability:** *All source code (MIT License) and reproducible benchmark scripts are archived on Zenodo (DOI: 10.5281/zenodo.24389254) and publicly hosted at `https://github.com/denispaul2406/bone-map`.*
