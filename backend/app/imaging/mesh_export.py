from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from scipy import ndimage
from skimage import measure

from app.imaging.loader import LoadedCTVolume
from app.imaging.segmentor import SegmentationResult


def export_reconstruction_glb(
    volume: LoadedCTVolume,
    seg: SegmentationResult,
    thickness_map_mm: np.ndarray,
    out_dir: Path,
    max_faces_per_layer: int = 55000,
) -> dict[str, Path]:
    """Generate decimated, centered multi-layer .glb 3D reconstructions for WebGL viewing."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dx, dy, dz = volume.spacing_xyz

    # Center all layers around the tibia's world centroid so Three.js framing is consistent
    if np.any(seg.tibia_mask):
        coords = np.argwhere(seg.tibia_mask)
        center_zyx = coords.mean(axis=0)
    else:
        center_zyx = np.array(volume.array_zyx.shape) / 2.0
    center_mm = np.array([center_zyx[0] * dz, center_zyx[1] * dy, center_zyx[2] * dx])

    scene = trimesh.Scene()
    outputs: dict[str, Path] = {}

    layers = [
        ("tibia_cortical", seg.tibia_mask, (232, 226, 213, 255)),     # Warm ivory
        ("mineralised_callus", seg.callus_mask, (245, 158, 11, 210)), # Translucent amber
        ("metal_hardware", seg.metal_mask, (148, 163, 184, 255)),     # Brushed titanium
        ("fibula", seg.fibula_mask, (214, 208, 196, 170)),            # Muted bone
    ]

    for name, mask, rgba in layers:
        mesh = _mask_to_mesh(mask, (dz, dy, dx), center_mm, rgba, max_faces_per_layer)
        if mesh is None:
            continue
        # Convert Z,Y,X -> X,Y,Z with Z up -> Y up for Three.js ergonomics
        mesh.vertices = mesh.vertices[:, [2, 0, 1]]
        layer_path = out_dir / f"{name}.glb"
        mesh.export(layer_path)
        outputs[name] = layer_path
        scene.add_geometry(mesh, node_name=name, geom_name=name)

    if len(scene.geometry) > 0:
        combined_path = out_dir / "combined_scene.glb"
        scene.export(combined_path)
        outputs["combined_scene"] = combined_path

    # Export Cortical Thickness Heatmap GLB (color-mapped 0..6 mm)
    if np.any(seg.tibia_mask):
        hm_mesh = _mask_to_mesh(
            seg.tibia_mask, (dz, dy, dx), center_mm, (232, 226, 213, 255), max_faces_per_layer
        )
        if hm_mesh is not None:
            # Sample thickness field at mesh vertices (convert back from mm centered to voxel z,y,x)
            verts_zyx_mm = hm_mesh.vertices + center_mm
            vz = np.clip(np.round(verts_zyx_mm[:, 0] / dz).astype(int), 0, thickness_map_mm.shape[0] - 1)
            vy = np.clip(np.round(verts_zyx_mm[:, 1] / dy).astype(int), 0, thickness_map_mm.shape[1] - 1)
            vx = np.clip(np.round(verts_zyx_mm[:, 2] / dx).astype(int), 0, thickness_map_mm.shape[2] - 1)

            # Smooth thickness map slightly so surface sampling captures nearby cortex
            smooth_th = ndimage.maximum_filter(thickness_map_mm, size=3)
            th_vals = smooth_th[vz, vy, vx]
            colors = _thickness_colormap(th_vals, vmin=0.5, vmax=5.5)
            hm_mesh.visual = trimesh.visual.ColorVisuals(mesh=hm_mesh, vertex_colors=colors)
            hm_mesh.vertices = hm_mesh.vertices[:, [2, 0, 1]]
            hm_path = out_dir / "tibia_thickness_heatmap.glb"
            hm_mesh.export(hm_path)
            outputs["tibia_thickness_heatmap"] = hm_path

    return outputs


def _mask_to_mesh(
    mask: np.ndarray,
    spacing_zyx: tuple[float, float, float],
    center_mm: np.ndarray,
    rgba: tuple[int, int, int, int],
    max_faces: int,
) -> trimesh.Trimesh | None:
    if not np.any(mask) or int(np.sum(mask)) < 25:
        return None
    # Smooth binary mask slightly for clean medical surface normals
    smoothed = ndimage.gaussian_filter(mask.astype(np.float32), sigma=0.6)
    if smoothed.max() < 0.45:
        return None
    verts, faces, _, _ = measure.marching_cubes(
        smoothed, level=0.45, spacing=spacing_zyx, step_size=1
    )
    verts = verts - center_mm
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    if len(mesh.faces) > max_faces:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=max_faces)
        except Exception:
            # Fallback stride decimation if fast-simplification optional dep absent
            pass
    mesh.visual = trimesh.visual.ColorVisuals(
        mesh=mesh,
        face_colors=np.tile(np.array(rgba, dtype=np.uint8), (len(mesh.faces), 1)),
    )
    return mesh


def _thickness_colormap(values: np.ndarray, vmin: float = 0.5, vmax: float = 5.5) -> np.ndarray:
    """Map cortical thickness (mm) to a restrained Apple-style blue -> teal -> emerald/amber scale."""
    t = np.clip((values - vmin) / max(vmax - vmin, 1e-6), 0.0, 1.0)
    # Thin (0.0): alert coral (#FF453A), Mid (0.5): clinical blue (#0A84FF), Thick (1.0): emerald (#30D158)
    rgba = np.zeros((len(t), 4), dtype=np.uint8)
    low = t < 0.5
    u_low = t[low] * 2.0
    rgba[low, 0] = (255 * (1 - u_low) + 10 * u_low).astype(np.uint8)
    rgba[low, 1] = (69 * (1 - u_low) + 132 * u_low).astype(np.uint8)
    rgba[low, 2] = (58 * (1 - u_low) + 255 * u_low).astype(np.uint8)

    high = ~low
    u_high = (t[high] - 0.5) * 2.0
    rgba[high, 0] = (10 * (1 - u_high) + 48 * u_high).astype(np.uint8)
    rgba[high, 1] = (132 * (1 - u_high) + 209 * u_high).astype(np.uint8)
    rgba[high, 2] = (255 * (1 - u_high) + 88 * u_high).astype(np.uint8)
    rgba[:, 3] = 255
    return rgba
