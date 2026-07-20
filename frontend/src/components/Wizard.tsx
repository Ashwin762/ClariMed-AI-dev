import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Mic, Upload, CheckCircle2, ChevronRight, AlertTriangle, ArrowLeft,
  Loader2, FileText, Phone, MapPin, Download, History, User, Eye,
  Sparkles, Hand, Smile, Activity, ShieldAlert, WifiOff, CalendarCheck,
  Ear, Wind, Utensils, Bone, ShieldCheck, Trash2, Lock, Brain, Droplet, Venus, HeartPulse, Camera,
} from 'lucide-react';
import {
  fetchConfig, submitScreening, fetchHistory, downloadReport, bookAppointment,
  fetchPrivacyPolicy, giveConsent, deleteMyData, suggestBodyPart, suggestSymptomsFromImage,
  guessBodyPartFromImage,
  type BodyPart, type ConfigResponse, type ScreenResponse, type HistoryItem, type Clinic,
  type PrivacyPolicy,
} from '../api';
import { useOnlineStatus } from '../useOnlineStatus';
import { useUserLocation, distanceKm, formatDistance, type UserLocation } from '../useUserLocation';
import MapView from './MapView';
import EmergencyBanner from './EmergencyBanner';
import SystemGrid from './SystemGrid';
import AIScanReveal from './AIScanReveal';
import ReasoningPanel from './ReasoningPanel';
import LanguageSelector from './LanguageSelector';
import { useLanguage } from '../i18n/LanguageContext';

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
  neurological: { label: 'Neurological', icon: <Brain size={20} />, desc: 'Seizures, tremor, memory, stroke signs - no photo needed' },
  urinary: { label: 'Urinary', icon: <Droplet size={20} />, desc: 'UTI, kidney stones, urination changes - no photo needed' },
  reproductive: { label: 'Reproductive Health', icon: <Venus size={20} />, desc: 'Periods, PCOS, pregnancy, menopause - no photo needed' },
  cardiovascular: { label: 'Heart / Circulation', icon: <HeartPulse size={20} />, desc: 'Chest pain, palpitations, blood pressure - no photo needed' },
  general: { label: 'General Health', icon: <Activity size={20} />, desc: 'Fever, fatigue, headache - no photo needed' },
};

// Body parts with no reliable visual sign in a standard photo — the image
// upload step is skipped for these. Mirrors which conditions have no image
// scorer in ai/rules/condition_engine.py.
const NON_PHOTOGRAPHABLE: BodyPart[] = ['general', 'respiratory', 'digestive', 'musculoskeletal', 'neurological', 'urinary', 'reproductive', 'cardiovascular'];

const VOICE_LANGS = [
  { code: 'en-US', label: 'English' },
  { code: 'hi-IN', label: 'Hindi' },
  { code: 'kn-IN', label: 'Kannada' },
  { code: 'ta-IN', label: 'Tamil' },
  { code: 'te-IN', label: 'Telugu' },
  { code: 'bn-IN', label: 'Bengali' },
  { code: 'mr-IN', label: 'Marathi' },
  { code: 'gu-IN', label: 'Gujarati' },
  { code: 'ml-IN', label: 'Malayalam' },
];

const RISK_STYLES: Record<string, string> = {
  green: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  yellow: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  red: 'bg-red-500/10 text-red-400 border-red-500/20',
};

/**
 * When the user's real location is available, override each clinic's
 * static "distance" label with a genuinely computed one and sort nearest
 * first. Without a location, returns the list unchanged (original order,
 * original static labels from the backend) — a graceful no-op, not a
 * broken state.
 */
function sortByDistance<T extends { lat?: number; lng?: number; distance: string }>(
  clinics: T[],
  userLocation: UserLocation | null
): T[] {
  if (!userLocation) return clinics;
  return [...clinics]
    .map((c) => {
      if (c.lat == null || c.lng == null) return { ...c, __km: Infinity };
      const km = distanceKm(userLocation, { lat: c.lat, lng: c.lng });
      return { ...c, distance: formatDistance(km), __km: km };
    })
    .sort((a, b) => a.__km - b.__km);
}

