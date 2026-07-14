// frontend/src/components/SystemGrid.tsx
//
// Body-area selector styled as a glassmorphic card grid with an ambient
// "scanner" motif. The user picks the area of the body their symptom relates
// to directly (Eyes, Skin, ...) — no body coordinates needed. A soft
// concentric-ring scan runs behind the grid, each card has subtle corner
// accents and a gentle ping on hover, and selecting one draws a soft glowing
// line down to a short description panel. The look is calm-futuristic, not
// a military HUD: wording stays plain and human throughout.
import React, { useLayoutEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import type { BodyPart } from '../api';

interface PartMeta {
  label: string;
  icon: React.ReactNode;
  desc: string;
}

interface Props {
  parts: BodyPart[];
  meta: Record<BodyPart, PartMeta>;
  selected: BodyPart | null;
  onSelect: (bp: BodyPart) => void;
}

/** Four small corner brackets — the soft corner-accent look. Pure CSS,
 * absolutely positioned inside a `relative` parent. */
function ReticleCorners({ active }: { active: boolean }) {
  const base = 'absolute w-2.5 h-2.5 border-emerald-400/0 transition-colors duration-300';
  const activeColor = active ? 'border-emerald-400/80' : 'group-hover:border-slate-500';
  return (
    <>
      <span className={`${base} ${activeColor} top-1.5 left-1.5 border-t border-l`} />
      <span className={`${base} ${activeColor} top-1.5 right-1.5 border-t border-r`} />
      <span className={`${base} ${activeColor} bottom-1.5 left-1.5 border-b border-l`} />
      <span className={`${base} ${activeColor} bottom-1.5 right-1.5 border-b border-r`} />
    </>
  );
}

export default function SystemGrid({ parts, meta, selected, onSelect }: Props) {
  const [hovered, setHovered] = useState<BodyPart | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<Partial<Record<BodyPart, HTMLButtonElement | null>>>({});
  const [beam, setBeam] = useState<{ x: number; y1: number; y2: number } | null>(null);

  // Recompute the connector line's geometry whenever the selection changes
  // (or the layout shifts, e.g. window resize) — measures the real DOM
  // positions rather than guessing at a fixed grid layout, so it stays
  // correct across 1/2/3-column responsive breakpoints.
  useLayoutEffect(() => {
    function recompute() {
      if (!selected || !wrapperRef.current || !panelRef.current) { setBeam(null); return; }
      const card = cardRefs.current[selected];
      if (!card) { setBeam(null); return; }
      const wrapRect = wrapperRef.current.getBoundingClientRect();
      const cardRect = card.getBoundingClientRect();
      const panelRect = panelRef.current.getBoundingClientRect();
      setBeam({
        x: cardRect.left + cardRect.width / 2 - wrapRect.left,
        y1: cardRect.bottom - wrapRect.top,
        y2: panelRect.top - wrapRect.top,
      });
    }
    recompute();
    window.addEventListener('resize', recompute);
    return () => window.removeEventListener('resize', recompute);
  }, [selected, parts.length]);

  const selectedMeta = selected ? meta[selected] : null;

  return (
    <div ref={wrapperRef} className="relative">
      {/* Soft scanner backdrop — concentric rings + a slow rotating sweep,
          kept low-opacity so it reads as ambient texture, not noise. */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden rounded-2xl">
        <div className="relative w-[140%] aspect-square opacity-[0.07]">
          <div className="absolute inset-0 rounded-full border border-emerald-400" />
          <div className="absolute inset-[15%] rounded-full border border-emerald-400" />
          <div className="absolute inset-[30%] rounded-full border border-emerald-400" />
          <div className="absolute inset-[45%] rounded-full border border-emerald-400" />
          <div
            className="absolute inset-0 rounded-full animate-[radar-spin_9s_linear_infinite]"
            style={{
              background: 'conic-gradient(from 0deg, transparent 0deg, transparent 300deg, rgba(52,211,153,0.9) 360deg)',
            }}
          />
        </div>
      </div>

      <div className="relative grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {parts.map((bp) => {
          const m = meta[bp];
          if (!m) return null;
          const isSelected = selected === bp;
          const isHovered = hovered === bp;
          return (
            <button
              key={bp}
              ref={(el) => { cardRefs.current[bp] = el; }}
              onMouseEnter={() => setHovered(bp)}
              onMouseLeave={() => setHovered(null)}
              onClick={() => onSelect(bp)}
              className={`group relative overflow-hidden p-4 rounded-xl border text-left backdrop-blur-md transition-all duration-300 ${
                isSelected
                  ? 'bg-emerald-500/10 border-emerald-500/70 shadow-[0_0_25px_-6px_rgba(16,185,129,0.55)]'
                  : 'bg-slate-900/40 border-slate-800/80 hover:border-slate-600 hover:bg-slate-900/60'
              }`}
            >
              <ReticleCorners active={isSelected} />

              <div className="flex items-center gap-3">
                <span className="relative flex items-center justify-center w-10 h-10 rounded-full border border-slate-700/70 bg-slate-950/60 shrink-0">
                  {isHovered && !isSelected && (
                    <span className="absolute inset-0 rounded-full border border-emerald-400/60 animate-ping" />
                  )}
                  {isSelected && (
                    <span className="absolute inset-0 rounded-full border border-emerald-400/50" style={{ animation: 'reticle-blink 2s ease-in-out infinite' }} />
                  )}
                  <span className={isSelected ? 'text-emerald-400' : 'text-slate-400 group-hover:text-slate-200'}>
                    {m.icon}
                  </span>
                </span>
                <div className="min-w-0">
                  <p className={`text-[10px] font-mono uppercase tracking-wider ${isSelected ? 'text-emerald-400' : 'text-slate-600'}`}>
                    {isSelected ? 'Selected' : 'Body area'}
                  </p>
                  <h3 className={`font-semibold text-sm truncate ${isSelected ? 'text-emerald-300' : 'text-slate-200'}`}>
                    {m.label}
                  </h3>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Soft glowing line connecting the selected card down to the panel below.
          Positioned absolutely against `wrapperRef`, geometry measured live. */}
      {beam && beam.y2 > beam.y1 && (
        <div
          className="pointer-events-none absolute w-px"
          style={{ left: beam.x, top: beam.y1, height: beam.y2 - beam.y1 }}
        >
          <div className="w-full h-full bg-gradient-to-b from-emerald-400/70 via-emerald-400/25 to-emerald-400/70" />
          <div
            className="absolute left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-emerald-300 shadow-[0_0_8px_2px_rgba(52,211,153,0.8)]"
            style={{ animation: 'pulse-travel 1.4s ease-in-out infinite' }}
          />
        </div>
      )}

      <div ref={panelRef} className="relative mt-3">
        <AnimatePresence mode="wait">
          {selectedMeta && (
            <motion.div
              key={selected}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/[0.04] flex items-start gap-3">
                <Sparkles className="text-emerald-400 shrink-0 mt-0.5" size={16} />
                <div>
                  <p className="text-xs font-mono uppercase tracking-wider text-emerald-400">{selectedMeta.label}</p>
                  <p className="text-xs text-slate-400 mt-1">{selectedMeta.desc}</p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}