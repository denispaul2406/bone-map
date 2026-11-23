# BONE-MAP — Q1 JIIM Paper Specification (`PaperOrchestra` Workflow Artifact)

## Target Primary Venue (Free Subscription Hybrid, PubMed + Scopus Q1)
- **Primary Journal:** *Journal of Imaging Informatics in Medicine* (Springer Nature; IF ~3.1; Q1 Medical Imaging / Health Informatics; PubMed + PMC + Scopus indexed; `$0` via traditional Subscription route).
- **Companion Software Paper (Optional Later):** *Journal of Open Source Software* (`JOSS`; `$0` Diamond Open Access; links to the validated JIIM clinical/benchmark paper cleanly).

## Core Clinical & Engineering Thesis (Problem + Solution)
1. **Clinical Gap:** Rehabilitation after tibial fractures requires aligning 3D bone healing geometry (cortical thickness distribution, 4-quadrant bridging, alignment) with mechanical load progression (`%BW`, active knee `ROM`, `Pain VAS`, `LEFS`, clinician `mRUST`).
2. **Algorithmic Reliability Gap:** Naive CT bone tools either report sub-millimeter trabecular microarchitecture (`Tb.Th`, `Tb.Sp`) on `0.75–1.0 mm` clinical CTs (violating Nyquist sampling limits), fabricate BMD (`mg/cm³`) without phantoms, or omit fibula-referenced left/right polarity.
3. **BONE-MAP Solution:** Open-source architecture (`FastAPI + SQLite + SimpleITK + TotalSegmentator + Next.js/Three.js`) integrating:
   - Bidirectional physical Nyquist gate (`<= 0.25 mm` unlocks medial-ridge trabecular quantification matching Scanco IPL `0.2414 mm` within `0.0194 mm` / <1 voxel; `> 0.25 mm` locks cleanly).
   - Dual segmentation (`TotalSegmentator appendicular_bones` GPU vs fast CPU HU fallback + 3D Slicer NIfTI round-trip) with dilated metallic artifact exclusion (`>= 2500 HU`).
   - Fibula-referenced 4-quadrant continuity polarity and strict clinician separation (`mRUST` 4–16 never auto-synthesized).

## Planned Full Q1 Quantitative Validation Upgrades
1. **3D Segmentation & Morphometry (`N = 10–15` matched `VSDFullBody` CT + published 3D Slicer GT pairs):** Mean ± SD Dice, `HD95 (mm)`, `ASSD (mm)`, Bland–Altman cortical thickness agreement (`TotalSegmentator` vs `Fast HU`).
2. **Micro-CT Positive Resolution-Gate Validation (`ORMIR CHAR_NOCMP_020` & `030`, `0.020 mm`):** Medial-ridge EDT (`0.222 mm`) vs Hildebrand–Rüegsegger sphere-fit reference (`0.2414 mm`).
3. **Full Clinical Tibial Plateau Cohort (`PlaTiF Parts 1–5`, `N = 186`):** Schatzker I–VI fracture vs normal morphology characterization and paired coronal CT availability.
4. **`PaperOrchestra` Quality & Literature Loop (Option B):** Systematic literature comparison against existing bone morphometry / TotalSegmentator / mRUST tools -> Springer LNCS/IMIM LaTeX build -> multi-round `AgentReview` critique & rebuttal-via-revision before submission.
