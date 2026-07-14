import React, { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence, useScroll } from 'framer-motion';
import {
  Activity, Eye, Hand, Sparkles, Smile, ScanLine, Layers,
  BookOpen, MapPinned, Wifi, WifiOff, ShieldCheck, ArrowDown, Lock, EyeOff, FileX,
  Brain,
} from 'lucide-react';
import Logo from './Logo';

const EASE = [0.16, 1, 0.3, 1] as const; // premium "expo-out" easing throughout

/* ---------- Signature element: a live, looping mini-scanner ---------- */
function LiveScannerDemo() {
  const [pct, setPct] = useState(0);

  useEffect(() => {
    const cycleMs = 2600;
    const start = Date.now();
    const iv = setInterval(() => {
      const elapsed = (Date.now() - start) % cycleMs;
      const t = elapsed / cycleMs;
      const val = t < 0.35 ? 0 : t < 0.85 ? Math.round(((t - 0.35) / 0.5) * 92) : 92;
      setPct(val);
    }, 60);
    return () => clearInterval(iv);
  }, []);

  return (
    <div className="relative w-full max-w-sm mx-auto">
      <div className="relative aspect-square rounded-[2.5rem] border border-slate-800 bg-slate-900/60 overflow-hidden shadow-[0_60px_120px_-30px_rgba(16,185,129,0.25)]">
        {['top-4 left-4 border-t border-l', 'top-4 right-4 border-t border-r', 'bottom-4 left-4 border-b border-l', 'bottom-4 right-4 border-b border-r'].map((pos, i) => (
          <div key={i} className={`absolute w-6 h-6 border-emerald-500/50 ${pos}`} />
        ))}
        <svg viewBox="0 0 240 200" className="absolute inset-0 w-full h-full p-10">
          <path d="M20,100 Q120,30 220,100 Q120,170 20,100 Z" fill="none" stroke="#334155" strokeWidth="2" />
          <circle cx="120" cy="100" r="34" fill="none" stroke="#334155" strokeWidth="2" />
          <circle cx="120" cy="100" r="14" fill="#1e293b" />
          <motion.circle cx="86" cy="76" r="4" fill="#34d399"
            animate={{ opacity: [0, 0, 1, 1, 0], scale: [0.5, 0.5, 1, 1, 0.5] }}
            transition={{ duration: 2.6, times: [0, 0.32, 0.4, 0.85, 1], repeat: Infinity }} />
          <motion.circle cx="150" cy="118" r="4" fill="#34d399"
            animate={{ opacity: [0, 0, 1, 1, 0], scale: [0.5, 0.5, 1, 1, 0.5] }}
            transition={{ duration: 2.6, times: [0, 0.45, 0.53, 0.85, 1], repeat: Infinity }} />
          <motion.circle cx="120" cy="140" r="4" fill="#f0b429"
            animate={{ opacity: [0, 0, 1, 1, 0], scale: [0.5, 0.5, 1, 1, 0.5] }}
            transition={{ duration: 2.6, times: [0, 0.58, 0.66, 0.85, 1], repeat: Infinity }} />
        </svg>
        <motion.div
          className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-emerald-400 to-transparent shadow-[0_0_16px_3px_rgba(52,211,153,0.6)]"
          animate={{ top: ['8%', '92%', '8%'] }}
          transition={{ duration: 2.6, repeat: Infinity, ease: 'linear' }}
        />
      </div>
      <div className="flex items-center justify-between mt-4 px-2">
        <span className="text-[11px] font-mono uppercase tracking-wider text-slate-500">Live analysis (sample)</span>
        <span className="text-base font-mono text-emerald-400">{pct}%</span>
      </div>
    </div>
  );
}

