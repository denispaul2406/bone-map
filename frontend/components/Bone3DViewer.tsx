"use client";

import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { Eye, EyeOff, Layers, RotateCcw, SlidersHorizontal, Sun, Moon } from "lucide-react";
import { CTRun, fullAssetUrl } from "@/lib/api";

interface Bone3DViewerProps {
  ctRun: CTRun;
  onOpenSlices?: () => void;
}

type LayerKey = "tibia_cortical" | "mineralised_callus" | "metal_hardware" | "fibula";

export function Bone3DViewer({ ctRun, onOpenSlices }: Bone3DViewerProps) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const layerGroupsRef = useRef<Record<string, THREE.Object3D>>({});
  const initialFrameRef = useRef<{ center: THREE.Vector3; dist: number }>({
    center: new THREE.Vector3(0, 0, 0),
    dist: 280,
  });

  const [darkCanvas, setDarkCanvas] = useState(true);
  const [heatmapMode, setHeatmapMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>({
    tibia_cortical: true,
    mineralised_callus: true,
    metal_hardware: true,
    fibula: true,
  });

  const layersRef = useRef(layers);
  layersRef.current = layers;
  const darkCanvasRef = useRef(darkCanvas);
  darkCanvasRef.current = darkCanvas;

  // Reset heatmap mode if the newly selected CT run doesn't have a heatmap mesh
  useEffect(() => {
    if (!ctRun.assets.tibia_thickness_heatmap) {
      setHeatmapMode(false);
    }
  }, [ctRun.id, ctRun.assets.tibia_thickness_heatmap]);

  const effectiveHeatmap = heatmapMode && Boolean(ctRun.assets.tibia_thickness_heatmap);
  const sceneUrl = fullAssetUrl(
    effectiveHeatmap ? ctRun.assets.tibia_thickness_heatmap : ctRun.assets.combined_scene
  );

  useEffect(() => {
    const container = mountRef.current;
    if (!container || !sceneUrl) return;

    let cancelled = false;
    setLoading(true);
    const width = container.clientWidth || 720;
    const height = container.clientHeight || 560;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(darkCanvasRef.current ? 0x0e1116 : 0xf5f5f7);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(36, width / height, 0.1, 2500);
    camera.position.set(195, 45, 225);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.minDistance = 40;
    controls.maxDistance = 650;
    controlsRef.current = controls;

    const hemi = new THREE.HemisphereLight(0xffffff, 0x3a4050, 0.85);
    scene.add(hemi);
    const keyLight = new THREE.DirectionalLight(0xfffaf0, 1.35);
    keyLight.position.set(160, 220, 180);
    scene.add(keyLight);
    const rimLight = new THREE.DirectionalLight(0xc7ddff, 0.65);
    rimLight.position.set(-180, -80, -140);
    scene.add(rimLight);

    const loader = new GLTFLoader();
    layerGroupsRef.current = {};

    loader.load(
      sceneUrl,
      (gltf) => {
        if (cancelled) return;
        const root = gltf.scene;
        root.traverse((obj) => {
          if ((obj as THREE.Mesh).isMesh) {
            const mesh = obj as THREE.Mesh;
            const mat = mesh.material as THREE.MeshStandardMaterial;
            if (mat) {
              mat.roughness = mesh.name.includes("metal") ? 0.25 : 0.62;
              mat.metalness = mesh.name.includes("metal") ? 0.78 : 0.05;
              if (mesh.name.includes("callus")) {
                mat.transparent = true;
                mat.opacity = 0.76;
              } else if (mesh.name.includes("fibula")) {
                mat.transparent = true;
                mat.opacity = 0.55;
              }
            }
            if (mesh.name) {
              layerGroupsRef.current[mesh.name] = mesh;
            }
          }
        });
        scene.add(root);

        const box = new THREE.Box3().setFromObject(root);
        if (!box.isEmpty()) {
          const center = box.getCenter(new THREE.Vector3());
          const size = box.getSize(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z);
          const dist = (maxDim / (2 * Math.tan((36 * Math.PI) / 360))) * 1.45;
          initialFrameRef.current = { center: center.clone(), dist };
          controls.target.copy(center);
          camera.position.set(
            center.x + dist * 0.55,
            center.y + dist * 0.18,
            center.z + dist * 0.85
          );
          controls.update();
        }

        Object.entries(layersRef.current).forEach(([k, visible]) => {
          if (layerGroupsRef.current[k]) {
            layerGroupsRef.current[k].visible = visible;
          }
        });
        setLoading(false);
      },
      undefined,
      () => {
        if (!cancelled) setLoading(false);
      }
    );

    let rafId = 0;
    const animate = () => {
      rafId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    const handleResize = () => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
      window.removeEventListener("resize", handleResize);
      controls.dispose();
      scene.traverse((obj) => {
        if ((obj as THREE.Mesh).isMesh) {
          const mesh = obj as THREE.Mesh;
          mesh.geometry?.dispose();
          const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          mats.forEach((m) => m?.dispose());
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [sceneUrl]);

  useEffect(() => {
    if (sceneRef.current) {
      sceneRef.current.background = new THREE.Color(darkCanvas ? 0x0e1116 : 0xf5f5f7);
    }
  }, [darkCanvas]);

  useEffect(() => {
    Object.entries(layers).forEach(([key, visible]) => {
      const obj = layerGroupsRef.current[key];
      if (obj) obj.visible = visible;
    });
  }, [layers]);

  const setCameraPreset = (preset: "ap" | "lat" | "reset") => {
    const cam = cameraRef.current;
    const ctrl = controlsRef.current;
    if (!cam || !ctrl) return;
    const { center, dist } = initialFrameRef.current;
    ctrl.target.copy(center);
    if (preset === "ap") cam.position.set(center.x, center.y + dist * 0.05, center.z + dist);
    if (preset === "lat") cam.position.set(center.x + dist, center.y + dist * 0.05, center.z);
    if (preset === "reset")
      cam.position.set(center.x + dist * 0.55, center.y + dist * 0.18, center.z + dist * 0.85);
    ctrl.update();
  };

  const toggleLayer = (key: LayerKey) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="relative h-[560px] w-full overflow-hidden rounded-[22px] border border-black/[0.08] shadow-sm">
      <div ref={mountRef} className="h-full w-full cursor-grab active:cursor-grabbing" />

      {loading && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/20 backdrop-blur-xs">
          <div className="rounded-full bg-white/90 px-4 py-1.5 text-xs font-medium text-[#1D1D1F] shadow-sm">
            Loading 3D reconstruction…
          </div>
        </div>
      )}

      {/* Top-left floating camera & mode pills */}
      <div className="absolute top-3 left-3 flex flex-wrap items-center gap-1.5">
        <div className="flex items-center gap-1 rounded-full bg-white/85 p-1 shadow-sm backdrop-blur-md border border-black/8">
          <button
            onClick={() => setHeatmapMode(false)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              !effectiveHeatmap
                ? "bg-[#1D1D1F] text-white"
                : "text-[#6E6E73] hover:text-[#1D1D1F]"
            }`}
          >
            Anatomy
          </button>
          {ctRun.assets.tibia_thickness_heatmap && (
            <button
              onClick={() => setHeatmapMode(true)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                effectiveHeatmap
                  ? "bg-[#0071E3] text-white"
                  : "text-[#6E6E73] hover:text-[#1D1D1F]"
              }`}
            >
              Cortical Thickness Map
            </button>
          )}
        </div>

        <div className="flex items-center gap-1 rounded-full bg-white/85 p-1 shadow-sm backdrop-blur-md border border-black/8">
          <button
            onClick={() => setCameraPreset("ap")}
            className="rounded-full px-2.5 py-1 text-xs font-medium text-[#1D1D1F] hover:bg-black/5"
          >
            AP
          </button>
          <button
            onClick={() => setCameraPreset("lat")}
            className="rounded-full px-2.5 py-1 text-xs font-medium text-[#1D1D1F] hover:bg-black/5"
          >
            Lateral
          </button>
          <button
            onClick={() => setCameraPreset("reset")}
            title="Reset Camera"
            aria-label="Reset 3D camera"
            className="rounded-full p-1.5 text-[#6E6E73] hover:bg-black/5 hover:text-[#1D1D1F]"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setDarkCanvas((d) => !d)}
            title="Toggle Viewport Theme"
            aria-label="Toggle 3D viewport background theme"
            className="rounded-full p-1.5 text-[#6E6E73] hover:bg-black/5 hover:text-[#1D1D1F]"
          >
            {darkCanvas ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          </button>
          {onOpenSlices && (
            <button
              onClick={onOpenSlices}
              className="inline-flex items-center gap-1 rounded-full bg-[#1D1D1F]/8 px-2.5 py-1 text-xs font-medium text-[#1D1D1F] hover:bg-[#1D1D1F]/15 transition"
            >
              <SlidersHorizontal className="h-3 w-3" />
              2D Slices
            </button>
          )}
        </div>
      </div>

      {/* Bottom-left layer toggles */}
      {!effectiveHeatmap && (
        <div className="absolute bottom-3 left-3 flex flex-wrap items-center gap-1.5 rounded-2xl bg-white/85 px-2.5 py-1.5 shadow-sm backdrop-blur-md border border-black/8">
          <Layers className="h-3.5 w-3.5 text-[#6E6E73] mr-1" />
          {(
            [
              ["tibia_cortical", "Tibia", "#E8E2D5"],
              ["mineralised_callus", "Callus", "#F59E0B"],
              ["metal_hardware", "Implant", "#94A3B8"],
              ["fibula", "Fibula", "#D6D0C4"],
            ] as Array<[LayerKey, string, string]>
          ).map(([key, label, swatch]) => {
            const exists = Boolean(ctRun.assets[key]);
            if (!exists) return null;
            const active = layers[key];
            return (
              <button
                key={key}
                onClick={() => toggleLayer(key)}
                className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition ${
                  active
                    ? "bg-black/6 text-[#1D1D1F]"
                    : "text-[#86868B] opacity-60 hover:opacity-100"
                }`}
              >
                <span
                  className="h-2.5 w-2.5 rounded-full border border-black/15"
                  style={{ backgroundColor: swatch }}
                />
                {label}
                {active ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
              </button>
            );
          })}
        </div>
      )}

      {/* Heatmap scale legend */}
      {effectiveHeatmap && (
        <div className="absolute bottom-3 left-3 flex items-center gap-3 rounded-full bg-white/90 px-3.5 py-1.5 text-xs shadow-sm backdrop-blur-md border border-black/8">
          <span className="font-medium text-[#1D1D1F]">Cortical Thickness</span>
          <span className="tabular-nums text-[#6E6E73]">0.5 mm</span>
          <div
            className="h-2 w-28 rounded-full"
            style={{
              background: "linear-gradient(90deg, #FF453A 0%, #0A84FF 50%, #30D158 100%)",
            }}
          />
          <span className="tabular-nums text-[#6E6E73]">5.5 mm</span>
        </div>
      )}
    </div>
  );
}