function getStepOrder(bodyPart: BodyPart | null): string[] {
  // 'start' merges the old consent + patient-details + describe steps into one
  // warm first screen: ask what's wrong, capture consent inline, optionally
  // take name/email — then detect the body part from the description.
  const base = ['start', 'bodypart', 'symptoms'];
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
  const { t, language, locale: globalLocale } = useLanguage();
  const isOnline = useOnlineStatus();
  const { location: userLocation, status: locationStatus, requestLocation } = useUserLocation();
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

  // Keep the mic's recognition language in sync with the global language
  // selection by default -- a user who sets Kannada as their language
  // expects to be understood (and answered) in Kannada, not stuck on
  // English speech recognition. Still overridable via the dropdown itself
  // for the rarer case of wanting a different spoken language than the
  // rest of the UI.
  useEffect(() => {
    setVoiceLang(globalLocale);
  }, [globalLocale]);
  const [isListening, setIsListening] = useState(false);
  const [image, setImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<ScreenResponse | null>(null);

  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [policy, setPolicy] = useState<PrivacyPolicy | null>(null);
  const [consentChecked, setConsentChecked] = useState(false);
  const [consentGiven, setConsentGiven] = useState(false);
  const [initialDescription, setInitialDescription] = useState('');
  const [suggestedBodyPart, setSuggestedBodyPart] = useState<BodyPart | null>(null);
  const [suggestionSource, setSuggestionSource] = useState<'text' | 'image' | null>(null);
  const [scanningFile, setScanningFile] = useState<File | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestingFromImage, setSuggestingFromImage] = useState(false);
  const [imageSuggestionInfo, setImageSuggestionInfo] = useState<{ names: string[]; count: number } | null>(null);
  const [imageSuggestionError, setImageSuggestionError] = useState('');
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchPrivacyPolicy().then(setPolicy).catch(() => {});
  }, []);

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
        transcript, language, patientName, patientEmail, file: image, consentGiven,
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
    // Back to the first screen for a fresh screening. Consent was already
    // recorded server-side this session; the checkbox stays ticked so the
    // patient isn't re-gated, but they can edit their new description.
    setStepIndex(0);
    setBodyPart(null);
    setSelectedSymptoms([]);
    setSelectedRedflags([]);
    setTranscript('');
    setImage(null);
    setImagePreview(null);
    setShowHistory(false);
    setInitialDescription('');
    setSuggestedBodyPart(null);
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

  const handleSuggestFromImage = async (file: File) => {
    if (!bodyPart) return;
    setSuggestingFromImage(true);
    setImageSuggestionError('');
    setImageSuggestionInfo(null);
    try {
      const result = await suggestSymptomsFromImage(bodyPart, file);
      if (!result.success) {
        setImageSuggestionError(result.message || 'Could not read that photo — try a clearer one, or skip this.');
        return;
      }
      if (result.suggested_symptoms.length === 0) {
        setImageSuggestionError("Didn't find a strong enough match from the photo — please select your symptoms below.");
        return;
      }
      // Pre-fill: merge into whatever's already selected, never replace or
      // uncheck anything the patient already picked themselves.
      setSelectedSymptoms((prev) => {
        const merged = [...prev];
        for (const s of result.suggested_symptoms) {
          if (!merged.includes(s)) merged.push(s);
        }
        return merged;
      });
      setImageSuggestionInfo({
        names: result.based_on_conditions.map((c) => c.name),
        count: result.suggested_symptoms.length,
      });
    } catch (e) {
      setImageSuggestionError(e instanceof Error ? e.message : 'Could not analyze that photo.');
    } finally {
      setSuggestingFromImage(false);
    }
  };

  const handleStartContinue = async () => {
    // 1) Record consent for audit (same backend call as before). We block on
    //    failure rather than silently proceeding without a consent record.
    if (!consentGiven) {
      try {
        await giveConsent(patientEmail);
      } catch {
        alert('Could not record consent with the server. Please try again.');
        return;
      }
      setConsentGiven(true);
    }

    // 2) Detect body part from the free-text description, if any was given.
    const text = initialDescription.trim();
    if (!text) {
      goNext();
      return;
    }
    setSuggesting(true);
    try {
      const suggestion = await suggestBodyPart(text);
      // Pre-select, never force — the grid on the next step is overridable.
      setSuggestedBodyPart(suggestion);
      setSuggestionSource('text');
      setBodyPart(suggestion);
      setSelectedSymptoms([]);
      setSelectedRedflags([]);
    } catch {
      setSuggestedBodyPart(null);
    } finally {
      setSuggesting(false);
      goNext();
    }
  };

  const handleDeleteMyData = async () => {
    if (!patientEmail) {
      alert('Enter the email you used for screenings first.');
      return;
    }
    if (!window.confirm(`Permanently delete all ClariMed records for ${patientEmail}? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      const res = await deleteMyData(patientEmail);
      const d = res.deleted;
      alert(`Deleted ${d.screenings_deleted} screening(s), ${d.appointments_deleted} appointment(s), ${d.consents_deleted} consent record(s).`);
      setHistoryItems([]);
    } catch {
      alert('Could not delete your data. Please try again.');
    } finally {
      setDeleting(false);
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
          <LanguageSelector />
          <button
            onClick={openHistory}
            disabled={!isOnline}
            title={!isOnline ? 'History sync needs an internet connection' : undefined}
            className="text-xs font-mono text-slate-400 hover:text-emerald-400 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1.5 transition-colors"
          >
            <History size={14} /> History
          </button>
          <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
            {response ? t('wizard_results_heading') : `Step ${stepIndex + 1} of ${steps.length}`}
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
                        {new Date(h.created_at).toLocaleString()} {h.confidence_tier && `- ${h.confidence_tier}`}
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
            userLocation={userLocation} locationStatus={locationStatus} requestLocation={requestLocation}
          />
        ) : (
          <AnimatePresence mode="wait">
            {stepId === 'start' && (
              <motion.div key="start" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-5">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">{t('wizard_start_heading')}</h2>
                  <p className="text-slate-400 text-sm mt-1">
                    {t('wizard_start_subheading')}
                  </p>
                </div>

                <textarea
                  value={initialDescription}
                  onChange={(e) => setInitialDescription(e.target.value)}
                  placeholder={t('wizard_start_placeholder')}
                  rows={4}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-emerald-600 text-slate-200 resize-none"
                />

                <div className="flex items-center gap-3">
                  <div className="h-px flex-1 bg-slate-800" />
                  <span className="text-[10px] text-slate-600 uppercase tracking-wider">or</span>
                  <div className="h-px flex-1 bg-slate-800" />
                </div>

                {scanningFile ? (
                  <AIScanReveal
                    file={scanningFile}
                    onResolved={(bp, _confidence) => {
                      if (bp) {
                        setSuggestedBodyPart(bp);
                        setSuggestionSource('image');
                        setBodyPart(bp);
                        setSelectedSymptoms([]);
                        setSelectedRedflags([]);
                      }
                      setScanningFile(null);
                      goNext();
                    }}
                    onCancel={() => setScanningFile(null)}
                  />
                ) : (
                  <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl space-y-2.5">
                    <label className="flex items-center gap-2 text-xs font-medium text-slate-300 cursor-pointer">
                      <Camera size={14} className="text-emerald-400" />
                      {t('wizard_start_photo_cta')}
                      <input
                        type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                        onChange={(e) => { const f = e.target.files?.[0]; if (f) setScanningFile(f); e.target.value = ''; }}
                      />
                    </label>
                    <p className="text-[10px] text-slate-600">This photo is analyzed instantly and never stored.</p>
                  </div>
                )}

                {/* Optional identity — folded in so it isn't its own step. */}
                <details className="group">
                  <summary className="text-xs text-slate-500 hover:text-slate-300 cursor-pointer list-none flex items-center gap-1.5">
                    <ChevronRight size={12} className="group-open:rotate-90 transition-transform" />
                    Add your name to save this screening (optional)
                  </summary>
                  <div className="space-y-2 mt-3">
                    <input
                      type="text" placeholder="Full name (optional)" value={patientName}
                      onChange={(e) => setPatientName(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-emerald-600 text-slate-200"
                    />
                    <input
                      type="email" placeholder="Email (optional, to find your history later)" value={patientEmail}
                      onChange={(e) => setPatientEmail(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-emerald-600 text-slate-200"
                    />
                    {patientEmail && (
                      <button
                        onClick={handleDeleteMyData}
                        disabled={deleting}
                        className="text-xs text-red-400/80 hover:text-red-400 flex items-center gap-1.5 transition-colors disabled:opacity-50"
                      >
                        {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                        Delete all my ClariMed data for this email
                      </button>
                    )}
                  </div>
                </details>

                {/* Consent — condensed to a plain-language summary + one checkbox,
                    with the full policy one tap away for anyone who wants it. */}
                <div className="p-4 bg-emerald-500/5 border border-emerald-500/20 rounded-xl space-y-2">
                  <div className="flex items-center gap-2 text-emerald-300">
                    <Lock size={13} />
                    <span className="text-xs font-mono uppercase tracking-wider">Before we start</span>
                  </div>
                  <ul className="space-y-1.5 text-xs text-slate-300">
                    <li className="flex gap-2"><ShieldCheck size={14} className="text-emerald-400 shrink-0 mt-0.5" /> Your images are analyzed live and never stored.</li>
                    <li className="flex gap-2"><ShieldCheck size={14} className="text-emerald-400 shrink-0 mt-0.5" /> This is preliminary screening — not a medical diagnosis.</li>
                    <li className="flex gap-2"><ShieldCheck size={14} className="text-emerald-400 shrink-0 mt-0.5" /> You can view or delete your data at any time.</li>
                  </ul>
                  {policy && (
                    <details className="pt-1">
                      <summary className="text-[11px] text-slate-500 hover:text-slate-300 cursor-pointer">Read the full privacy details</summary>
                      <div className="mt-2 space-y-2 text-xs text-slate-400">
                        <p>{policy.image_handling}</p>
                        <p className="text-amber-300/80">{policy.scope_limitation}</p>
                        <div>
                          <p className="text-slate-500 mb-1">What we store:</p>
                          <ul className="space-y-1">{policy.what_we_store.map((s, i) => <li key={i} className="flex gap-2"><span className="text-slate-600">-</span>{s}</li>)}</ul>
                        </div>
                        <div>
                          <p className="text-slate-500 mb-1">Your rights:</p>
                          <ul className="space-y-1">{policy.your_rights.map((s, i) => <li key={i} className="flex gap-2"><span className="text-slate-600">-</span>{s}</li>)}</ul>
                        </div>
                      </div>
                    </details>
                  )}
                </div>

                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox" checked={consentChecked}
                    onChange={(e) => setConsentChecked(e.target.checked)}
                    className="mt-0.5 accent-emerald-500 w-4 h-4 shrink-0"
                  />
                  <span className="text-sm text-slate-300">I understand and I'm ready to start.</span>
                </label>

                <button
                  onClick={() => { setInitialDescription(''); handleStartContinue(); }}
                  disabled={!consentChecked}
                  className="text-xs text-slate-500 hover:text-slate-300 disabled:opacity-40 transition-colors"
                >
                  Skip describing — I'll pick the body area myself
                </button>
              </motion.div>
            )}

            {stepId === 'bodypart' && config && (
              <motion.div key="bodypart" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">{t('wizard_bodypart_heading')}</h2>
                  <p className="text-slate-400 text-sm mt-1">{t('wizard_bodypart_subheading')}</p>
                  {suggestedBodyPart && bodyPart === suggestedBodyPart && (
                    <p className="text-xs text-emerald-400 mt-2">
                      {suggestionSource === 'image' ? 'Picked from your photo' : 'Picked from your description'} — tap a different area to change it.
                    </p>
                  )}
                </div>

                <SystemGrid
                  parts={config.body_parts}
                  meta={BODY_PART_META}
                  selected={bodyPart}
                  onSelect={(bp) => { setBodyPart(bp); setSelectedSymptoms([]); setSelectedRedflags([]); }}
                />
              </motion.div>
            )}

            {stepId === 'symptoms' && config && bodyPart && (
              <motion.div key="symptoms" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="space-y-6">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight">{t('wizard_symptoms_heading')}</h2>
                  <p className="text-slate-400 text-sm mt-1">{t('wizard_symptoms_subheading')}</p>
                </div>

                {!NON_PHOTOGRAPHABLE.includes(bodyPart) && (
                  <div className="p-4 bg-slate-900/60 border border-slate-800 rounded-xl space-y-2.5">
                    <label className="flex items-center gap-2 text-xs font-medium text-slate-300 cursor-pointer">
                      <Camera size={14} className="text-emerald-400" />
                      {t('wizard_symptoms_photo_cta')}
                      <input
                        type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleSuggestFromImage(f); e.target.value = ''; }}
                      />
                    </label>
                    {suggestingFromImage && (
                      <p className="text-xs text-slate-500 flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Reading your photo...</p>
                    )}
                    {imageSuggestionInfo && (
                      <p className="text-xs text-emerald-400">
                        Picked {imageSuggestionInfo.count} symptom{imageSuggestionInfo.count !== 1 ? 's' : ''} from your photo
                        {imageSuggestionInfo.names.length > 0 && <> (based on patterns matching {imageSuggestionInfo.names.join(', ')})</>} — review below, uncheck anything that doesn't apply.
                      </p>
                    )}
                    {imageSuggestionError && (
                      <p className="text-xs text-amber-400">{imageSuggestionError}</p>
                    )}
                    <p className="text-[10px] text-slate-600">This photo is analyzed instantly and never stored — you'll still upload a photo separately for the actual screening.</p>
                  </div>
                )}

                <div className="flex flex-wrap gap-2.5">
                  {(config.symptoms[bodyPart] ?? []).map((sym) => (
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

                {(config.symptoms[bodyPart] ?? []).length === 0 && (
                  <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl text-xs text-amber-300">
                    No symptom list returned by the backend for "{bodyPart}". The backend may be running an older
                    version — restart it so it picks up the latest condition_engine.py.
                  </div>
                )}

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
            {t('wizard_back_button')}
          </button>
          <button
            onClick={() => {
              if (stepId === 'start') return handleStartContinue();
              if (stepId === 'review') return submitScreeningData();
              goNext();
            }}
            disabled={
              (stepId === 'start' && (!consentChecked || !policy || suggesting)) ||
              (stepId === 'bodypart' && !bodyPart)
            }
            className="bg-slate-100 hover:bg-white disabled:opacity-40 text-slate-950 font-medium px-5 py-2.5 rounded-xl text-sm flex items-center gap-1.5 transition-all shadow-md active:scale-95"
          >
            {suggesting && stepId === 'start' ? (
              <><Loader2 size={16} className="animate-spin" /> Reading your description...</>
            ) : (
              <>{stepId === 'start' ? t('wizard_start_button') : stepId === 'review' ? t('wizard_run_screening_button') : t('wizard_continue_button')} <ChevronRight size={16} /></>
            )}
          </button>
        </footer>
      )}
    </div>
  );
}

function ResultsView({
  response, onReset, onDownload, onRetake, isOnline, patientName, patientEmail,
  userLocation, locationStatus, requestLocation,
}: {
  response: ScreenResponse; onReset: () => void; onDownload: (id: string) => void; onRetake: () => void;
  isOnline: boolean; patientName: string; patientEmail: string;
  userLocation: UserLocation | null; locationStatus: string; requestLocation: () => void;
}) {
  const { t } = useLanguage();

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

  const { result, guidance, guidance_source, image, healthcare_network, screening_id, interpreted_symptoms, interpreted_redflags, vision_detected_symptoms, vision_other_observations, routed_specialist, emergency } = response;

  return (
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
      {emergency?.is_emergency && (
        <EmergencyBanner
          emergency={emergency} riskReason={result?.risk_reason || 'A red-flag symptom was reported.'}
          screeningId={screening_id} patientName={patientName}
          interpretedRedflags={interpreted_redflags}
          userLocation={userLocation} locationStatus={locationStatus} requestLocation={requestLocation}
        />
      )}

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
              <p className="text-xs text-emerald-400 font-mono mt-1">{result.top.match_strength}</p>
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

      {vision_detected_symptoms && vision_detected_symptoms.length > 0 && (
        <div className="flex items-start gap-2 px-4 py-2.5 bg-emerald-500/5 border border-emerald-500/20 rounded-xl text-xs text-slate-400">
          <Camera size={14} className="text-emerald-400 shrink-0 mt-0.5" />
          <span>Detected directly from your photo: <span className="text-emerald-300">{vision_detected_symptoms.join(', ')}</span></span>
        </div>
      )}

      {vision_other_observations && (
        <div className="flex items-start gap-2 px-4 py-2 text-[11px] text-slate-500 italic">
          <Eye size={12} className="text-slate-600 shrink-0 mt-0.5" />
          <span>
            Also noted from your photo, outside our standard checklist (not used in the assessment above,
            shared with your doctor for reference): "{vision_other_observations}"
          </span>
        </div>
      )}

      {/* Guidance and next steps are ordered FIRST — what the patient should
          do matters more than the list of what it might be. */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4 order-2 md:order-1">
          {result && result.top && (
            <ReasoningPanel top={result.top} evidence={result.evidence} rankingReliable={result.ranking_reliable} />
          )}

          {image?.heatmap_overlay && (
            <div>
              <h3 className="text-xs font-mono tracking-wider uppercase text-slate-400 mb-2">Visual Attention Map</h3>
              <img src={image.heatmap_overlay} alt="heatmap" className="rounded-xl border border-slate-800 w-full" />
              <p className="text-[10px] text-slate-500 mt-1">Heuristic overlay - placeholder for a trained-model Grad-CAM.</p>
            </div>
          )}

          {image?.relevance_warning && (
            <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl flex items-start gap-2">
              <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-300">{image.relevance_warning}</p>
            </div>
          )}

          {result && result.candidates.length > 0 && (
            <div>
              <h3 className="text-xs font-mono tracking-wider uppercase text-slate-400 mb-2">
                {result.ranking_reliable ? 'Differential' : 'Conditions That Share Your Symptoms'}
              </h3>

              {/* Evidence basis — tells the patient WHY the result is uncertain */}
              <div className="mb-2 px-3 py-2 bg-slate-900/40 border border-slate-800/60 rounded-lg text-[10px] text-slate-500">
                Based on {result.evidence.symptoms_reported} symptom
                {result.evidence.symptoms_reported === 1 ? '' : 's'}
                {result.evidence.image_provided ? ' and an uploaded image' : ' and no image'}
                {' · '}
                {result.evidence.candidates_considered} condition
                {result.evidence.candidates_considered === 1 ? '' : 's'} considered
              </div>

              {!result.ranking_reliable && (
                <div className="mb-2 px-3 py-2.5 bg-slate-900/40 border border-slate-800/60 rounded-lg text-[11px] text-slate-400 leading-relaxed">
                  There isn't enough information to rank these confidently. They're listed as conditions
                  that share your symptoms — <span className="text-slate-300">not in order of likelihood</span>.
                  Adding more symptoms{!result.evidence.image_provided && ' or a photo'} would sharpen this.
                </div>
              )}

              <div className="bg-slate-900/50 border border-slate-800/80 rounded-xl p-4 space-y-3">
                {result.candidates.map((c) => (
                  <div key={c.id}>
                    <div className="flex justify-between items-center text-xs mb-1">
                      <span className="text-slate-300">{c.name}</span>
                      <span className="text-slate-500 font-mono text-[10px]">{c.match_strength}</span>
                    </div>
                    {result.ranking_reliable && (
                      <div
                        className="bg-slate-800 rounded-full h-1.5"
                        role="progressbar" aria-valuenow={Math.round(c.strength_raw * 100)}
                        aria-valuemin={0} aria-valuemax={100}
                        aria-label={`${c.name} match strength`}
                      >
                        <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: `${Math.round(c.strength_raw * 100)}%` }} />
                      </div>
                    )}
                    {c.matched_keywords.length > 0 && (
                      <p className="text-[10px] text-slate-500 mt-1">Matched: {c.matched_keywords.join(', ')}</p>
                    )}
                  </div>
                ))}
              </div>

              <p className="text-[10px] text-slate-600 mt-2 leading-relaxed">
                "Match strength" means how closely your symptoms and image fit each condition — it is
                <span className="text-slate-500"> not the chance that you have it</span>.
              </p>
            </div>
          )}
        </div>

        <div className="space-y-4 order-1 md:order-2">
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

              {!userLocation && (
                <button
                  onClick={requestLocation}
                  disabled={locationStatus === 'requesting'}
                  className="mb-3 text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1.5 disabled:opacity-50"
                >
                  <MapPin size={12} />
                  {locationStatus === 'requesting' ? 'Getting your location...' :
                   locationStatus === 'denied' ? 'Location permission denied - showing estimated distances' :
                   locationStatus === 'timeout' ? "Couldn't get a location fix in time - tap to try again" :
                   locationStatus === 'unavailable' ? 'Location signal unavailable right now - tap to retry' :
                   locationStatus === 'unsupported' ? 'Location not supported on this device' :
                   'Use my location for accurate distances'}
                </button>
              )}

              <div className="mb-3">
                <MapView clinics={healthcare_network} userLocation={userLocation} />
              </div>
              <div className="space-y-2">
                {sortByDistance(healthcare_network, userLocation).map((clinic, index) => (
                  <div key={index} className="bg-slate-900/30 border border-slate-800/60 p-3 rounded-xl">
                    <div className="flex justify-between items-start">
                      <div>
                        <h4 className="text-sm font-semibold text-slate-200">{clinic.name}</h4>
                        <p className="text-xs text-slate-400 flex items-center gap-1 mt-1">
                          <MapPin size={12} className="text-emerald-400" /> {clinic.clinic} - {clinic.distance}
                          {userLocation && <span className="text-emerald-500/70">{' '}(live)</span>}
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
        {t('wizard_disclaimer')}
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