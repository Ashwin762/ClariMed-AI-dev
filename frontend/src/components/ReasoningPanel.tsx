// frontend/src/components/ReasoningPanel.tsx
import React from 'react';
import { motion } from 'framer-motion';
import { Brain, Sparkles } from 'lucide-react';
import type { Candidate, Evidence } from '../api';

interface Props {
  top: Candidate;
  evidence: Evidence;
  rankingReliable: boolean;
}

/**
 * "Show its work": rather than presenting a single confident-looking result,
 * this visualizes the actual fusion math the engine computed — symptom
 * match, image match (when actually used), and how they combined. Every
 * number here is real backend output, not decoration. This is the second
 * half of the transparent-AI story alongside AIScanReveal: the model's
 * reasoning made visible, not a black box announcing an answer.
 */
export default function ReasoningPanel({ top, evidence, rankingReliable }: Props) {
  const symPct = Math.round(top.sym_score * 100);
  const imgPct = top.image_relevant && top.img_score != null ? Math.round(top.img_score * 100) : null;
  const combinedPct = Math.round(top.strength_raw * 100);

  return (
    <div className="p-4 bg-slate-900/50 border border-slate-800 rounded-xl space-y-4">
      <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-emerald-400">
        <Brain size={12} />
        How the AI got here
      </div>

      <div className="space-y-3">
        <ReasoningBar label="Symptom match" pct={symPct} delay={0} />
        {imgPct !== null ? (
          <ReasoningBar label="Photo match" pct={imgPct} delay={0.15} />
        ) : evidence.image_provided ? (
          <p className="text-[11px] text-slate-600 pl-1">Photo wasn't a relevant signal for this specific condition — text symptoms carried the match.</p>
        ) : null}

        <div className="pt-2 border-t border-slate-800/80">
          <ReasoningBar label="Combined confidence" pct={combinedPct} delay={0.3} emphasized />
        </div>
      </div>

      {top.matched_keywords.length > 0 && (
        <div>
          <p className="text-[10px] text-slate-500 mb-1.5">What actually matched:</p>
          <div className="flex flex-wrap gap-1.5">
            {top.matched_keywords.map((kw, i) => (
              <motion.span
                key={kw}
                initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.5 + i * 0.08 }}
                className="text-[10px] px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 flex items-center gap-1"
              >
                <Sparkles size={9} />
                {kw}
              </motion.span>
            ))}
          </div>
        </div>
      )}

      <p className="text-[10px] text-slate-600 leading-relaxed">
        {evidence.candidates_considered} condition{evidence.candidates_considered === 1 ? '' : 's'} evaluated
        {' · '}{evidence.matched_signals} signal{evidence.matched_signals === 1 ? '' : 's'} matched
        {!rankingReliable && ' · confidence still building — see note below'}
      </p>
    </div>
  );
}

function ReasoningBar({ label, pct, delay, emphasized }: { label: string; pct: number; delay: number; emphasized?: boolean }) {
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1">
        <span className={`text-xs ${emphasized ? 'text-slate-200 font-medium' : 'text-slate-400'}`}>{label}</span>
        <AnimatedNumber value={pct} delay={delay} emphasized={emphasized} />
      </div>
      <div className="h-2 bg-slate-950 rounded-full overflow-hidden border border-slate-800/60">
        <motion.div
          initial={{ width: '0%' }} animate={{ width: `${pct}%` }}
          transition={{ duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] }}
          className={`h-full rounded-full ${emphasized ? 'bg-gradient-to-r from-emerald-500 to-emerald-400' : 'bg-slate-600'}`}
        />
      </div>
    </div>
  );
}

function AnimatedNumber({ value, delay, emphasized }: { value: number; delay: number; emphasized?: boolean }) {
  const [display, setDisplay] = React.useState(0);
  React.useEffect(() => {
    const timeout = setTimeout(() => {
      const start = performance.now();
      const duration = 800;
      const tick = (now: number) => {
        const t = Math.min(1, (now - start) / duration);
        setDisplay(Math.round(value * t));
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }, delay * 1000);
    return () => clearTimeout(timeout);
  }, [value, delay]);
  return (
    <span className={`text-xs font-mono ${emphasized ? 'text-emerald-300' : 'text-slate-500'}`}>{display}%</span>
  );
}