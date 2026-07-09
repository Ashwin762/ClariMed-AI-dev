import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Activity, Eye, Hand, Sparkles, Smile, ScanLine, Layers,
  BookOpen, MapPinned, Wifi, WifiOff, ShieldCheck, ArrowDown,
} from 'lucide-react';

/* ---------- Signature element: a live, looping mini-scanner ---------- */
/* Recreates, in miniature, exactly what the real product does: sweep a
   photo, surface detection markers, and produce a scored confidence read. */
function LiveScannerDemo() {
  const [pct, setPct] = useState(0);

  useEffect(() => {
    const cycleMs = 2600;
    const start = Date.now();
    const iv = setInterval(() => {
      const elapsed = (Date.now() - start) % cycleMs;
      const t = elapsed / cycleMs;
      // ramps up between 35%-90% of the cycle, holds, then resets
      const val = t < 0.35 ? 0 : t < 0.85 ? Math.round(((t - 0.35) / 0.5) * 92) : 92;
      setPct(val);
    }, 60);
    return () => clearInterval(iv);
  }, []);

  return (
    <div className="relative w-full max-w-xs mx-auto">
      <div className="relative aspect-square rounded-3xl border border-slate-800 bg-slate-900/60 overflow-hidden">
        {/* corner reticle */}
        {['top-3 left-3 border-t border-l', 'top-3 right-3 border-t border-r', 'bottom-3 left-3 border-b border-l', 'bottom-3 right-3 border-b border-r'].map((pos, i) => (
          <div key={i} className={`absolute w-5 h-5 border-emerald-500/60 ${pos}`} />
        ))}

        {/* abstract eye silhouette */}
        <svg viewBox="0 0 240 200" className="absolute inset-0 w-full h-full p-8">
          <path d="M20,100 Q120,30 220,100 Q120,170 20,100 Z" fill="none" stroke="#334155" strokeWidth="2" />
          <circle cx="120" cy="100" r="34" fill="none" stroke="#334155" strokeWidth="2" />
          <circle cx="120" cy="100" r="14" fill="#1e293b" />

          {/* detection markers - stagger their appearance across the scan cycle */}
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

        {/* scan line sweep */}
        <motion.div
          className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-emerald-400 to-transparent shadow-[0_0_12px_2px_rgba(52,211,153,0.6)]"
          animate={{ top: ['8%', '92%', '8%'] }}
          transition={{ duration: 2.6, repeat: Infinity, ease: 'linear' }}
        />
      </div>

      <div className="flex items-center justify-between mt-3 px-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">Live analysis (sample)</span>
        <span className="text-sm font-mono text-emerald-400">{pct}%</span>
      </div>
    </div>
  );
}

