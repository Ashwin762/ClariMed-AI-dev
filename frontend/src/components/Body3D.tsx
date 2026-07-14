// frontend/src/components/Body3D.tsx
import React, { useState, Suspense, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls as OrbitControlsImpl } from 'three/examples/jsm/controls/OrbitControls.js';
import { Canvas, useThree, useFrame, extend } from '@react-three/fiber';
import { motion, AnimatePresence } from 'framer-motion';
import type { BodyPart } from '../api';

// Registers three.js's OrbitControls as a usable JSX element (<orbitControls>).
// This is the standard way to use OrbitControls with react-three-fiber
// WITHOUT @react-three/drei — used here because drei's current release still
// declares a peer dependency on react-three/fiber@8, not @9, so npm refuses
// to install it alongside React 19. three.js itself has no React version
// dependency at all, so this path has no such conflict.
extend({ OrbitControlsImpl });

declare module '@react-three/fiber' {
  interface ThreeElements {
    orbitControlsImpl: any;
  }
}

type Region = 'head' | 'torso' | 'leftArm' | 'rightArm' | 'leftHand' | 'rightHand' | 'leftLeg' | 'rightLeg';

// Identical mapping to BodyDiagram.tsx (2D version) — same interaction logic
// proven there, only the rendering layer changes here.
const REGION_MAP: Record<Region, BodyPart[]> = {
  head: ['eye', 'oral', 'dental', 'ent', 'hair', 'neurological'],
  torso: ['respiratory', 'digestive', 'urinary', 'reproductive'],
  leftArm: ['musculoskeletal'],
  rightArm: ['musculoskeletal'],
  leftHand: ['nail', 'musculoskeletal'],
  rightHand: ['nail', 'musculoskeletal'],
  leftLeg: ['musculoskeletal'],
  rightLeg: ['musculoskeletal'],
};

const REGION_LABELS: Record<Region, string> = {
  head: 'Head / Face', torso: 'Chest / Abdomen', leftArm: 'Arm', rightArm: 'Arm',
  leftHand: 'Hand', rightHand: 'Hand', leftLeg: 'Leg', rightLeg: 'Leg',
};

const BASE_COLOR = '#475569';   // slate-600, unselected
const HOVER_COLOR = '#10b981';  // emerald-500, hover
const SELECT_COLOR = '#34d399'; // emerald-400, selected

// Approximate world-space focus point for each region (accounts for the
// Figure group's [0,-1,0] offset), used to gently zoom the camera toward
// whatever the user clicks — completing the hover -> glow -> click -> zoom
// sequence.
const REGION_FOCUS: Record<Region, [number, number, number]> = {
  head: [0, 1.55, 0.3],
  torso: [0, -0.1, 0.4],
  leftArm: [-1.0, 0.1, 0.3],
  rightArm: [1.0, 0.1, 0.3],
  leftHand: [-1.5, -0.65, 0.3],
  rightHand: [1.5, -0.65, 0.3],
  leftLeg: [-0.35, -1.5, 0.3],
  rightLeg: [0.35, -1.5, 0.3],
};

const DEFAULT_TARGET: [number, number, number] = [0, 0, 0];
const DEFAULT_DISTANCE = 5.5;
const ZOOMED_DISTANCE = 3.8;

/** Smoothly animates the camera toward a focus point on click, and back to
 * the default framing when nothing is focused. Runs every frame via a plain
 * lerp — simple and predictable rather than a dedicated animation library,
 * since this can't be visually tested here before shipping. */
