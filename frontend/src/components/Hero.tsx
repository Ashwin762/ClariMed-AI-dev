import React from 'react';
import { motion } from 'framer-motion';
import { Shield, Eye, Activity, Terminal } from 'lucide-react';

export default function Hero({ onStart }: { onStart: () => void }) {
  return (
    <div className="bg-slate-950 text-slate-50 min-h-screen font-sans selection:bg-emerald-500/30">
      {/* Top Glassmorphic Navbar */}
      <nav className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-slate-950/70 border-b border-slate-800 px-6 py-4 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <Activity className="text-emerald-400 w-6 h-6 animate-pulse" />
          <span className="font-bold text-xl tracking-tight bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">ClariMed<span className="text-emerald-400">.AI</span></span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 rounded-full font-mono">v1.0 MVP Core</span>
        </div>
      </nav>

      {/* Section 1: The Hook */}
      <section className="min-h-screen flex flex-col justify-center items-center px-4 pt-20 text-center relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(16,185,129,0.08),transparent_50%)]" />
        
        <motion.div 
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="max-w-3xl z-10"
        >
          <span className="text-emerald-400 text-sm font-mono tracking-widest uppercase border border-emerald-500/30 bg-emerald-950/40 px-3 py-1 rounded-full">
            Clinical Intelligence Ecosystem
          </span>
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight mt-6 mb-6 leading-[1.1]">
            Next-Gen Preliminary <br/>
            <span className="bg-gradient-to-r from-emerald-400 via-teal-200 to-cyan-400 bg-clip-text text-transparent">Medical Screening</span>
          </h1>
          <p className="text-slate-400 text-lg md:text-xl max-w-2xl mx-auto mb-10 leading-relaxed">
            A multimodal clinical evaluation engine combining computer vision, real-time context-aware symptom mapping, and strict retrieval-augmented medical governance.
          </p>
          <button 
            onClick={onStart}
            className="group relative px-8 py-4 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold rounded-xl transition-all duration-300 shadow-lg shadow-emerald-500/20 hover:shadow-emerald-400/40 transform hover:-translate-y-0.5"
          >
            Launch Screening Engine
          </button>
        </motion.div>
      </section>

      {/* Section 2: Scrollytelling Architecture Pipeline */}
      <section className="py-32 px-6 max-w-5xl mx-auto space-y-24">
        <div className="text-center md:text-left">
          <h2 className="text-3xl font-bold tracking-tight text-slate-200">The 4-Tier Evaluation Protocol</h2>
          <p className="text-slate-400 mt-2">How ClariMed processes preliminary data securely.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 relative">
          {/* Box 1 */}
          <motion.div 
            initial={{ opacity: 0, x: -50 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            className="p-8 bg-slate-900/50 border border-slate-800 rounded-2xl hover:border-slate-700 transition-colors"
          >
            <Eye className="text-emerald-400 w-8 h-8 mb-4" />
            <h3 className="text-xl font-semibold text-white mb-2">1. Computer Vision Layer</h3>
            <p className="text-slate-400 text-sm leading-relaxed">
              Utilizes a deep Transfer Learning backbone (ResNet50 architecture) optimized for rapid feature identification in ophthalmic variations.
            </p>
          </motion.div>

          {/* Box 2 */}
          <motion.div 
            initial={{ opacity: 0, x: 50 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            className="p-8 bg-slate-900/50 border border-slate-800 rounded-2xl hover:border-slate-700 transition-colors"
          >
            <Terminal className="text-emerald-400 w-8 h-8 mb-4" />
            <h3 className="text-xl font-semibold text-white mb-2">2. Explainable AI (XAI)</h3>
            <p className="text-slate-400 text-sm leading-relaxed">
              Generates targeted spatial activation maps through Grad-CAM localization, highlighting targeted clinical indicators with mathematical backing.
            </p>
          </motion.div>

          {/* Box 3 */}
          <motion.div 
            initial={{ opacity: 0, x: -50 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            className="p-8 bg-slate-900/50 border border-slate-800 rounded-2xl hover:border-slate-700 transition-colors"
          >
            <Shield className="text-emerald-400 w-8 h-8 mb-4" />
            <h3 className="text-xl font-semibold text-white mb-2">3. Isolated Medical RAG</h3>
            <p className="text-slate-400 text-sm leading-relaxed">
              Queries a local, curated multi-layered vector store (ChromaDB) seeded completely by verified institutions like WHO, NIH, and CDC. Zero internet reliance.
            </p>
          </motion.div>

          {/* Box 4 */}
          <motion.div 
            initial={{ opacity: 0, x: 50 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            className="p-8 bg-slate-900/50 border border-slate-800 rounded-2xl hover:border-slate-700 transition-colors"
          >
            <Activity className="text-emerald-400 w-8 h-8 mb-4" />
            <h3 className="text-xl font-semibold text-white mb-2">4. Context-Aware Pipeline</h3>
            <p className="text-slate-400 text-sm leading-relaxed">
              Consolidates diagnostic imagery, user history, and real-time symptom mapping metrics to render zero-diagnosis screening thresholds.
            </p>
          </motion.div>
        </div>
      </section>

      {/* Strict Guardrail Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-12 px-6 text-center text-xs text-slate-500 tracking-wide">
        <p className="max-w-2xl mx-auto uppercase font-mono">
          ⚠️ CLARIMED AI IS AN ASSISTED PRELIMINARY SCREENING ECOSYSTEM. IT DOES NOT PROVIDE FORMAL DIAGNOSES, PROGNOSES, OR THERAPEUTIC PRESCRIPTIONS. ALL DATA RENDERED MUST BE VERIFIED INDEPENDENTLY BY A LICENSED HEALTHCARE PROFESSIONAL.
        </p>
      </footer>
    </div>
  );
}