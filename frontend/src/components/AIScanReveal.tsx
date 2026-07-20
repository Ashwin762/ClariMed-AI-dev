// frontend/src/components/AIScanReveal.tsx
import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ScanLine, CheckCircle2 } from 'lucide-react';
import { guessBodyPartFromImage, type BodyPart, type BodyPartGuess } from '../api';

// Kept local rather than imported from Wizard.tsx to avoid a circular
// dependency — this is intentionally a self-contained, reusable component.
const LABELS: Record<string, { label: string; icon: string }> = {
  eye: { label: 'Eyes', icon: '👁' },
  skin: { label: 'Skin', icon: '✋' },
  nail: { label: 'Nails', icon: '💅' },
  oral: { label: 'Mouth', icon: '👄' },
  dental: { label: 'Teeth', icon: '🦷' },
  ent: { label: 'Ear / Nose / Throat', icon: '👂' },
  hair: { label: 'Hair / Scalp', icon: '💇' },
};
const ORDER = ['eye', 'skin', 'nail', 'oral', 'dental', 'ent', 'hair'];

type Phase = 'scanning' | 'revealed' | 'error';

interface Props {
  file: File;
  onResolved: (bodyPart: BodyPart | null, confidence: number | null) => void;
  onCancel?: () => void;
}

/**
 * The visual centerpiece of the "transparent AI" story: rather than a black
 * box that just announces one answer, this shows the actual confidence
 * distribution CLIP computes across every candidate body part, live. This
 * is real model output being made visible, not a decorative animation
 * layered on top of a hidden decision.
 */
export default function AIScanReveal({ file, onResolved, onCancel }: Props) {
  const [phase, setPhase] = useState<Phase>('scanning');
  const [result, setResult] = useState<BodyPartGuess | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    let cancelled = false;
    // Minimum scan duration so the reveal doesn't feel like a flicker even
    // on a fast connection — the scan animation is part of the story here,
    // not just a loading spinner to get rid of quickly.
    const minDelay = new Promise((r) => setTimeout(r, 1400));

    (async () => {
      try {
        const [apiResult] = await Promise.all([guessBodyPartFromImage(file), minDelay]);
        if (cancelled) return;
        setResult(apiResult);
        setPhase('revealed');
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'Could not analyze that photo.');
        setPhase('error');
      }
    })();

    return () => { cancelled = true; };
  }, [file]);

  const sortedScores = result?.all_scores
    ? ORDER
        .filter((bp) => bp in (result.all_scores as Record<string, number>))
        .map((bp) => ({ bp, score: (result.all_scores as Record<string, number>)[bp] }))
        .sort((a, b) => b.score - a.score)
    : [];

  const winner = result?.guessed_body_part ?? null;

  return (
    <div className="relative w-full max-w-md mx-auto">
      <div className="relative rounded-3xl border border-slate-800 bg-slate-900/60 overflow-hidden shadow-[0_40px_100px_-30px_rgba(16,185,129,0.25)] p-5">
        {/* Corner brackets — same reticle motif as the landing page scanner and SystemGrid */}
        {['top-3 left-3 border-t border-l', 'top-3 right-3 border-t border-r', 'bottom-3 left-3 border-b border-l', 'bottom-3 right-3 border-b border-r'].map((pos, i) => (
          <div key={i} className={`absolute w-5 h-5 border-emerald-500/50 pointer-events-none ${pos}`} />
        ))}

        <div className="flex items-center gap-2 mb-4 text-[10px] font-mono uppercase tracking-widest text-emerald-400">
          <ScanLine size={12} className={phase === 'scanning' ? 'animate-pulse' : ''} />
          {phase === 'scanning' ? 'Analyzing photo' : phase === 'revealed' ? 'Analysis complete' : 'Analysis unavailable'}
        </div>

        {/* Image preview with scanning sweep overlay */}
        <div className="relative w-full aspect-video rounded-xl overflow-hidden border border-slate-800 mb-5 bg-slate-950">
          {previewUrl && <img src={previewUrl} alt="Uploaded photo" className="w-full h-full object-cover" />}
          <AnimatePresence>
            {phase === 'scanning' && (
              <motion.div
                initial={{ top: '0%' }} animate={{ top: ['0%', '95%', '0%'] }}
                transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
                exit={{ opacity: 0 }}
                className="absolute left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-emerald-400 to-transparent shadow-[0_0_12px_2px_rgba(52,211,153,0.6)]"
              />
            )}
          </AnimatePresence>
          {phase === 'scanning' && <div className="absolute inset-0 bg-slate-950/20" />}
        </div>

        {/* Live confidence breakdown */}
        <AnimatePresence mode="wait">
          {phase === 'scanning' && (
            <motion.p key="scanning-label" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="text-xs text-slate-500 text-center py-2">
              Comparing your photo against every body area...
            </motion.p>
          )}

          {phase === 'revealed' && (
            <motion.div key="bars" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
              {sortedScores.map(({ bp, score }, i) => {
                const isWinner = bp === winner;
                // all_scores now comes back as 0-100 integers directly from the
                // vision LLM (see ai/vision/relevance_gate.py) -- no rescaling.
                const pct = Math.round(score);
                return (
                  <motion.div
                    key={bp}
                    initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.06 }}
                    className="flex items-center gap-2.5"
                  >
                    <span className="text-sm w-5 shrink-0">{LABELS[bp]?.icon}</span>
                    <span className={`text-xs w-16 shrink-0 truncate ${isWinner ? 'text-emerald-300 font-semibold' : 'text-slate-500'}`}>
                      {LABELS[bp]?.label}
                    </span>
                    <div className="flex-1 h-5 bg-slate-950 rounded-full overflow-hidden border border-slate-800/80 relative">
                      <motion.div
                        initial={{ width: '0%' }} animate={{ width: `${pct}%` }}
                        transition={{ duration: 0.7, delay: 0.2 + i * 0.06, ease: [0.16, 1, 0.3, 1] }}
                        className={`h-full rounded-full ${isWinner ? 'bg-gradient-to-r from-emerald-500 to-emerald-400' : 'bg-slate-700'}`}
                      />
                    </div>
                    <span className={`text-[11px] font-mono w-9 text-right shrink-0 ${isWinner ? 'text-emerald-300' : 'text-slate-600'}`}>
                      {pct}%
                    </span>
                    {isWinner && <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />}
                  </motion.div>
                );
              })}

              {!winner && (
                <p className="text-xs text-amber-400 pt-2 text-center">
                  No single area stood out clearly — please select it yourself on the next step.
                </p>
              )}

              <motion.button
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.9 }}
                onClick={() => onResolved(winner, result?.confidence ?? null)}
                className="w-full mt-3 bg-slate-100 hover:bg-white text-slate-950 font-medium py-2.5 rounded-xl text-sm transition-all active:scale-[0.98]"
              >
                {winner ? `Continue with ${LABELS[winner]?.label}` : 'Continue — select area myself'}
              </motion.button>
            </motion.div>
          )}

          {phase === 'error' && (
            <motion.div key="error" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center space-y-3 py-2">
              <p className="text-xs text-amber-400">{error}</p>
              <button
                onClick={() => onResolved(null, null)}
                className="w-full bg-slate-100 hover:bg-white text-slate-950 font-medium py-2.5 rounded-xl text-sm transition-all"
              >
                Continue — select area myself
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {onCancel && phase !== 'scanning' && (
          <button onClick={onCancel} className="w-full mt-2 text-[11px] text-slate-600 hover:text-slate-400">
            Try a different photo
          </button>
        )}
      </div>
    </div>
  );
}