function CameraRig({ focusRegion }: { focusRegion: Region | null }) {
  const { camera, gl } = useThree();
  const controlsRef = useRef<OrbitControlsImpl>(null!);
  const targetVec = useRef(new THREE.Vector3(...DEFAULT_TARGET));

  useFrame(() => {
    const controls = controlsRef.current;
    if (!controls) return;

    const wantTarget = focusRegion ? REGION_FOCUS[focusRegion] : DEFAULT_TARGET;
    const wantDistance = focusRegion ? ZOOMED_DISTANCE : DEFAULT_DISTANCE;

    targetVec.current.lerp(new THREE.Vector3(...wantTarget), 0.08);
    controls.target.copy(targetVec.current);

    const dir = new THREE.Vector3().subVectors(camera.position, controls.target).normalize();
    const currentDistance = camera.position.distanceTo(controls.target);
    const nextDistance = currentDistance + (wantDistance - currentDistance) * 0.08;
    camera.position.copy(controls.target).add(dir.multiplyScalar(nextDistance));

    controls.update();
  });

  return (
    <orbitControlsImpl
      ref={controlsRef}
      args={[camera, gl.domElement]}
      enablePan={false}
      minDistance={3.2}
      maxDistance={8}
      autoRotate={!focusRegion}
      autoRotateSpeed={1.2}
      maxPolarAngle={Math.PI / 1.7}
      minPolarAngle={Math.PI / 4}
    />
  );
}

interface RegionGroupProps {
  region: Region;
  isSelected: boolean;
  isHovered: boolean;
  onHover: (r: Region | null) => void;
  onClick: (r: Region) => void;
  children: (color: string) => React.ReactNode;
}

/** Wraps a group of meshes for one region with shared hover/click behavior.
 * Color is computed here and passed explicitly into each material via a
 * render-prop function — NOT via cloneElement, which can't reach materials
 * nested inside <mesh> children (a real bug caught before shipping: cloning
 * only touches the direct <mesh> element, never the <meshStandardMaterial>
 * nested one level inside it, so the color injection silently did nothing). */
function RegionGroup({ region, isSelected, isHovered, onHover, onClick, children }: RegionGroupProps) {
  const color = isSelected ? SELECT_COLOR : isHovered ? HOVER_COLOR : BASE_COLOR;
  return (
    <group
      onPointerOver={(e) => { e.stopPropagation(); onHover(region); document.body.style.cursor = 'pointer'; }}
      onPointerOut={(e) => { e.stopPropagation(); onHover(null); document.body.style.cursor = 'auto'; }}
      onClick={(e) => { e.stopPropagation(); onClick(region); }}
    >
      {children(color)}
    </group>
  );
}

function Figure({
  selected, hovered, setHovered, handleClick,
}: {
  selected: BodyPart | null; hovered: Region | null;
  setHovered: (r: Region | null) => void; handleClick: (r: Region) => void;
}) {
  const isRegionSelected = (region: Region) => selected != null && REGION_MAP[region].includes(selected);

  const groupProps = (region: Region) => ({
    region, isSelected: isRegionSelected(region), isHovered: hovered === region,
    onHover: setHovered, onClick: handleClick,
  });

  return (
    <group position={[0, -1, 0]}>
      {/* head + neck */}
      <RegionGroup {...groupProps('head')}>
        {(color) => (
          <>
            <mesh position={[0, 2.55, 0]}>
              <sphereGeometry args={[0.55, 24, 24]} />
              <meshStandardMaterial color={color} />
            </mesh>
            <mesh position={[0, 2.1, 0]}>
              <cylinderGeometry args={[0.2, 0.24, 0.3, 16]} />
              <meshStandardMaterial color={color} />
            </mesh>
          </>
        )}
      </RegionGroup>

      {/* torso: upper (chest/shoulders -> waist) + lower (pelvis) */}
      <RegionGroup {...groupProps('torso')}>
        {(color) => (
          <>
            <mesh position={[0, 1.35, 0]}>
              <cylinderGeometry args={[0.95, 0.6, 1.3, 20]} />
              <meshStandardMaterial color={color} />
            </mesh>
            <mesh position={[0, 0.45, 0]}>
              <cylinderGeometry args={[0.6, 0.72, 0.5, 20]} />
              <meshStandardMaterial color={color} />
            </mesh>
          </>
        )}
      </RegionGroup>

      {/* left arm + hand */}
      <RegionGroup {...groupProps('leftArm')}>
        {(color) => (
          <mesh position={[-1.15, 1.2, 0]} rotation={[0, 0, 0.36]}>
            <cylinderGeometry args={[0.2, 0.13, 1.65, 16]} />
            <meshStandardMaterial color={color} />
          </mesh>
        )}
      </RegionGroup>
      <RegionGroup {...groupProps('leftHand')}>
        {(color) => (
          <mesh position={[-1.5, 0.35, 0]}>
            <sphereGeometry args={[0.16, 16, 16]} />
            <meshStandardMaterial color={color} />
          </mesh>
        )}
      </RegionGroup>

      {/* right arm + hand */}
      <RegionGroup {...groupProps('rightArm')}>
        {(color) => (
          <mesh position={[1.15, 1.2, 0]} rotation={[0, 0, -0.36]}>
            <cylinderGeometry args={[0.2, 0.13, 1.65, 16]} />
            <meshStandardMaterial color={color} />
          </mesh>
        )}
      </RegionGroup>
      <RegionGroup {...groupProps('rightHand')}>
        {(color) => (
          <mesh position={[1.5, 0.35, 0]}>
            <sphereGeometry args={[0.16, 16, 16]} />
            <meshStandardMaterial color={color} />
          </mesh>
        )}
      </RegionGroup>

      {/* left leg + foot */}
      <RegionGroup {...groupProps('leftLeg')}>
        {(color) => (
          <>
            <mesh position={[-0.32, -0.7, 0]} rotation={[0, 0, 0.08]}>
              <cylinderGeometry args={[0.27, 0.16, 1.7, 16]} />
              <meshStandardMaterial color={color} />
            </mesh>
            <mesh position={[-0.42, -1.62, 0.12]}>
              <sphereGeometry args={[0.19, 12, 12]} />
              <meshStandardMaterial color={color} />
            </mesh>
          </>
        )}
      </RegionGroup>

      {/* right leg + foot */}
      <RegionGroup {...groupProps('rightLeg')}>
        {(color) => (
          <>
            <mesh position={[0.32, -0.7, 0]} rotation={[0, 0, -0.08]}>
              <cylinderGeometry args={[0.27, 0.16, 1.7, 16]} />
              <meshStandardMaterial color={color} />
            </mesh>
            <mesh position={[0.42, -1.62, 0.12]}>
              <sphereGeometry args={[0.19, 12, 12]} />
              <meshStandardMaterial color={color} />
            </mesh>
          </>
        )}
      </RegionGroup>
    </group>
  );
}

