// frontend/src/components/BodyDiagram.tsx
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { BodyPart } from '../api';

type Region = 'head' | 'torso' | 'leftArm' | 'rightArm' | 'leftHand' | 'rightHand' | 'leftLeg' | 'rightLeg';

// Which body parts a click on each region could mean. Regions mapping to
// more than one body part show a chip picker; single-mapping regions select
// immediately. The torso is drawn as one continuous silhouette shape (for
// realism) rather than subdivided chest/abdomen/pelvis zones, so a tap
// anywhere on it offers all torso-related choices.
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

interface Props {
  onSelect: (bp: BodyPart) => void;
  bodyPartLabels: Record<BodyPart, string>;
  selected: BodyPart | null;
}

export default function BodyDiagram({ onSelect, bodyPartLabels, selected }: Props) {
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

  const isRegionSelected = (region: Region) => selected != null && REGION_MAP[region].includes(selected);

  const fill = (region: Region) => {
    if (isRegionSelected(region)) return 'rgba(52,211,153,0.32)';
    if (hovered === region || active === region) return 'rgba(52,211,153,0.20)';
    return 'rgba(148,163,184,0.14)';
  };
  const stroke = (region: Region) =>
    isRegionSelected(region) || hovered === region || active === region ? '#34d399' : '#475569';

  const regionProps = (region: Region) => ({
    fill: fill(region),
    stroke: stroke(region),
    strokeWidth: 2,
    style: { cursor: 'pointer', transition: 'fill 0.15s, stroke 0.15s' },
    onMouseEnter: () => setHovered(region),
    onMouseLeave: () => setHovered(null),
    onClick: () => handleRegionClick(region),
  });

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 240 500" className="w-full max-w-[220px] h-auto" aria-label="Clickable body diagram">
        {/* left leg */}
        <path
          d="M90,315 C82,340 78,368 78,395 C78,415 80,432 84,448 C86,456 90,462 96,462
             C101,462 104,456 104,448 C103,425 102,400 103,375 C104,355 106,335 110,318 Z"
          {...regionProps('leftLeg')}
        />
        {/* right leg */}
        <path
          d="M150,315 C158,340 162,368 162,395 C162,415 160,432 156,448 C154,456 150,462 144,462
             C139,462 136,456 136,448 C137,425 138,400 137,375 C136,355 134,335 130,318 Z"
          {...regionProps('rightLeg')}
        />
        {/* feet (part of leg region) */}
        <ellipse cx="92" cy="472" rx="17" ry="9" {...regionProps('leftLeg')} />
        <ellipse cx="148" cy="472" rx="17" ry="9" {...regionProps('rightLeg')} />

        {/* left arm */}
        <path
          d="M78,118 C60,124 48,140 42,165 C37,188 36,212 38,235 C39,248 42,258 47,266
             C50,270 55,271 58,266 C60,260 59,250 57,238 C55,215 55,192 59,170 C62,152 68,138 80,128 Z"
          {...regionProps('leftArm')}
        />
        {/* right arm */}
        <path
          d="M162,118 C180,124 192,140 198,165 C203,188 204,212 202,235 C201,248 198,258 193,266
             C190,270 185,271 182,266 C180,260 181,250 183,238 C185,215 185,192 181,170 C178,152 172,138 160,128 Z"
          {...regionProps('rightArm')}
        />
        {/* hands */}
        <ellipse cx="45" cy="278" rx="13" ry="16" {...regionProps('leftHand')} />
        <ellipse cx="195" cy="278" rx="13" ry="16" {...regionProps('rightHand')} />

        {/* torso: one continuous tapered silhouette (shoulders -> waist -> hips) */}
        <path
          d="M90,112 C75,118 68,135 66,160 C64,185 66,210 70,230 C66,250 64,268 66,285
             C68,300 74,312 85,318 L155,318 C166,312 172,300 174,285 C176,268 174,250 170,230
             C174,210 176,185 174,160 C172,135 165,118 150,112 C138,108 128,106 120,106
             C112,106 102,108 90,112 Z"
          {...regionProps('torso')}
        />

        {/* neck (visual only, part of head region) */}
        <rect x="108" y="98" width="24" height="18" rx="6" {...regionProps('head')} />

        {/* head */}
        <path
          d="M120,20 C140,20 154,34 156,55 C158,72 154,86 145,96 C138,103 130,106 120,106
             C110,106 102,103 95,96 C86,86 82,72 84,55 C86,34 100,20 120,20 Z"
          {...regionProps('head')}
        />
      </svg>

      <p className="text-[11px] text-slate-500 mt-2">
        {hovered ? REGION_LABELS[hovered] : 'Tap a region to select where it hurts'}
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