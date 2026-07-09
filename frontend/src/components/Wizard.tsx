import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Mic, Upload, CheckCircle2, ChevronRight, AlertTriangle, ArrowLeft,
  Loader2, FileText, Phone, MapPin, Download, History, User, Eye,
  Sparkles, Hand, Smile, Activity, ShieldAlert, WifiOff, CalendarCheck,
  Ear, Wind, Utensils, Bone,
} from 'lucide-react';
import {
  fetchConfig, submitScreening, fetchHistory, downloadReport, bookAppointment,
  type BodyPart, type ConfigResponse, type ScreenResponse, type HistoryItem, type Clinic,
} from '../api';
import { useOnlineStatus } from '../useOnlineStatus';

const BODY_PART_META: Record<BodyPart, { label: string; icon: React.ReactNode; desc: string }> = {
  eye: { label: 'Eye', icon: <Eye size={20} />, desc: 'Redness, irritation, vision changes' },
  skin: { label: 'Skin', icon: <Hand size={20} />, desc: 'Rashes, patches, acne, irritation' },
  nail: { label: 'Nail', icon: <Sparkles size={20} />, desc: 'Discoloration, thickening, pain' },
  oral: { label: 'Oral', icon: <Smile size={20} />, desc: 'Mouth, gums, lips' },
  dental: { label: 'Dental', icon: <Smile size={20} />, desc: 'Teeth, cavities, gum disease' },
  ent: { label: 'Ear / Nose / Throat', icon: <Ear size={20} />, desc: 'Ear pain, sinus, sore throat' },
  hair: { label: 'Hair / Scalp', icon: <Sparkles size={20} />, desc: 'Dandruff, hair loss, scalp issues' },
  respiratory: { label: 'Respiratory', icon: <Wind size={20} />, desc: 'Cough, wheezing, breathlessness - no photo needed' },
  digestive: { label: 'Digestive', icon: <Utensils size={20} />, desc: 'Heartburn, bloating, bowel changes - no photo needed' },
  musculoskeletal: { label: 'Muscles / Joints', icon: <Bone size={20} />, desc: 'Joint pain, back pain, strains - no photo needed' },
  general: { label: 'General Health', icon: <Activity size={20} />, desc: 'Fever, fatigue, headache - no photo needed' },
};

// Body parts with no reliable visual sign in a standard photo — the image
// upload step is skipped for these. Mirrors which conditions have no image
// scorer in ai/rules/condition_engine.py.
const NON_PHOTOGRAPHABLE: BodyPart[] = ['general', 'respiratory', 'digestive', 'musculoskeletal'];

const VOICE_LANGS = [
  { code: 'en-US', label: 'English' },
  { code: 'hi-IN', label: 'Hindi' },
  { code: 'kn-IN', label: 'Kannada' },
];

const RISK_STYLES: Record<string, string> = {
  green: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  yellow: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  red: 'bg-red-500/10 text-red-400 border-red-500/20',
};

function getStepOrder(bodyPart: BodyPart | null): string[] {
  const base = ['patient', 'bodypart', 'symptoms'];
  if (bodyPart && !NON_PHOTOGRAPHABLE.includes(bodyPart)) base.push('image');
  base.push('review');
  return base;
}

/** Small markdown-ish renderer for the guidance text (### headers, - bullets, plain paragraphs) */
function GuidanceText({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="space-y-2 text-sm text-slate-300 leading-relaxed">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed || trimmed === '---') return null;
        if (trimmed.startsWith('###')) {
          return (
            <h4 key={i} className="text-xs font-mono uppercase tracking-wider text-emerald-400 pt-2">
              {trimmed.replace(/^#+\s*/, '')}
            </h4>
          );
        }
        if (trimmed.startsWith('-')) {
          return (
            <div key={i} className="flex gap-2 pl-1">
              <span className="text-emerald-500">-</span>
              <span>{trimmed.replace(/^-\s*/, '')}</span>
            </div>
          );
        }
        if (trimmed.startsWith('*') && trimmed.endsWith('*')) {
          return (
            <p key={i} className="text-xs text-slate-500 italic pt-2">
              {trimmed.replace(/^\*|\*$/g, '')}
            </p>
          );
        }
        return <p key={i}>{trimmed}</p>;
      })}
    </div>
  );
}