interface Props {
  onSelect: (bp: BodyPart) => void;
  bodyPartLabels: Record<BodyPart, string>;
  selected: BodyPart | null;
}

export default function Body3D({ onSelect, bodyPartLabels, selected }: Props) {
  const [hovered, setHovered] = useState<Region | null>(null);
  const [active, setActive] = useState<Region | null>(null);

  const handleRegionClick = (region: Region) => {
    const options = REGION_MAP[region];
    if (options.length === 1) {
      onSelect(options[0]);
      setActive(null);
    } else {
      setActive(region);
    }
  };

  return (
    <div className="flex flex-col items-center">
      <div className="w-full h-[320px] rounded-xl border border-slate-800 bg-slate-950/60 overflow-hidden">
        <Canvas camera={{ position: [0, 0.3, 5.5], fov: 42 }}>
          <ambientLight intensity={0.7} />
          <directionalLight position={[3, 5, 4]} intensity={1.1} />
          <directionalLight position={[-3, 2, -2]} intensity={0.3} />
          <Suspense fallback={null}>
            <Figure selected={selected} hovered={hovered} setHovered={setHovered} handleClick={handleRegionClick} />
          </Suspense>
          <CameraRig focusRegion={active} />
        </Canvas>
      </div>

      <p className="text-[11px] text-slate-500 mt-2">
        {hovered ? REGION_LABELS[hovered] : 'Drag to rotate — tap a region to select where it hurts'}
      </p>

      <AnimatePresence>
        {active && (
          <motion.div
            initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
            className="w-full mt-3 p-3 bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden"
          >
            <p className="text-xs text-slate-400 mb-2">Which of these matches best?</p>
            <div className="flex flex-wrap gap-2">
              {REGION_MAP[active].map((bp) => (
                <button
                  key={bp}
                  onClick={() => { onSelect(bp); setActive(null); }}
                  className="px-3 py-1.5 text-xs rounded-lg border bg-slate-900 text-slate-300 border-slate-700 hover:border-emerald-500 hover:text-emerald-300 transition-colors"
                >
                  {bodyPartLabels[bp]}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}