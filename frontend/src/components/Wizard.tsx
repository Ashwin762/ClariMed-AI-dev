import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Upload, CheckCircle2, ChevronRight, AlertTriangle, ArrowLeft, Loader2, FileText, Phone, MapPin } from 'lucide-react';

export default function Wizard({ onBack }: { onBack: () => void }) {
  const [step, setStep] = useState(1);
  const [transcript, setTranscript] = useState('');
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);
  const [image, setImage] = useState<File | null>(null);
  const [isListening, setIsListening] = useState(false);
  
  const [loading, setLoading] = useState(false);
  const [screeningReport, setScreeningReport] = useState<string | null>(null);
  const [networkClinics, setNetworkClinics] = useState<any[]>([]);
  const [metaInfo, setMetaInfo] = useState<any>(null);

  const handleVoiceInput = () => {
    // @ts-ignore
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return alert("Speech API not supported in this browser.");
    
    const recognition = new SpeechRecognition();
    recognition.lang = 'en-US';
    setIsListening(true);

    recognition.onresult = (event: any) => {
      setTranscript(event.results[0][0].transcript);
      setIsListening(false);
    };
    recognition.onerror = () => setIsListening(false);
    recognition.start();
  };

  const toggleSymptom = (symptom: string) => {
    setSelectedSymptoms(prev => 
      prev.includes(symptom) ? prev.filter(s => s !== symptom) : [...prev, symptom]
    );
  };

  const submitScreeningData = async () => {
    setLoading(true);
    try {
      // Create FormData layout to support stream processing of binary files
      const formData = new FormData();
      formData.append('symptoms_json', JSON.stringify(selectedSymptoms));
      formData.append('transcript', transcript);
      if (image) {
        formData.append('file', image);
      }

      const response = await fetch('http://127.0.0.1:8000/api/screen', {
        method: 'POST',
        body: formData // Browser handles headers automatically for Multipart fields
      });
      
      const data = await response.json();
      if (data.success) {
        setScreeningReport(data.preliminary_report);
        setNetworkClinics(data.healthcare_network || []);
        setMetaInfo(data.metadata);
      } else {
        setScreeningReport(data.preliminary_report); // Handles failure summaries gracefully
        setMetaInfo(data.metadata);
      }
    } catch (err) {
      console.error(err);
      alert("Pipeline integration mismatch. Validate FastAPI local service instances.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-950 text-slate-50 min-h-screen flex flex-col justify-between p-6 font-sans">
      <header className="flex justify-between items-center max-w-3xl w-full mx-auto pb-4 border-b border-slate-800">
        <button onClick={onBack} className="text-slate-400 hover:text-white flex items-center gap-1 text-sm transition-colors">
          <ArrowLeft size={16} /> Exit Engine
        </button>
        <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
          {screeningReport ? 'Ecosystem Analysis Output' : `Step {step} of 3`}
        </span>
      </header>

      <main className="max-w-3xl w-full mx-auto py-12 flex-grow flex flex-col justify-center">
        {loading ? (
          <div className="text-center space-y-4 py-12">
            <Loader2 className="w-12 h-12 text-emerald-400 animate-spin mx-auto" />
            <p className="text-sm font-mono text-slate-400">Processing Multimodal Matrix Array & Quantifying Risk Tiers...</p>
          </div>
        ) : screeningReport ? (
          <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
            
            {/* Header Telemetry row */}
            <div className="flex justify-between items-start border-b border-slate-800 pb-4">
              <div>
                <h2 className="text-2xl font-bold text-white flex items-center gap-2">
                  <FileText className="text-emerald-400" /> ClariMed Smart Intake Chart
                </h2>
                <p className="text-xs text-slate-400 mt-1">Unified Multi-Product Analysis Matrix</p>
              </div>
              <div className="text-right">
                <span className={`inline-block text-[10px] font-mono border px-2.5 py-0.5 rounded uppercase font-semibold tracking-wide ${metaInfo?.risk_tier?.includes('Medium') ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'}`}>
                  {metaInfo?.risk_tier}
                </span>
                <p className="text-xs text-emerald-400 font-mono mt-1">{metaInfo?.confidence_bracket}</p>
              </div>
            </div>

            {/* Grid Splitter: Left column (RAG Intelligence), Right column (Healthcare Network) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              
              {/* Product 2 & 3 Output Column */}
              <div className="space-y-2">
                <h3 className="text-xs font-mono tracking-wider uppercase text-slate-400">Clinical Evaluation Breakdown</h3>
                <div className="bg-slate-900/50 border border-slate-800/80 rounded-xl p-5 text-sm text-slate-300 leading-relaxed max-h-[380px] overflow-y-auto whitespace-pre-wrap font-sans">
                  {screeningReport}
                </div>
              </div>

              {/* Product 4 Network Node Navigation Output Column */}
              <div className="space-y-4">
                <div>
                  <h3 className="text-xs font-mono tracking-wider uppercase text-slate-400">Intelligent Referral Channels</h3>
                  <p className="text-xs text-slate-500 mt-0.5">Automated primary routing mapping vectors:</p>
                </div>
                
                <div className="space-y-3">
                  {networkClinics.map((clinic, index) => (
                    <div key={index} className="bg-slate-900/30 border border-slate-800/60 p-4 rounded-xl space-y-3 hover:border-slate-700 transition-colors">
                      <div className="flex justify-between items-start">
                        <div>
                          <h4 className="text-sm font-semibold text-slate-200">{clinic.name}</h4>
                          <p className="text-xs text-slate-400 flex items-center gap-1 mt-1">
                            <MapPin size={12} className="text-emerald-400" /> {clinic.clinic}
                          </p>
                        </div>
                        <span className="text-[10px] font-mono bg-slate-800 text-slate-400 px-2 py-0.5 rounded">{clinic.distance}</span>
                      </div>
                      
                      <a href={`tel:${clinic.phone}`} className="w-full py-2 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 text-emerald-400 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-colors">
                        <Phone size={12} /> Contact Specialist Clinic
                      </a>
                    </div>
                  ))}
                </div>

                {/* Mock Map Element Placeholder block */}
                <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 flex items-center justify-center h-28 relative overflow-hidden group">
                  <div className="absolute inset-0 bg-gradient-to-br from-emerald-950/20 to-slate-900 opacity-60" />
                  <span className="text-xs font-mono text-slate-400 relative z-10 group-hover:text-emerald-400 transition-colors">🗺️ Interactive Leaflet Map Array Mounted</span>
                </div>
              </div>

            </div>

            <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl text-[10px] text-slate-500 font-mono uppercase tracking-wider text-center">
              ⚠️ {metaInfo?.regulatory_disclaimer}
            </div>
            
            <button 
              onClick={() => { setScreeningReport(null); setStep(1); setSelectedSymptoms([]); setTranscript(''); setImage(null); }}
              className="w-full py-3 bg-slate-800 hover:bg-slate-750 text-white rounded-xl text-sm font-medium transition-colors"
            >
              Initialize New Ecosystem Diagnostic Scan
            </button>
          </motion.div>
        ) : (
          /* Keep Multi-step Form Wizard Elements intact */
          <AnimatePresence mode="wait">
            {step === 1 && (
              <motion.div key="step1" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: -20 }} className="space-y-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">Select Target Physiological Area</h2>
                  <p className="text-slate-400 text-sm mt-1">Version 1 deployment supports targeted high-fidelity ophthalmic assessment.</p>
                </div>
                <div className="grid grid-cols-1 gap-4">
                  <div className="p-5 bg-emerald-500/10 border-2 border-emerald-500 rounded-xl flex items-center justify-between cursor-pointer">
                    <div>
                      <h3 className="font-semibold text-emerald-400">Ophthalmic System (Eye)</h3>
                      <p className="text-xs text-slate-400 mt-0.5">Active modules: Conjunctivitis, Dry Eye Disease</p>
                    </div>
                    <CheckCircle2 className="text-emerald-400" />
                  </div>
                  <div className="p-5 bg-slate-900/40 border border-slate-800/80 rounded-xl opacity-40 cursor-not-allowed flex items-center justify-between">
                    <div>
                      <h3 className="font-semibold text-slate-300">Dermatological System (Skin)</h3>
                      <p className="text-xs text-slate-500 mt-0.5">Pipeline expansion scheduled for Next Phase</p>
                    </div>
                    <span className="text-xs font-mono text-slate-500 bg-slate-800 px-2 py-0.5 rounded">Locked</span>
                  </div>
                </div>
              </motion.div>
            )}

            {step === 2 && (
              <motion.div key="step2" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: -20 }} className="space-y-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">Symptom Quantification & Mapping</h2>
                  <p className="text-slate-400 text-sm mt-1">Select distinct physiological flags and provide optional verbal reports.</p>
                </div>
                <div className="flex flex-wrap gap-2.5">
                  {['Ocular Redness', 'Watery Eyes', 'Itching', 'Burning Sensation', 'Dryness', 'Crust Formation'].map((sym) => (
                    <button
                      key={sym}
                      onClick={() => toggleSymptom(sym)}
                      className={`px-4 py-2 text-xs rounded-lg border font-medium transition-all duration-200 ${
                        selectedSymptoms.includes(sym) 
                          ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500' 
                          : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      {sym}
                    </button>
                  ))}
                </div>

                <div className="pt-4 border-t border-slate-900">
                  <label className="block text-sm font-medium text-slate-300 mb-2">Supplementary Verbal Synthesis (Optional)</label>
                  <div className="flex gap-2">
                    <input 
                      type="text" 
                      value={transcript}
                      onChange={(e) => setTranscript(e.target.value)}
                      placeholder="Describe supplementary symptoms via vocal input stream..." 
                      className="flex-grow bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-slate-700 text-slate-300"
                    />
                    <button 
                      onClick={handleVoiceInput}
                      className={`p-3 rounded-xl transition-all border ${isListening ? 'bg-red-500/20 text-red-400 border-red-500 animate-pulse' : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'}`}
                    >
                      <Mic size={18} />
                    </button>
                  </div>
                </div>
              </motion.div>
            )}

            {step === 3 && (
              <motion.div key="step3" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: -20 }} className="space-y-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">High-Resolution Image Processing</h2>
                  <p className="text-slate-400 text-sm mt-1">Provide clear macro imagery under controlled lighting variables.</p>
                </div>
                <div className="border-2 border-dashed border-slate-800 hover:border-slate-700 transition-colors rounded-2xl p-10 flex flex-col items-center justify-center text-center cursor-pointer relative bg-slate-900/10">
                  <input 
                    type="file" 
                    accept="image/*" 
                    onChange={(e) => e.target.files && setImage(e.target.files[0])} 
                    className="absolute inset-0 opacity-0 cursor-pointer"
                  />
                  <Upload className="text-slate-500 mb-3 w-8 h-8" />
                  {image ? (
                    <p className="text-sm text-emerald-400 font-mono">{image.name} successfully mounted.</p>
                  ) : (
                    <p className="text-sm text-slate-400">Drag imagery here or <span className="text-emerald-400 underline">browse matrix array</span></p>
                  )}
                </div>
                <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl flex gap-3">
                  <AlertTriangle className="text-amber-400 shrink-0 w-5 h-5 mt-0.5" />
                  <p className="text-xs text-amber-300/90 leading-normal">
                    <strong>Quality Control Pipeline Validation:</strong> Blur profiles, sub-optimal luminosity metrics, and structural occlusion will trigger automated ingestion rejection frameworks.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </main>

      {!screeningReport && !loading && (
        <footer className="max-w-xl w-full mx-auto pt-6 border-t border-slate-900 flex justify-between items-center">
          <button 
            onClick={() => step > 1 && setStep(step - 1)}
            disabled={step === 1}
            className="text-sm text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-0"
          >
            Previous Step
          </button>
          <button 
            onClick={() => step < 3 ? setStep(step + 1) : submitScreeningData()}
            className="bg-slate-100 hover:bg-white text-slate-950 font-medium px-5 py-2.5 rounded-xl text-sm flex items-center gap-1.5 transition-all shadow-md active:scale-95"
          >
            {step === 3 ? "Initialize Screening" : "Proceed Integration"} <ChevronRight size={16} />
          </button>
        </footer>
      )}
    </div>
  );
}