export default function Wizard({ onBack }: { onBack: () => void }) {
  const isOnline = useOnlineStatus();
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);

  const [stepIndex, setStepIndex] = useState(0);
  const [patientName, setPatientName] = useState('');
  const [patientEmail, setPatientEmail] = useState('');
  const [bodyPart, setBodyPart] = useState<BodyPart | null>(null);
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);
  const [selectedRedflags, setSelectedRedflags] = useState<string[]>([]);
  const [transcript, setTranscript] = useState('');
  const [voiceLang, setVoiceLang] = useState('en-US');
  const [isListening, setIsListening] = useState(false);
  const [image, setImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<ScreenResponse | null>(null);

  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    fetchConfig()
      .then(setConfig)
      .catch(() => setConfigError('Could not reach the ClariMed backend. Is it running on port 8000?'));
  }, []);

  const steps = getStepOrder(bodyPart);
  const stepId = steps[stepIndex];

  const handleVoiceInput = () => {
    // @ts-ignore
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Voice input is not supported in this browser. Try Chrome.');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = voiceLang;
    setIsListening(true);
    recognition.onresult = (event: any) => {
      setTranscript(event.results[0][0].transcript);
      setIsListening(false);
    };
    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => setIsListening(false);
    recognition.start();
  };

  const toggleSymptom = (s: string) =>
    setSelectedSymptoms((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  const toggleRedflag = (s: string) =>
    setSelectedRedflags((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));

  const handleFile = (f: File) => {
    setImage(f);
    setImagePreview(URL.createObjectURL(f));
  };

  const goNext = () => setStepIndex((i) => Math.min(i + 1, steps.length - 1));
  const goBack = () => setStepIndex((i) => Math.max(i - 1, 0));

  const submitScreeningData = async () => {
    if (!bodyPart) return;
    setLoading(true);
    try {
      const data = await submitScreening({
        bodyPart, symptoms: selectedSymptoms, redflags: selectedRedflags,
        transcript, patientName, patientEmail, file: image,
      });
      setResponse(data);
    } catch (err) {
      console.error(err);
      alert('Could not reach the ClariMed backend. Make sure the FastAPI server is running on port 8000.');
    } finally {
      setLoading(false);
    }
  };

  const resetAll = () => {
    setResponse(null);
    setStepIndex(0);
    setBodyPart(null);
    setSelectedSymptoms([]);
    setSelectedRedflags([]);
    setTranscript('');
    setImage(null);
    setImagePreview(null);
    setShowHistory(false);
  };

  const openHistory = async () => {
    setShowHistory(true);
    setHistoryLoading(true);
    try {
      const items = await fetchHistory(patientEmail || undefined);
      setHistoryItems(items);
    } catch (err) {
      console.error(err);
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleDownload = async (id: string) => {
    try {
      await downloadReport(id, `ClariMed_Report_${id.slice(0, 8)}.pdf`);
    } catch (err) {
      alert('Could not download the report.');
    }
  };

  if (configError) {
    return (
      <div className="bg-slate-950 text-slate-50 min-h-screen flex items-center justify-center p-6">
        <div className="max-w-md text-center space-y-3">
          <AlertTriangle className="mx-auto text-amber-400" size={32} />
          <p className="text-sm text-slate-400">{configError}</p>
          <button onClick={onBack} className="text-emerald-400 text-sm underline">Go back</button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-950 text-slate-50 min-h-screen flex flex-col justify-between p-6 font-sans">
      <header className="flex justify-between items-center max-w-3xl w-full mx-auto pb-4 border-b border-slate-800">
        <button onClick={onBack} className="text-slate-400 hover:text-white flex items-center gap-1 text-sm transition-colors">
          <ArrowLeft size={16} /> Exit Engine
        </button>
        <div className="flex items-center gap-3">
          <button
            onClick={openHistory}
            disabled={!isOnline}
            title={!isOnline ? 'History sync needs an internet connection' : undefined}
            className="text-xs font-mono text-slate-400 hover:text-emerald-400 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1.5 transition-colors"
          >
            <History size={14} /> History
          </button>
          <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
            {response ? 'Screening Complete' : `Step ${stepIndex + 1} of ${steps.length}`}
          </span>
        </div>
      </header>

      {!isOnline && (
        <div className="max-w-3xl w-full mx-auto mt-4 px-4 py-2.5 bg-amber-500/10 border border-amber-500/20 rounded-xl flex items-center gap-2.5 text-xs text-amber-300">
          <WifiOff size={14} className="shrink-0" />
          <span>You're offline — screening still works fully. Booking, specialist directory sync, and history require internet.</span>
        </div>
      )}

      <main className="max-w-3xl w-full mx-auto py-12 flex-grow flex flex-col justify-center">
        {showHistory ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-bold">Screening History</h2>
              <button onClick={() => setShowHistory(false)} className="text-xs text-slate-400 hover:text-white">Close</button>
            </div>
            {historyLoading ? (
              <Loader2 className="animate-spin text-emerald-400 mx-auto" />
            ) : historyItems.length === 0 ? (
              <p className="text-sm text-slate-500">No past screenings found{patientEmail ? ` for ${patientEmail}` : ''}.</p>
            ) : (
              <div className="space-y-2">
                {historyItems.map((h) => (
                  <div key={h.id} className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 flex justify-between items-center">
                    <div>
                      <p className="text-sm font-medium text-slate-200">
                        {h.top_condition_name || 'Outside coverage'} <span className="text-slate-500">- {h.body_part}</span>
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {new Date(h.created_at).toLocaleString()} {h.top_confidence_pct != null && `- ${h.top_confidence_pct}%`}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`text-[10px] font-mono border px-2 py-0.5 rounded uppercase ${RISK_STYLES[h.risk_level] || RISK_STYLES.yellow}`}>
                        {h.risk_level}
                      </span>
                      <button onClick={() => handleDownload(h.id)} aria-label={`Download report for ${h.top_condition_name || 'this screening'}`} className="text-emerald-400 hover:text-emerald-300">
                        <Download size={16} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        ) : loading ? (
          <div className="text-center space-y-4 py-12">
            <Loader2 className="w-12 h-12 text-emerald-400 animate-spin mx-auto" />
            <p className="text-sm font-mono text-slate-400">Running image analysis + symptom fusion...</p>
          </div>
        ) : response ? (
          <ResultsView
            response={response} onReset={resetAll} onDownload={handleDownload}
            onRetake={() => { setResponse(null); setStepIndex(steps.indexOf('image') >= 0 ? steps.indexOf('image') : steps.length - 1); }}
            isOnline={isOnline} patientName={patientName} patientEmail={patientEmail}
          />
        ) : (
          <AnimatePresence mode="wait">
            {stepId === 'patient' && (
              <motion.div key="patient" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight flex items-center gap-2"><User className="text-emerald-400" size={22} /> Patient Details</h2>
                  <p className="text-slate-400 text-sm mt-1">Used to save your screening history. Stays on your device / local server only.</p>
                </div>
                <div className="space-y-3">
                  <input
                    type="text" placeholder="Full name (optional)" value={patientName}
                    onChange={(e) => setPatientName(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-emerald-600 text-slate-200"
                  />
                  <input
                    type="email" placeholder="Email (optional, used to find your history later)" value={patientEmail}
                    onChange={(e) => setPatientEmail(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-emerald-600 text-slate-200"
                  />
                </div>
              </motion.div>
            )}

            {stepId === 'bodypart' && config && (
              <motion.div key="bodypart" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">Select Affected Area</h2>
                  <p className="text-slate-400 text-sm mt-1">This determines the symptom checklist and conditions screened.</p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {config.body_parts.map((bp) => {
                    const meta = BODY_PART_META[bp];
                    if (!meta) return null;
                    const selected = bodyPart === bp;
                    return (
                      <button
                        key={bp}
                        onClick={() => { setBodyPart(bp); setSelectedSymptoms([]); setSelectedRedflags([]); }}
                        className={`p-4 rounded-xl border-2 flex items-center gap-3 text-left transition-all ${
                          selected ? 'bg-emerald-500/10 border-emerald-500' : 'bg-slate-900/40 border-slate-800/80 hover:border-slate-700'
                        }`}
                      >
                        <span className={selected ? 'text-emerald-400' : 'text-slate-400'}>{meta.icon}</span>
                        <div>
                          <h3 className={`font-semibold text-sm ${selected ? 'text-emerald-400' : 'text-slate-200'}`}>{meta.label}</h3>
                          <p className="text-xs text-slate-500 mt-0.5">{meta.desc}</p>
                        </div>
                        {selected && <CheckCircle2 className="text-emerald-400 ml-auto shrink-0" size={18} />}
                      </button>
                    );
                  })}
                </div>
              </motion.div>
            )}

            {stepId === 'symptoms' && config && bodyPart && (
              <motion.div key="symptoms" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">Select Symptoms</h2>
                  <p className="text-slate-400 text-sm mt-1">Tap all that apply.</p>
                </div>
                <div className="flex flex-wrap gap-2.5">
                  {config.symptoms[bodyPart].map((sym) => (
                    <button
                      key={sym} onClick={() => toggleSymptom(sym)}
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

                {config.redflags[bodyPart]?.length > 0 && (
                  <div className="p-4 bg-red-500/5 border border-red-500/20 rounded-xl space-y-2.5">
                    <p className="text-xs font-mono uppercase tracking-wider text-red-400 flex items-center gap-1.5">
                      <ShieldAlert size={14} /> Any of these right now?
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {config.redflags[bodyPart].map((rf) => (
                        <button
                          key={rf} onClick={() => toggleRedflag(rf)}
                          className={`px-3 py-1.5 text-xs rounded-lg border transition-all ${
                            selectedRedflags.includes(rf)
                              ? 'bg-red-500/20 text-red-300 border-red-500'
                              : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-red-800'
                          }`}
                        >
                          {rf}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="pt-4 border-t border-slate-900">
                  <div className="flex items-center justify-between mb-2">
                    <label className="block text-sm font-medium text-slate-300">Additional notes (optional, voice supported)</label>
                    <select
                      value={voiceLang} onChange={(e) => setVoiceLang(e.target.value)}
                      aria-label="Voice input language"
                      className="bg-slate-900 border border-slate-800 rounded-lg text-xs px-2 py-1 text-slate-400"
                    >
                      {VOICE_LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
                    </select>
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text" value={transcript} onChange={(e) => setTranscript(e.target.value)}
                      placeholder="Describe anything else, or use the mic..."
                      className="flex-grow bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-slate-700 text-slate-300"
                    />
                    <button
                      onClick={handleVoiceInput}
                      aria-label={isListening ? 'Listening...' : 'Start voice input'}
                      className={`p-3 rounded-xl transition-all border ${isListening ? 'bg-red-500/20 text-red-400 border-red-500 animate-pulse' : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'}`}
                    >
                      <Mic size={18} />
                    </button>
                  </div>
                </div>
              </motion.div>
            )}

            {stepId === 'image' && (
              <motion.div key="image" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">Upload a Photo</h2>
                  <p className="text-slate-400 text-sm mt-1">Optional, but improves accuracy. Processed on the server, not sent anywhere else.</p>
                </div>
                <div className="border-2 border-dashed border-slate-800 hover:border-slate-700 transition-colors rounded-2xl p-10 flex flex-col items-center justify-center text-center cursor-pointer relative bg-slate-900/10">
                  <input
                    type="file" accept="image/*" aria-label="Upload a photo of the affected area"
                    onChange={(e) => e.target.files && handleFile(e.target.files[0])}
                    className="absolute inset-0 opacity-0 cursor-pointer"
                  />
                  {imagePreview ? (
                    <img src={imagePreview} alt="preview" className="max-h-48 rounded-lg mb-3" />
                  ) : (
                    <Upload className="text-slate-500 mb-3 w-8 h-8" />
                  )}
                  {image ? (
                    <p className="text-sm text-emerald-400 font-mono">{image.name}</p>
                  ) : (
                    <p className="text-sm text-slate-400">Drag an image here or <span className="text-emerald-400 underline">browse</span></p>
                  )}
                </div>
                <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl flex gap-3">
                  <AlertTriangle className="text-amber-400 shrink-0 w-5 h-5 mt-0.5" />
                  <p className="text-xs text-amber-300/90 leading-normal">
                    Blurry or very dark/bright photos will be rejected automatically with a reason - you'll get a chance to retake it.
                  </p>
                </div>
              </motion.div>
            )}

            {stepId === 'review' && bodyPart && (
              <motion.div key="review" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-4">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">Review & Submit</h2>
                  <p className="text-slate-400 text-sm mt-1">Confirm before running the screening.</p>
                </div>
                <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 space-y-2 text-sm">
                  <p><span className="text-slate-500">Body part:</span> <span className="text-slate-200">{BODY_PART_META[bodyPart].label}</span></p>
                  <p><span className="text-slate-500">Symptoms:</span> <span className="text-slate-200">{selectedSymptoms.join(', ') || 'None selected'}</span></p>
                  {selectedRedflags.length > 0 && (
                    <p><span className="text-red-400">Red flags:</span> <span className="text-red-300">{selectedRedflags.join(', ')}</span></p>
                  )}
                  <p><span className="text-slate-500">Image:</span> <span className="text-slate-200">{image ? image.name : 'Not provided'}</span></p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </main>

      {!response && !loading && !showHistory && (
        <footer className="max-w-xl w-full mx-auto pt-6 border-t border-slate-900 flex justify-between items-center">
          <button
            onClick={goBack} disabled={stepIndex === 0}
            className="text-sm text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-0"
          >
            Previous Step
          </button>
          <button
            onClick={() => (stepId === 'review' ? submitScreeningData() : goNext())}
            disabled={stepId === 'bodypart' && !bodyPart}
            className="bg-slate-100 hover:bg-white disabled:opacity-40 text-slate-950 font-medium px-5 py-2.5 rounded-xl text-sm flex items-center gap-1.5 transition-all shadow-md active:scale-95"
          >
            {stepId === 'review' ? 'Run Screening' : 'Continue'} <ChevronRight size={16} />
          </button>
        </footer>
      )}
    </div>
  );
}

function ResultsView({
  response, onReset, onDownload, onRetake, isOnline, patientName, patientEmail,
}: {
  response: ScreenResponse; onReset: () => void; onDownload: (id: string) => void; onRetake: () => void;
  isOnline: boolean; patientName: string; patientEmail: string;
}) {
  if (response.success === false) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6 text-center py-8">
        <AlertTriangle className="mx-auto text-amber-400" size={40} />
        <h2 className="text-xl font-bold">Image Quality Check Failed</h2>
        <ul className="text-sm text-slate-400 space-y-1">
          {response.issues?.map((i, idx) => <li key={idx}>- {i}</li>)}
        </ul>
        <button onClick={onRetake} className="bg-slate-100 hover:bg-white text-slate-950 font-medium px-5 py-2.5 rounded-xl text-sm">
          Retake Photo
        </button>
      </motion.div>
    );
  }

  const { result, guidance, guidance_source, image, healthcare_network, metadata, screening_id, interpreted_symptoms, routed_specialist } = response;

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
      <div className="flex justify-between items-start border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">
            <FileText className="text-emerald-400" /> Screening Result
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            {result?.out_of_coverage ? 'Outside current knowledge base coverage' : result?.top?.name}
          </p>
        </div>
        {result && (
          <div className="text-right">
            <span className={`inline-block text-[10px] font-mono border px-2.5 py-0.5 rounded uppercase font-semibold tracking-wide ${RISK_STYLES[result.risk_level] || RISK_STYLES.yellow}`}>
              {result.risk_level} risk
            </span>
            {result.top && (
              <p className="text-xs text-emerald-400 font-mono mt-1">{result.top.pct}% - {result.top.confidence_tier}</p>
            )}
          </div>
        )}
      </div>

      {interpreted_symptoms && interpreted_symptoms.length > 0 && (
        <div className="flex items-start gap-2 px-4 py-2.5 bg-slate-900/40 border border-slate-800/60 rounded-xl text-xs text-slate-400">
          <Sparkles size={14} className="text-emerald-400 shrink-0 mt-0.5" />
          <span>Also picked up from your description: <span className="text-slate-300">{interpreted_symptoms.join(', ')}</span></span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4">
          {image?.heatmap_overlay && (
            <div>
              <h3 className="text-xs font-mono tracking-wider uppercase text-slate-400 mb-2">Visual Attention Map</h3>
              <img src={image.heatmap_overlay} alt="heatmap" className="rounded-xl border border-slate-800 w-full" />
              <p className="text-[10px] text-slate-500 mt-1">Heuristic overlay - placeholder for a trained-model Grad-CAM.</p>
            </div>
          )}

          {result && result.candidates.length > 0 && (
            <div>
              <h3 className="text-xs font-mono tracking-wider uppercase text-slate-400 mb-2">Differential</h3>
              <div className="bg-slate-900/50 border border-slate-800/80 rounded-xl p-4 space-y-3">
                {result.candidates.map((c) => (
                  <div key={c.id}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-300">{c.name}</span>
                      <span className="text-emerald-400 font-mono">{c.pct}%</span>
                    </div>
                    <div
                      className="bg-slate-800 rounded-full h-1.5"
                      role="progressbar" aria-valuenow={c.pct} aria-valuemin={0} aria-valuemax={100}
                      aria-label={`${c.name} confidence`}
                    >
                      <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: `${c.pct}%` }} />
                    </div>
                    {c.matched_keywords.length > 0 && (
                      <p className="text-[10px] text-slate-500 mt-1">Matched: {c.matched_keywords.join(', ')}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-mono tracking-wider uppercase text-slate-400">Guidance</h3>
              {guidance_source === 'general_llm_unverified' && (
                <span className="text-[10px] font-mono uppercase tracking-wide text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded flex items-center gap-1">
                  <AlertTriangle size={10} /> General AI info - unverified
                </span>
              )}
              {guidance_source === 'curated_kb' && (
                <span className="text-[10px] font-mono uppercase tracking-wide text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                  Curated knowledge base
                </span>
              )}
            </div>
            <div className={`border rounded-xl p-5 max-h-[380px] overflow-y-auto ${
              guidance_source === 'general_llm_unverified' ? 'bg-amber-500/5 border-amber-500/20' : 'bg-slate-900/50 border-slate-800/80'
            }`}>
              <GuidanceText text={guidance || ''} />
            </div>
          </div>

          {healthcare_network && healthcare_network.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-mono tracking-wider uppercase text-slate-400">Nearby Specialists</h3>
                {routed_specialist && (
                  <span className="text-[10px] font-mono text-emerald-400">{routed_specialist}</span>
                )}
              </div>
              {guidance_source === 'general_llm_unverified' && (
                <p className="text-[10px] text-slate-500 mb-2">
                  Suggested based on your description. This is triage direction, not a diagnosis.
                </p>
              )}
              <div className="space-y-2">
                {healthcare_network.map((clinic, index) => (
                  <div key={index} className="bg-slate-900/30 border border-slate-800/60 p-3 rounded-xl">
                    <div className="flex justify-between items-start">
                      <div>
                        <h4 className="text-sm font-semibold text-slate-200">{clinic.name}</h4>
                        <p className="text-xs text-slate-400 flex items-center gap-1 mt-1">
                          <MapPin size={12} className="text-emerald-400" /> {clinic.clinic} - {clinic.distance}
                        </p>
                      </div>
                      <a href={`tel:${clinic.phone}`} aria-label={`Call ${clinic.name}`} className="text-emerald-400 hover:text-emerald-300">
                        <Phone size={14} />
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {healthcare_network && healthcare_network.length > 0 && (
        <BookingSection
          clinics={healthcare_network} screeningId={screening_id} isOnline={isOnline}
          patientName={patientName} patientEmail={patientEmail}
        />
      )}

      <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-xl text-[10px] text-slate-500 font-mono uppercase tracking-wider text-center">
        {metadata?.regulatory_disclaimer}
      </div>

      <div className="flex gap-3">
        {screening_id && (
          <button
            onClick={() => onDownload(screening_id)}
            className="flex-1 py-3 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 text-emerald-400 rounded-xl text-sm font-medium flex items-center justify-center gap-1.5 transition-colors"
          >
            <Download size={16} /> Download PDF Report
          </button>
        )}
        <button
          onClick={onReset}
          className="flex-1 py-3 bg-slate-800 hover:bg-slate-750 text-white rounded-xl text-sm font-medium transition-colors"
        >
          New Screening
        </button>
      </div>
    </motion.div>
  );
}

const SLOTS = ['Tomorrow · 10:00 AM', 'Tomorrow · 2:00 PM', 'Thu · 11:30 AM', 'Fri · 4:00 PM'];

function BookingSection({
  clinics, screeningId, isOnline, patientName, patientEmail,
}: {
  clinics: Clinic[]; screeningId?: string; isOnline: boolean; patientName: string; patientEmail: string;
}) {
  const [selectedClinic, setSelectedClinic] = useState<Clinic | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [booking, setBooking] = useState(false);
  const [confirmed, setConfirmed] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleBook = async () => {
    if (!selectedClinic || !selectedSlot) return;
    setBooking(true);
    setError(null);
    try {
      const res = await bookAppointment({
        specialistName: selectedClinic.name, slot: selectedSlot, screeningId,
        clinicName: selectedClinic.clinic, patientName, patientEmail,
      });
      setConfirmed(res.appointment_id);
    } catch (err) {
      setError('Could not reach the scheduling system. This action needs an internet connection.');
    } finally {
      setBooking(false);
    }
  };

  if (confirmed) {
    return (
      <div className="p-5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex items-start gap-3">
        <CalendarCheck className="text-emerald-400 shrink-0 mt-0.5" size={20} />
        <div>
          <p className="text-sm font-medium text-emerald-300">Appointment confirmed</p>
          <p className="text-xs text-emerald-400/80 mt-0.5">
            {selectedClinic?.name} · {selectedSlot} · Confirmation ID {confirmed.slice(0, 8)}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-mono tracking-wider uppercase text-slate-400">Book an Appointment</h3>
        {!isOnline && (
          <span className="text-[10px] text-amber-400 flex items-center gap-1"><WifiOff size={11} /> Needs internet</span>
        )}
      </div>
      <div className={`bg-slate-900/50 border border-slate-800/80 rounded-xl p-4 space-y-3 ${!isOnline ? 'opacity-50' : ''}`}>
        <div className="flex flex-wrap gap-2">
          {clinics.map((c) => (
            <button
              key={c.name} disabled={!isOnline}
              onClick={() => setSelectedClinic(c)}
              className={`px-3 py-2 text-xs rounded-lg border text-left transition-all disabled:cursor-not-allowed ${
                selectedClinic?.name === c.name ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500' : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>
        {selectedClinic && (
          <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-800">
            {SLOTS.map((s) => (
              <button
                key={s} disabled={!isOnline}
                onClick={() => setSelectedSlot(s)}
                className={`px-3 py-1.5 text-xs font-mono rounded-lg border transition-all disabled:cursor-not-allowed ${
                  selectedSlot === s ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500' : 'bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {error && <p className="text-xs text-red-400">{error}</p>}
        <button
          onClick={handleBook}
          disabled={!isOnline || !selectedClinic || !selectedSlot || booking}
          className="w-full py-2.5 bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-800 disabled:text-slate-600 text-slate-950 font-medium rounded-lg text-xs flex items-center justify-center gap-1.5 transition-colors disabled:cursor-not-allowed"
        >
          {booking ? <Loader2 size={14} className="animate-spin" /> : <CalendarCheck size={14} />}
          {booking ? 'Booking...' : 'Confirm Appointment'}
        </button>
      </div>
    </div>
  );
}