function Reveal({ children, delay = 0, x = 0 }: { children: React.ReactNode; delay?: number; x?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 32, x }}
      whileInView={{ opacity: 1, y: 0, x: 0 }}
      viewport={{ once: true, margin: '-100px' }}
      transition={{ duration: 0.9, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

const PIPELINE = [
  { icon: <ScanLine size={40} />, title: 'Capture', desc: 'Select the affected area, note your symptoms, and optionally add a photo. Everything is processed on the server — nothing goes to a third party.' },
  { icon: <Layers size={40} />, title: 'Analyze', desc: 'A fusion engine reads real pixel signals from your photo and combines them with your symptoms into a scored, ranked result — not a black box.' },
  { icon: <BookOpen size={40} />, title: 'Explain', desc: 'Every result comes with a visual attention map and a plain list of exactly which symptoms and image findings drove the outcome.' },
  { icon: <ShieldCheck size={40} />, title: 'Guide', desc: 'Guidance is pulled from a curated knowledge base you can read yourself — precautions, home care, and clear signs to seek help.' },
  { icon: <MapPinned size={40} />, title: 'Connect', desc: 'Get matched with the right kind of specialist, save the result to your history, and download a PDF report to bring to your appointment.' },
];

/* ---------- Apple-style pinned scroll section ---------- */
function PinnedPipeline() {
  const ref = useRef<HTMLDivElement>(null);
  const stepCount = PIPELINE.length;
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] });
  const [active, setActive] = useState(0);

  // Subscribe directly to scrollYProgress. The earlier version derived a
  // MotionValue via useTransform and listened to that, which never fired —
  // leaving `active` pinned at 0 (only "Capture" ever showed).
  useEffect(() => {
    const unsub = scrollYProgress.on('change', (v) => {
      // Clamp to the last step slightly before the very end so the final
      // step is readable before the section scrolls away.
      const idx = Math.min(stepCount - 1, Math.max(0, Math.floor(v * stepCount * 0.999)));
      setActive((prev) => (prev === idx ? prev : idx));
    });
    return () => unsub();
  }, [scrollYProgress, stepCount]);

  return (
    <div ref={ref} style={{ height: `${stepCount * 90}vh` }} className="relative">
      <div className="sticky top-0 h-screen flex items-center overflow-hidden px-6">
        <div className="max-w-6xl mx-auto w-full grid grid-cols-1 lg:grid-cols-2 gap-20 items-center">
          <div className="relative aspect-square max-w-md mx-auto w-full">
            <div className="absolute inset-0 rounded-[3rem] border border-slate-800 bg-slate-900/40 flex items-center justify-center overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(16,185,129,0.12),transparent_60%)]" />
              <AnimatePresence mode="wait">
                <motion.div
                  key={active}
                  initial={{ opacity: 0, scale: 0.85, rotate: -4 }}
                  animate={{ opacity: 1, scale: 1, rotate: 0 }}
                  exit={{ opacity: 0, scale: 0.85, rotate: 4 }}
                  transition={{ duration: 0.5, ease: EASE }}
                  className="text-emerald-400 w-28 h-28 rounded-3xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center"
                >
                  {PIPELINE[active].icon}
                </motion.div>
              </AnimatePresence>
            </div>
            <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 text-[11px] font-mono text-slate-600 tracking-widest">
              STEP {active + 1} / {stepCount}
            </div>
          </div>

          <div className="space-y-3">
            {PIPELINE.map((step, i) => (
              <div
                key={step.title}
                className={`flex items-start gap-4 py-3 transition-all duration-500 ${i === active ? 'opacity-100' : 'opacity-25'}`}
              >
                <span className={`text-xs font-mono mt-1.5 shrink-0 ${i === active ? 'text-emerald-400' : 'text-slate-700'}`}>0{i + 1}</span>
                <div>
                  <h3 className={`font-display text-2xl md:text-3xl font-semibold tracking-tight transition-colors duration-500 ${i === active ? 'text-white' : 'text-slate-600'}`}>
                    {step.title}
                  </h3>
                  {i === active && (
                    <motion.p
                      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 }}
                      className="text-slate-400 text-base leading-relaxed mt-2 max-w-md"
                    >
                      {step.desc}
                    </motion.p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const COVERAGE = [
  { icon: <Eye size={24} />, label: 'Eye', count: 7 },
  { icon: <Hand size={24} />, label: 'Skin', count: 7 },
  { icon: <Sparkles size={24} />, label: 'Nail', count: 4 },
  { icon: <Smile size={24} />, label: 'Oral', count: 4 },
  { icon: <Activity size={24} />, label: 'General', count: 4 },
];

const PRIVACY_POINTS = [
  { icon: <EyeOff size={28} />, title: 'Your photo is never stored.', desc: 'Analyzed in memory, then discarded. Never written to disk. Never sent anywhere else.' },
  { icon: <Lock size={28} />, title: 'Nothing runs without your consent.', desc: 'A timestamped, versioned consent record is required before any screening begins.' },
  { icon: <FileX size={28} />, title: 'Delete everything, anytime.', desc: 'One request permanently erases every screening, appointment, and consent record tied to you.' },
];

export default function Hero({ onStart }: { onStart: () => void }) {
  return (
    <div className="bg-slate-950 text-slate-50 min-h-screen font-sans selection:bg-emerald-500/30">
      {/* Ambient drifting color — the "something behind the glass" that makes
          backdrop-blur read as genuine frosted glass rather than a flat tint.
          Slow, soft, continuous drift (Apple dynamic-wallpaper style), fixed
          so it sits behind the whole page rather than just the hero section. */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
        <motion.div
          className="absolute w-[500px] h-[500px] rounded-full"
          style={{ background: 'radial-gradient(circle, rgba(16,185,129,0.55), transparent 65%)', filter: 'blur(25px)' }}
          animate={{ x: [-80, 60, -80], y: [-60, 40, -60] }}
          transition={{ duration: 22, repeat: Infinity, ease: 'easeInOut' }}
          initial={{ top: '-10%', left: '-5%' }}
        />
        <motion.div
          className="absolute w-[420px] h-[420px] rounded-full"
          style={{ background: 'radial-gradient(circle, rgba(5,150,105,0.50), transparent 65%)', filter: 'blur(25px)' }}
          animate={{ x: [40, -60, 40], y: [30, -30, 30] }}
          transition={{ duration: 26, repeat: Infinity, ease: 'easeInOut' }}
          initial={{ bottom: '-10%', right: '0%' }}
        />
        <motion.div
          className="absolute w-[380px] h-[380px] rounded-full"
          style={{ background: 'radial-gradient(circle, rgba(52,211,153,0.40), transparent 65%)', filter: 'blur(25px)' }}
          animate={{ x: [-40, 50, -40], y: [50, -20, 50] }}
          transition={{ duration: 30, repeat: Infinity, ease: 'easeInOut' }}
          initial={{ top: '35%', left: '55%' }}
        />
      </div>

      <nav className="fixed top-0 left-0 right-0 z-50 backdrop-blur-xl backdrop-saturate-150 bg-slate-950/40 border-b border-white/[0.08] px-6 py-4 flex justify-between items-center">
        <div className="flex items-center gap-2.5">
          <Logo size={32} />
          <span className="font-display font-bold text-xl tracking-tight text-white">
            ClariMed<span className="text-emerald-400">.AI</span>
          </span>
        </div>
        <span className="text-[11px] backdrop-blur-lg backdrop-saturate-150 bg-white/[0.10] text-emerald-300 border border-white/[0.20] px-2.5 py-1 rounded-full font-mono shadow-lg shadow-black/20" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.15), 0 4px 16px rgba(0,0,0,0.2)' }}>
          109 conditions · 14 body parts
        </span>
      </nav>

      {/* Hero — huge, confident, minimal */}
      <section className="min-h-screen flex flex-col items-center justify-center px-6 pt-20 relative overflow-hidden text-center">
        <motion.div
          initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 1, ease: EASE }}
          className="z-10 max-w-4xl"
        >
          <span className="text-emerald-300 text-xs font-mono tracking-widest uppercase backdrop-blur-lg backdrop-saturate-150 border border-white/[0.20] bg-white/[0.10] px-3 py-1 rounded-full shadow-lg shadow-black/20" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.15), 0 4px 16px rgba(0,0,0,0.2)' }}>
            Connected care, resilient anywhere
          </span>
          <h1 className="font-display text-6xl sm:text-7xl lg:text-8xl font-semibold tracking-tight mt-8 mb-8 leading-[1.02]">
            See what your
            <br />
            symptoms <span className="text-emerald-400">can tell you.</span>
          </h1>
          <p className="text-slate-400 text-xl max-w-2xl mx-auto mb-10 leading-relaxed">
            ClariMed connects AI-assisted screening with real appointment booking and a specialist network.
            The core screening engine has no cloud dependency — it keeps working where the connection doesn't.
          </p>
          <div className="flex flex-col items-center gap-4">
            <button
              onClick={onStart}
              className="px-10 py-5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-lg rounded-2xl transition-all duration-300 shadow-2xl shadow-emerald-500/20 hover:shadow-emerald-400/40 transform hover:-translate-y-1"
            >
              Start a screening
            </button>
            <span className="text-xs text-slate-500 flex items-center gap-1.5">
              <Wifi size={14} className="text-emerald-500" /> Screening works offline
            </span>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 1, delay: 0.3, ease: EASE }}
          className="mt-20 z-10"
        >
          <LiveScannerDemo />
        </motion.div>

        <motion.div
          className="absolute bottom-8 left-1/2 -translate-x-1/2 text-slate-600"
          animate={{ y: [0, 8, 0] }} transition={{ duration: 2, repeat: Infinity, ease: EASE }}
        >
          <ArrowDown size={20} />
        </motion.div>
      </section>

      {/* Pinned scroll-driven pipeline — the Apple technique */}
      <section className="px-0">
        <div className="text-center pt-32 pb-8 px-6">
          <Reveal>
            <span className="text-emerald-400 text-xs font-mono tracking-widest uppercase">How it works</span>
            <h2 className="font-display text-4xl md:text-5xl font-semibold tracking-tight text-slate-100 mt-4">
              Five real stages. In order.
            </h2>
          </Reveal>
        </div>
        <PinnedPipeline />
      </section>

      {/* Coverage — huge stat numbers, Apple loves a big number */}
      <section className="py-36 px-6 max-w-5xl mx-auto text-center">
        <Reveal>
          <span className="text-emerald-400 text-xs font-mono tracking-widest uppercase">Coverage</span>
          <h2 className="font-display text-5xl md:text-6xl font-semibold tracking-tight text-slate-100 mt-4 mb-3">
            46 conditions.
          </h2>
          <p className="text-slate-400 text-lg mb-16">Across 11 body parts — and growing.</p>
        </Reveal>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          {COVERAGE.map((c, i) => (
            <Reveal key={c.label} delay={i * 0.08}>
              <div className="p-6 bg-slate-900/40 border border-slate-800/80 rounded-3xl hover:border-emerald-500/40 transition-colors">
                <div className="text-emerald-400 flex justify-center mb-4">{c.icon}</div>
                <div className="font-display text-3xl font-semibold text-white">{c.count}</div>
                <p className="text-xs text-slate-500 mt-1">{c.label}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Explainability showcase */}
      <section className="py-32 px-6 max-w-5xl mx-auto">
        <Reveal>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-16 items-center">
            <div>
              <span className="text-emerald-400 text-xs font-mono tracking-widest uppercase">Explainable</span>
              <h2 className="font-display text-4xl md:text-5xl font-semibold tracking-tight text-slate-100 mt-4 mb-6 leading-tight">
                Every result
                <br />shows its work.
              </h2>
              <p className="text-slate-400 text-lg leading-relaxed mb-4">
                You see how strongly your symptoms and image fit each condition, exactly which signals matched, and
                a visual map of what the analysis focused on.
              </p>
              <p className="text-slate-500 leading-relaxed">
                When the evidence is thin, ClariMed refuses to rank conditions rather than implying a precision
                it doesn't have — and tells you what would sharpen the result.
              </p>
            </div>
            <div className="bg-slate-900/50 border border-slate-800 rounded-3xl p-7 space-y-4">
              <p className="text-[11px] text-slate-500 pb-1">Based on 3 symptoms and an uploaded image</p>
              {[
                { name: 'Conjunctivitis', strength: 'Strong match', bar: 78 },
                { name: 'Dry Eye Disease', strength: 'Weak match', bar: 34 },
              ].map((row) => (
                <div key={row.name}>
                  <div className="flex justify-between items-center text-sm mb-1.5">
                    <span className="text-slate-300">{row.name}</span>
                    <span className="text-slate-500 font-mono text-xs">{row.strength}</span>
                  </div>
                  <div className="bg-slate-800 rounded-full h-2">
                    <div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${row.bar}%` }} />
                  </div>
                </div>
              ))}
              <p className="text-[11px] text-slate-600 pt-3 leading-relaxed">
                Match strength is how well your symptoms fit a condition — not the chance you have it.
              </p>
              <p className="text-[10px] text-slate-600 font-mono pt-1">SAMPLE OUTPUT — ILLUSTRATIVE</p>
            </div>
          </div>
        </Reveal>
      </section>

      {/* Privacy — dedicated spread, Apple's actual pattern */}
      <section className="py-36 px-6 bg-gradient-to-b from-slate-950 via-slate-900/40 to-slate-950">
        <div className="max-w-5xl mx-auto text-center mb-20">
          <Reveal>
            <span className="text-emerald-400 text-xs font-mono tracking-widest uppercase">Privacy</span>
            <h2 className="font-display text-5xl md:text-6xl font-semibold tracking-tight text-slate-100 mt-4">
              Your photo stays yours.
            </h2>
          </Reveal>
        </div>
        <div className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-8">
          {PRIVACY_POINTS.map((p, i) => (
            <Reveal key={p.title} delay={i * 0.1}>
              <div className="text-center px-4">
                <div className="text-emerald-400 flex justify-center mb-5">{p.icon}</div>
                <h3 className="font-display text-xl font-semibold text-white mb-3">{p.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{p.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-40 px-6 text-center">
        <Reveal>
          <h2 className="font-display text-5xl md:text-6xl font-semibold tracking-tight mb-6">
            Ready to see what it finds?
          </h2>
          <p className="text-slate-400 text-lg mb-10 max-w-lg mx-auto">Takes about two minutes. No account needed.</p>
          <button
            onClick={onStart}
            className="px-10 py-5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold text-lg rounded-2xl transition-all duration-300 shadow-2xl shadow-emerald-500/20 hover:shadow-emerald-400/40 transform hover:-translate-y-1"
          >
            Start a screening
          </button>
        </Reveal>
      </section>

      <footer className="border-t border-slate-900 bg-slate-950 py-14 px-6 text-center text-xs text-slate-500 tracking-wide">
        <p className="max-w-2xl mx-auto uppercase font-mono leading-relaxed">
          ⚠️ ClariMed AI provides assisted preliminary screening only. It does not diagnose disease or prescribe
          treatment. Always confirm any result with a licensed healthcare professional.
        </p>
      </footer>
    </div>
  );
}