/* ---------- Reveal wrapper for scroll-triggered sections ---------- */
function Reveal({ children, delay = 0, x = 0 }: { children: React.ReactNode; delay?: number; x?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24, x }}
      whileInView={{ opacity: 1, y: 0, x: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

const PIPELINE = [
  { icon: <ScanLine size={22} />, title: 'Capture', desc: 'Select the affected area, note your symptoms, and optionally add a photo. Everything is processed on the server — nothing goes to a third party.' },
  { icon: <Layers size={22} />, title: 'Analyze', desc: 'A fusion engine reads real pixel signals (redness, texture, tint) from your photo and combines them with your symptoms into a scored, ranked result — not a black box.' },
  { icon: <BookOpen size={22} />, title: 'Explain', desc: 'Every result comes with a visual attention map and a plain list of exactly which symptoms and image findings drove the outcome.' },
  { icon: <ShieldCheck size={22} />, title: 'Guide', desc: 'Guidance is pulled from a curated knowledge base you can read yourself — precautions, home care, and clear signs to seek help.' },
  { icon: <MapPinned size={22} />, title: 'Connect', desc: 'Get matched with the right kind of specialist, save the result to your history, and download a PDF report to bring to your appointment.' },
];

const COVERAGE = [
  { icon: <Eye size={22} />, label: 'Eye', count: 2 },
  { icon: <Hand size={22} />, label: 'Skin', count: 5 },
  { icon: <Sparkles size={22} />, label: 'Nail', count: 4 },
  { icon: <Smile size={22} />, label: 'Oral', count: 4 },
  { icon: <Activity size={22} />, label: 'General Health', count: 4 },
];

export default function Hero({ onStart }: { onStart: () => void }) {
  return (
    <div className="bg-slate-950 text-slate-50 min-h-screen font-sans selection:bg-emerald-500/30">
      <nav className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-slate-950/70 border-b border-slate-800 px-6 py-4 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <Activity className="text-emerald-400 w-6 h-6" />
          <span className="font-display font-bold text-xl tracking-tight text-white">
            ClariMed<span className="text-emerald-400">.AI</span>
          </span>
        </div>
        <span className="text-[11px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 rounded-full font-mono">
          19 conditions · 5 body parts
        </span>
      </nav>

      {/* Hero */}
      <section className="min-h-screen flex items-center px-6 pt-20 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_40%,rgba(16,185,129,0.08),transparent_55%)]" />
        <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-14 items-center z-10 w-full">
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7 }}>
            <span className="text-emerald-400 text-xs font-mono tracking-widest uppercase border border-emerald-500/30 bg-emerald-950/40 px-3 py-1 rounded-full">
              Connected care, resilient anywhere
            </span>
            <h1 className="font-display text-5xl md:text-6xl font-semibold tracking-tight mt-6 mb-6 leading-[1.08]">
              See what your symptoms
              <br />
              <span className="text-emerald-400">and a photo</span> can tell you.
            </h1>
            <p className="text-slate-400 text-lg max-w-xl mb-8 leading-relaxed">
              ClariMed connects AI-assisted screening with real appointment booking, a specialist network, and a
              synced health history. The core screening engine has no cloud dependency, so it keeps working even in
              clinics where the connection doesn't — built for unreliable internet, not just none.
            </p>
            <div className="flex items-center gap-4">
              <button
                onClick={onStart}
                className="px-8 py-4 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold rounded-xl transition-all duration-300 shadow-lg shadow-emerald-500/20 hover:shadow-emerald-400/40 transform hover:-translate-y-0.5"
              >
                Start a screening
              </button>
              <span className="text-xs text-slate-500 flex items-center gap-1.5">
                <Wifi size={14} className="text-emerald-500" /> Screening works offline
              </span>
            </div>
          </motion.div>

          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.8, delay: 0.2 }}>
            <LiveScannerDemo />
          </motion.div>
        </div>

        <motion.div
          className="absolute bottom-8 left-1/2 -translate-x-1/2 text-slate-600"
          animate={{ y: [0, 6, 0] }}
          transition={{ duration: 1.8, repeat: Infinity }}
        >
          <ArrowDown size={18} />
        </motion.div>
      </section>

      {/* How it works - real pipeline, order carries meaning */}
      <section className="py-32 px-6 max-w-5xl mx-auto">
        <Reveal>
          <div className="mb-16">
            <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-100">How a screening actually works</h2>
            <p className="text-slate-400 mt-2">Five real stages, in order — the same ones you'll walk through.</p>
          </div>
        </Reveal>
        <div className="space-y-6">
          {PIPELINE.map((step, i) => (
            <Reveal key={step.title} delay={i * 0.06} x={i % 2 === 0 ? -20 : 20}>
              <div className="flex items-start gap-5 p-6 bg-slate-900/40 border border-slate-800/80 rounded-2xl hover:border-slate-700 transition-colors">
                <div className="shrink-0 w-11 h-11 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                  {step.icon}
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-mono text-slate-600">0{i + 1}</span>
                    <h3 className="font-display text-lg font-semibold text-white">{step.title}</h3>
                  </div>
                  <p className="text-slate-400 text-sm leading-relaxed">{step.desc}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Online ecosystem vs offline-resilient screening */}
      <section className="py-24 px-6 max-w-5xl mx-auto">
        <Reveal>
          <div className="mb-12 text-center">
            <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-100">
              A connected system, built to degrade gracefully
            </h2>
            <p className="text-slate-400 mt-2 max-w-xl mx-auto">
              ClariMed is a full healthcare ecosystem. In areas with unreliable connectivity, screening keeps working —
              only the parts that genuinely need a live network step back.
            </p>
          </div>
        </Reveal>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Reveal x={-20}>
            <div className="p-6 bg-emerald-500/5 border border-emerald-500/20 rounded-2xl h-full">
              <div className="flex items-center gap-2 mb-4">
                <Wifi size={16} className="text-emerald-400" />
                <h3 className="font-display font-semibold text-emerald-300">Always available</h3>
              </div>
              <ul className="space-y-2.5 text-sm text-slate-300">
                <li className="flex gap-2"><span className="text-emerald-500">-</span> Image + symptom screening</li>
                <li className="flex gap-2"><span className="text-emerald-500">-</span> Visual attention map & differential</li>
                <li className="flex gap-2"><span className="text-emerald-500">-</span> Curated medical guidance</li>
                <li className="flex gap-2"><span className="text-emerald-500">-</span> PDF report generation</li>
              </ul>
            </div>
          </Reveal>
          <Reveal x={20} delay={0.08}>
            <div className="p-6 bg-slate-900/40 border border-slate-800/80 rounded-2xl h-full">
              <div className="flex items-center gap-2 mb-4">
                <WifiOff size={16} className="text-slate-500" />
                <h3 className="font-display font-semibold text-slate-300">Needs connection</h3>
              </div>
              <ul className="space-y-2.5 text-sm text-slate-400">
                <li className="flex gap-2"><span className="text-slate-600">-</span> Booking a specialist appointment</li>
                <li className="flex gap-2"><span className="text-slate-600">-</span> Specialist directory sync</li>
                <li className="flex gap-2"><span className="text-slate-600">-</span> Screening history sync across devices</li>
                <li className="flex gap-2"><span className="text-slate-600">-</span> Hospital network updates</li>
              </ul>
            </div>
          </Reveal>
        </div>
      </section>

      {/* Coverage */}
      <section className="py-24 px-6 max-w-5xl mx-auto">
        <Reveal>
          <div className="mb-12 text-center">
            <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-100">What it currently screens for</h2>
            <p className="text-slate-400 mt-2">19 conditions across 5 body parts — and growing.</p>
          </div>
        </Reveal>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          {COVERAGE.map((c, i) => (
            <Reveal key={c.label} delay={i * 0.08}>
              <div className="p-5 bg-slate-900/40 border border-slate-800/80 rounded-2xl text-center hover:border-emerald-500/40 transition-colors">
                <div className="text-emerald-400 flex justify-center mb-3">{c.icon}</div>
                <h3 className="text-sm font-medium text-slate-200">{c.label}</h3>
                <p className="text-xs font-mono text-slate-500 mt-1">{c.count} conditions</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Explainability showcase */}
      <section className="py-24 px-6 max-w-4xl mx-auto">
        <Reveal>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-10 items-center">
            <div>
              <h2 className="font-display text-3xl font-semibold tracking-tight text-slate-100 mb-4">
                Every result shows its work
              </h2>
              <p className="text-slate-400 leading-relaxed mb-4">
                You see how strongly your symptoms and image fit each condition, exactly which signals matched, and a
                visual map of what the image analysis focused on.
              </p>
              <p className="text-slate-500 text-sm leading-relaxed">
                When the evidence is thin, ClariMed refuses to rank conditions rather than implying a precision it
                doesn't have — and it tells you what would sharpen the result.
              </p>
            </div>
            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 space-y-3">
              <p className="text-[10px] text-slate-500 pb-1">Based on 3 symptoms and an uploaded image</p>
              {[
                { name: 'Conjunctivitis', strength: 'Strong match', bar: 78 },
                { name: 'Dry Eye Disease', strength: 'Weak match', bar: 34 },
              ].map((row) => (
                <div key={row.name}>
                  <div className="flex justify-between items-center text-xs mb-1">
                    <span className="text-slate-300">{row.name}</span>
                    <span className="text-slate-500 font-mono text-[10px]">{row.strength}</span>
                  </div>
                  <div className="bg-slate-800 rounded-full h-1.5">
                    <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: `${row.bar}%` }} />
                  </div>
                </div>
              ))}
              <p className="text-[10px] text-slate-600 pt-2 leading-relaxed">
                Match strength is how well your symptoms fit a condition — not the chance you have it.
              </p>
              <p className="text-[10px] text-slate-600 font-mono pt-1">SAMPLE OUTPUT — ILLUSTRATIVE</p>
            </div>
          </div>
        </Reveal>
      </section>

      {/* Final CTA */}
      <section className="py-32 px-6 text-center">
        <Reveal>
          <h2 className="font-display text-4xl font-semibold tracking-tight mb-4">Ready to see what it finds?</h2>
          <p className="text-slate-400 mb-8 max-w-lg mx-auto">Takes about two minutes. No account needed.</p>
          <button
            onClick={onStart}
            className="px-8 py-4 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold rounded-xl transition-all duration-300 shadow-lg shadow-emerald-500/20 hover:shadow-emerald-400/40 transform hover:-translate-y-0.5"
          >
            Start a screening
          </button>
        </Reveal>
      </section>

      <footer className="border-t border-slate-900 bg-slate-950 py-12 px-6 text-center text-xs text-slate-500 tracking-wide">
        <p className="max-w-2xl mx-auto uppercase font-mono">
          ⚠️ ClariMed AI provides assisted preliminary screening only. It does not diagnose disease or prescribe
          treatment. Always confirm any result with a licensed healthcare professional.
        </p>
      </footer>
    </div>
  );
}