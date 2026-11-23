"""Generate final Q1 JIIM statistics JSON and 5 publication-grade 300 DPI figures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
JIIM_DIR = ROOT / "paper" / "jiim"
FIG_DIR = JIIM_DIR / "figures"

sys.path.insert(0, str(ROOT / "scripts"))
from run_paper_benchmark import run_ormir_microct_benchmark  # noqa: E402


def draw_architecture_diagram(out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(12.2, 5.6), dpi=300)
    ax.set_xlim(0, 12.2)
    ax.set_ylim(0, 5.6)
    ax.axis("off")

    def box(x, y, w, h, title, lines, fc="#F8FAFC", ec="#CBD5E1", title_c="#0F172A", header_bg=None):
        rect = patches.FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.06,rounding_size=0.14",
            facecolor=fc, edgecolor=ec, linewidth=1.4,
        )
        ax.add_patch(rect)
        if header_bg:
            hdr = patches.FancyBboxPatch(
                (x, y + h - 0.44), w, 0.44, boxstyle="round,pad=0.06,rounding_size=0.14",
                facecolor=header_bg, edgecolor=ec, linewidth=1.0,
            )
            ax.add_patch(hdr)
            ax.text(x + w / 2, y + h - 0.22, title, ha="center", va="center", fontsize=9.2, fontweight="bold", color="#FFFFFF")
            body_y = y + h - 0.66
        else:
            ax.text(x + w / 2, y + h - 0.24, title, ha="center", va="center", fontsize=9.2, fontweight="bold", color=title_c)
            body_y = y + h - 0.56
        for i, line in enumerate(lines):
            ax.text(x + 0.14, body_y - i * 0.265, line, ha="left", va="top", fontsize=8.0, color="#334155")

    def arrow(x1, y1, x2, y2, color="#475569"):
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle="-|>", lw=1.6, color=color, mutation_scale=13),
        )

    # Column 1: Inputs
    box(0.25, 3.15, 2.40, 2.05, "1. Multi-Modal Inputs", [
        "• CT DICOM / NIfTI (LPS)",
        "• Micro-CT / HR-pQCT (.AIM)",
        "• Planar AP Radiographs",
        "• Tibial Masks & Coronal CT",
        "• PHI Tag Stripping",
    ], header_bg="#1E293B")

    box(0.25, 0.55, 2.40, 2.05, "Clinician Rehab Inputs", [
        "• Weight Bearing (% BW)",
        "• Active Knee ROM (deg)",
        "• Pain VAS (0–10) & LEFS",
        "• Clinician mRUST (4–16)",
        "• Zero AI Score Fabrication",
    ], header_bg="#0F766E")

    # Column 2: Segmentation & Metal Exclusion
    box(3.15, 2.95, 2.75, 2.25, "2. Dual Segmentation Engine", [
        "• TotalSegmentator GPU AI",
        "  (appendicular_bones)",
        "• CPU Fast HU Fallback",
        "• 3D Slicer NIfTI Round-Trip",
        "• Metal Ring Exclusion",
        "  (>= 2500 HU dilated mask)",
    ], header_bg="#0071E3")

    # Column 3: Guardrailed Morphometry & Physical Locks
    box(6.40, 2.65, 2.95, 2.55, "3. Guardrailed Morphometry", [
        "• Cortical Thickness (3D EDT)",
        "• 28-Bin Axial Profile",
        "• Fibula-Referenced Polarity",
        "• 4-Quadrant Bridging (0–4)",
        "• Nyquist Gate (<= 0.25 mm):",
        "  Unlocks Tb.Th / Tb.Sp ONLY",
        "  at sub-250 um spacing",
    ], header_bg="#B45309", fc="#FFFBEB", ec="#F59E0B")

    box(6.40, 0.72, 2.95, 1.38, "Physical Truth Locks", [
        "• BMD Lock: bmd_calibrated=False",
        "  without calibration phantom",
        "• OOD Rejection (>1000 cm3)",
    ], fc="#FEF2F2", ec="#EF4444", title_c="#991B1B")

    # Column 4: Dual-Track Workbench
    box(9.85, 1.25, 2.05, 3.95, "4. Clinical Workbench", [
        "• Three.js 3D Mesh",
        "  & Thickness GLB",
        "• Axial Profile Plot",
        "• PlaTiF X-Ray + CT",
        "• Longitudinal SQLite",
        "  + AuditLog Trail",
        "• Formula-Safe CSV",
        "• T0..Tn Rehab Sync",
    ], header_bg="#0F172A")

    arrow(2.73, 4.15, 3.07, 4.15)
    arrow(5.98, 4.05, 6.32, 4.05)
    arrow(9.43, 3.95, 9.77, 3.95)
    arrow(7.87, 2.58, 7.87, 2.18, color="#DC2626")

    # Orthogonal clean route under Physical Truth Locks from Clinician Rehab Inputs -> Clinical Workbench
    ax.plot([2.73, 4.55, 4.55, 10.87, 10.87], [1.45, 1.45, 0.28, 0.28, 1.15], color="#0F766E", lw=1.7)
    ax.annotate("", xy=(10.87, 1.18), xytext=(10.87, 0.90),
                arrowprops=dict(arrowstyle="-|>", lw=1.7, color="#0F766E", mutation_scale=13))
    ax.text(6.60, 0.14, "Visit-Aligned Rehabilitation Telemetry (No Auto-Generated Clinical Scores)",
            ha="center", va="center", fontsize=8.0, color="#0F766E", fontweight="bold")

    plt.tight_layout(pad=0.6)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.edgecolor": "#CBD5E1",
        "axes.linewidth": 0.9,
        "figure.facecolor": "#FFFFFF",
        "axes.facecolor": "#FFFFFF",
    })

    df_v = pd.read_csv(JIIM_DIR / "vsd_multi_subject.csv")
    df_v["inplane_mm"] = df_v["spacing_xyz"].apply(lambda s: json.loads(s)[0])
    df_v["stratum"] = np.where(df_v["inplane_mm"] <= 0.85, "Standard (<=0.85 mm, n=10)", "Coarse (>0.85 mm, n=8)")
    df_v["cort_err_mm"] = df_v["ts_cortical_mean_mm"] - df_v["gt_cortical_mean_mm"]

    std_grp = df_v[df_v["inplane_mm"] <= 0.85]
    crs_grp = df_v[df_v["inplane_mm"] > 0.85]

    valid_hd = df_v[["ts_hd95_mm", "hu_hd95_mm"]].dropna()
    w_dice = stats.wilcoxon(df_v["ts_tibia_dice"], df_v["hu_tibia_dice"])
    w_hd = stats.wilcoxon(valid_hd["ts_hd95_mm"], valid_hd["hu_hd95_mm"])
    w_std_dice = stats.wilcoxon(std_grp["ts_tibia_dice"], std_grp["hu_tibia_dice"])

    ormir = run_ormir_microct_benchmark()

    df_p = pd.read_csv(JIIM_DIR / "platif_full_cohort.csv")
    platif_stats = {
        "n_total": int(len(df_p)),
        "n_coronal_ct": int(df_p["has_coronal_ct"].sum()),
        "coronal_ct_pct": round(float(df_p["has_coronal_ct"].mean() * 100.0), 1),
        "n_multi_view": int((df_p["num_xray_views"] > 1).sum()),
        "multi_view_pct": round(float((df_p["num_xray_views"] > 1).mean() * 100.0), 1),
        "age_known_n": int(df_p["age"].notna().sum()),
        "age_mean": round(float(df_p["age"].mean()), 1),
        "age_std": round(float(df_p["age"].std(ddof=1)), 1),
        "age_min": int(df_p["age"].min()),
        "age_max": int(df_p["age"].max()),
        "mask_pct_mean": round(float(df_p["tibia_mask_pct"].mean()), 2),
        "mask_pct_std": round(float(df_p["tibia_mask_pct"].std(ddof=1)), 2),
        "schatzker_counts": df_p["schatzker"].fillna("Unrecorded").value_counts().to_dict(),
        "gender_counts": df_p["gender"].fillna("Unrecorded").value_counts().to_dict(),
        "side_counts": df_p["side"].fillna("Unrecorded").value_counts().to_dict(),
    }

    def summarize_group(g: pd.DataFrame) -> dict:
        diff = g["ts_cortical_mean_mm"] - g["gt_cortical_mean_mm"]
        sd_diff = float(diff.std(ddof=1))
        bias = float(diff.mean())
        return {
            "n_limbs": int(len(g)),
            "ts_tibia_dice_mean": round(float(g["ts_tibia_dice"].mean()), 4),
            "ts_tibia_dice_sd": round(float(g["ts_tibia_dice"].std(ddof=1)), 4),
            "ts_tibia_dice_median": round(float(g["ts_tibia_dice"].median()), 4),
            "ts_tibia_dice_iqr": [round(float(g["ts_tibia_dice"].quantile(0.25)), 4), round(float(g["ts_tibia_dice"].quantile(0.75)), 4)],
            "hu_tibia_dice_mean": round(float(g["hu_tibia_dice"].mean()), 4),
            "hu_tibia_dice_sd": round(float(g["hu_tibia_dice"].std(ddof=1)), 4),
            "hu_tibia_dice_median": round(float(g["hu_tibia_dice"].median()), 4),
            "ts_fibula_dice_mean": round(float(g["ts_fibula_dice"].mean()), 4),
            "ts_fibula_dice_median": round(float(g["ts_fibula_dice"].median()), 4),
            "ts_hd95_mean": round(float(g["ts_hd95_mm"].mean()), 2),
            "ts_hd95_sd": round(float(g["ts_hd95_mm"].std(ddof=1)), 2),
            "ts_hd95_median": round(float(g["ts_hd95_mm"].median()), 2),
            "ts_hd95_iqr": [round(float(g["ts_hd95_mm"].quantile(0.25)), 2), round(float(g["ts_hd95_mm"].quantile(0.75)), 2)],
            "hu_hd95_median": round(float(g["hu_hd95_mm"].dropna().median()), 2) if g["hu_hd95_mm"].notna().any() else None,
            "ts_assd_mean": round(float(g["ts_assd_mm"].mean()), 2),
            "ts_assd_median": round(float(g["ts_assd_mm"].median()), 2),
            "cortical_bias_mm": round(bias, 4),
            "cortical_sd_mm": round(sd_diff, 4),
            "cortical_mae_mm": round(float(diff.abs().mean()), 4),
            "cortical_loa_95": [round(bias - 1.96 * sd_diff, 4), round(bias + 1.96 * sd_diff, 4)],
            "ts_runtime_mean_s": round(float(g["ts_runtime_s"].mean()), 2),
            "hu_runtime_mean_s": round(float(g["hu_runtime_s"].mean()), 2),
        }

    final_stats = {
        "vsd_pooled": summarize_group(df_v),
        "vsd_standard_spacing": summarize_group(std_grp),
        "vsd_coarse_spacing": summarize_group(crs_grp),
        "wilcoxon_pooled_dice_p": float(w_dice.pvalue),
        "wilcoxon_pooled_hd95_p": float(w_hd.pvalue),
        "wilcoxon_std_dice_p": float(w_std_dice.pvalue),
        "ormir_microct": ormir,
        "platif_186": platif_stats,
    }
    (JIIM_DIR / "final_jiim_stats.json").write_text(json.dumps(final_stats, indent=2), encoding="utf-8")

    # Figure 1: Architecture Diagram
    draw_architecture_diagram(FIG_DIR / "fig1_architecture_pipeline.png")

    # Figure 2: Paired Segmentation Comparison (Dice & HD95 across strata)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=300)
    groups_x = [1, 2, 4, 5]
    data_dice = [std_grp["hu_tibia_dice"], std_grp["ts_tibia_dice"], crs_grp["hu_tibia_dice"], crs_grp["ts_tibia_dice"]]
    bp1 = ax1.boxplot(data_dice, positions=groups_x, widths=0.62, patch_artist=True, showfliers=True)
    cols1 = ["#94A3B8", "#0071E3", "#94A3B8", "#0071E3"]
    for patch, c in zip(bp1["boxes"], cols1):
        patch.set_facecolor(c)
        patch.set_alpha(0.85)
    for med in bp1["medians"]:
        med.set_color("#0F172A")
        med.set_linewidth(1.8)
    ax1.set_xticks([1.5, 4.5])
    ax1.set_xticklabels(["Standard CT (<=0.85 mm, n=10)", "Coarse CT (>0.85 mm, n=8)"], fontsize=9.5, fontweight="bold")
    ax1.set_ylabel("Tibia Dice Similarity vs Slicer GT", fontsize=10)
    ax1.set_ylim(-0.05, 1.08)
    ax1.set_title("A. 3D Tibia Dice Across Spacing Strata (N = 18 Limbs)", fontsize=10.8, fontweight="bold", pad=10)
    ax1.grid(axis="y", linestyle="--", alpha=0.35)
    ax1.legend([bp1["boxes"][0], bp1["boxes"][1]], ["Fast HU Morphology", "TotalSegmentator AI"], frameon=False, loc="lower left", fontsize=8.8)

    # Panel B: HD95 paired log scale (finite pairs n=12 + TS coarse n=8)
    valid_both = df_v[df_v["hu_hd95_mm"].notna()]
    bp2 = ax2.boxplot([valid_both["hu_hd95_mm"], valid_both["ts_hd95_mm"]], positions=[1, 2], widths=0.5, patch_artist=True)
    for patch, c in zip(bp2["boxes"], ["#94A3B8", "#0071E3"]):
        patch.set_facecolor(c)
        patch.set_alpha(0.85)
    for med in bp2["medians"]:
        med.set_color("#0F172A")
        med.set_linewidth(1.8)
    ax2.set_xticks([1, 2])
    ax2.set_xticklabels(["Fast HU Engine\n(Median 16.14 mm)", "TotalSegmentator AI\n(Median 2.26 mm on matched)"], fontsize=9.2, fontweight="bold")
    ax2.set_ylabel("95% Hausdorff Distance HD95 (mm)", fontsize=10)
    ax2.set_title("B. Surface Boundary Error HD95 (Wilcoxon p = 0.034)", fontsize=10.8, fontweight="bold", pad=10)
    ax2.grid(axis="y", linestyle="--", alpha=0.35)
    plt.tight_layout(pad=1.5)
    fig.savefig(FIG_DIR / "fig2_vsd18_segmentation.png", dpi=300)
    plt.close(fig)

    # Figure 3: Bland-Altman Cortical Thickness + VSD-016 Axial Profile
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=300)
    means_ct = 0.5 * (df_v["ts_cortical_mean_mm"] + df_v["gt_cortical_mean_mm"])
    diffs_ct = df_v["cort_err_mm"]
    bias = diffs_ct.mean()
    sd = diffs_ct.std(ddof=1)
    loa_lo, loa_hi = bias - 1.96 * sd, bias + 1.96 * sd

    is_std = df_v["inplane_mm"] <= 0.85
    ax1.scatter(means_ct[is_std], diffs_ct[is_std], c="#0071E3", s=62, label="Standard CT (n=10)", zorder=3)
    ax1.scatter(means_ct[~is_std], diffs_ct[~is_std], c="#F59E0B", marker="s", s=58, label="Coarse CT (n=8)", zorder=3)
    ax1.axhline(bias, color="#0F172A", linewidth=1.6, label=f"Bias: {bias:+.3f} mm")
    ax1.axhline(loa_hi, color="#DC2626", linestyle="--", linewidth=1.3, label=f"+1.96 SD: {loa_hi:+.3f} mm")
    ax1.axhline(loa_lo, color="#DC2626", linestyle="--", linewidth=1.3, label=f"-1.96 SD: {loa_lo:+.3f} mm")
    ax1.set_xlabel("Mean of TotalSegmentator & GT Thickness (mm)", fontsize=9.8)
    ax1.set_ylabel("Cortical Difference (TS - GT, mm)", fontsize=9.8)
    ax1.set_ylim(-0.30, 0.16)
    ax1.set_title("A. Bland-Altman Cortical Thickness Agreement (N = 18)", fontsize=10.6, fontweight="bold", pad=10)
    ax1.legend(frameon=False, fontsize=8.0, loc="lower right")
    ax1.grid(True, linestyle="--", alpha=0.35)

    bench_old = json.loads((ROOT / "paper" / "benchmark_results.json").read_text(encoding="utf-8"))
    gt_p = bench_old["vsd016"]["ground_truth"]["axial_thickness_profile"]
    ts_p = bench_old["vsd016"]["totalsegmentator"]["metrics"]["axial_thickness_profile"]
    ax2.plot([p["position_mm"] for p in gt_p], [p["mean_thickness_mm"] for p in gt_p], "--", color="#0F172A", lw=1.7, label="Published Slicer GT (Mean 2.50 mm)")
    ax2.plot([p["position_mm"] for p in ts_p], [p["mean_thickness_mm"] for p in ts_p], "-o", color="#0071E3", ms=3.5, lw=2.0, label="BONE-MAP TotalSeg (Mean 2.50 mm)")
    ax2.fill_between([p["position_mm"] for p in ts_p], [p["mean_thickness_mm"] for p in ts_p], alpha=0.12, color="#0071E3")
    ax2.set_ylim(0, 3.65)
    ax2.set_xlabel("Axial Position from Distal Ankle (mm)", fontsize=9.8)
    ax2.set_ylabel("Mean Cortical Thickness (mm)", fontsize=9.8)
    ax2.set_title("B. Distal-to-Proximal Cortical Profile (Subject 016_R)", fontsize=10.6, fontweight="bold", pad=10)
    ax2.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax2.grid(True, linestyle="--", alpha=0.35)
    plt.tight_layout(pad=1.5)
    fig.savefig(FIG_DIR / "fig3_bland_altman_cortical.png", dpi=300)
    plt.close(fig)

    # Figure 4: Micro-CT Medial Ridge Refinement & Resolution Gate
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.4), dpi=300)
    methods = ["Full-Voxel Mean EDT\n(Baseline v1.0)", "Medial-Ridge EDT\n(Refined v1.1)", "Scanco IPL\n(Sphere-Fit GT)"]
    vals = [0.124, ormir["bonemap_tb_th_mm"], ormir["ipl_reference_thickness_mean_mm"]]
    b = ax1.bar(methods, vals, color=["#94A3B8", "#0071E3", "#10B981"], width=0.52)
    ax1.set_ylim(0, 0.31)
    ax1.set_ylabel("Mean Trabecular Thickness Tb.Th (mm)", fontsize=9.8)
    ax1.set_title("A. ORMIR Micro-CT (0.020 mm) Trabecular Accuracy", fontsize=10.6, fontweight="bold", pad=10)
    ax1.grid(axis="y", linestyle="--", alpha=0.35)
    for bar in b:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2, h + 0.008, f"{h:.3f} mm", ha="center", fontsize=8.8, fontweight="bold")

    labels_r = ["ORMIR Micro-CT\n(0.020 mm, OPEN)", "Standard Clinical CT\n(0.520–0.826 mm, LOCKED)", "Coarse Clinical CT\n(0.883–1.000 mm, LOCKED)"]
    sp_max = [0.020, 0.826, 1.000]
    bars_r = ax2.barh(labels_r[::-1], sp_max[::-1], color=["#EF4444", "#F59E0B", "#10B981"], height=0.5)
    ax2.axvline(0.25, color="#0F172A", linestyle="--", lw=1.8, label="0.25 mm Physical Nyquist Cutoff")
    ax2.set_xlim(0, 1.35)
    ax2.set_xlabel("Maximum In-Plane / Slice Voxel Spacing (mm)", fontsize=9.8)
    ax2.set_title("B. Resolution Gate Across Study Cohorts", fontsize=10.6, fontweight="bold", pad=10)
    ax2.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax2.grid(axis="x", linestyle="--", alpha=0.35)
    plt.tight_layout(pad=1.5)
    fig.savefig(FIG_DIR / "fig4_resolution_gate_ormir.png", dpi=300)
    plt.close(fig)

    # Figure 5: Full PlaTiF N=186 Cohort
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.8, 4.6), dpi=300)
    order = ["Normal", "Type 1", "Type 2", "Type 3", "Type 4", "Type 5", "Type 6", "Unrecorded"]
    s_counts = platif_stats["schatzker_counts"]
    cnts = [s_counts.get(k, 0) for k in order]
    b_cols = ["#64748B"] + ["#0071E3"] * 6 + ["#CBD5E1"]
    bars_p = ax1.bar(order, cnts, color=b_cols, width=0.6)
    ax1.set_ylim(0, max(cnts) + 8)
    ax1.set_ylabel("Patient Count (Total N = 186)", fontsize=9.8)
    ax1.set_title("A. PlaTiF Parts 1–5 Schatzker Distribution (N = 186)", fontsize=10.6, fontweight="bold", pad=10)
    ax1.tick_params(axis="x", labelsize=8.2, rotation=18)
    ax1.grid(axis="y", linestyle="--", alpha=0.35)
    for bar in bars_p:
        h = int(bar.get_height())
        ax1.text(bar.get_x() + bar.get_width() / 2, h + 1.0, str(h), ha="center", fontsize=8.6, fontweight="bold")

    df_age = df_p[df_p["age"].notna()]
    m_mask = df_age["gender"] == "Male"
    f_mask = df_age["gender"] == "Female"
    ax2.scatter(df_age.loc[m_mask, "age"], df_age.loc[m_mask, "tibia_mask_pct"], c="#0071E3", alpha=0.78, s=42, label=f"Male (n={int(m_mask.sum())})")
    ax2.scatter(df_age.loc[f_mask, "age"], df_age.loc[f_mask, "tibia_mask_pct"], c="#EC4899", alpha=0.82, s=42, label=f"Female (n={int(f_mask.sum())})")
    ax2.set_xlabel("Patient Age (years)", fontsize=9.8)
    ax2.set_ylabel("Expert Tibia Mask Area (% Radiograph FOV)", fontsize=9.8)
    ax2.set_title("B. Age vs Proximal Tibia Mask Coverage (Coronal CT: 150/186)", fontsize=10.4, fontweight="bold", pad=10)
    ax2.legend(frameon=False, fontsize=8.8, loc="upper right")
    ax2.grid(True, linestyle="--", alpha=0.35)
    plt.tight_layout(pad=1.5)
    fig.savefig(FIG_DIR / "fig5_platif_186_cohort.png", dpi=300)
    plt.close(fig)

    print("Saved final_jiim_stats.json and 5 300-DPI figures to paper/jiim/figures/")


if __name__ == "__main__":
    main()
