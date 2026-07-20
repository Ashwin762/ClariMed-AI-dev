// frontend/src/components/Chat.tsx
import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send, Camera, Loader2, ShieldCheck, Sparkles, AlertTriangle,
  ArrowLeft, Phone, MapPin, Lock, Mic, Volume2, VolumeX, Globe,
} from 'lucide-react';
import {
  sendChatTurn, fetchPrivacyPolicy, giveConsent, fetchLanguages,
  type ChatMessage, type ChatResultResponse, type BodyPart, type PrivacyPolicy, type SupportedLanguage,
} from '../api';
import { isSpeechRecognitionSupported, isSpeechSynthesisSupported, startListening, speak, stopSpeaking } from '../speech';
import Logo from './Logo';
import ReasoningPanel from './ReasoningPanel';
import LanguageSelector from './LanguageSelector';
import { useLanguage } from '../i18n/LanguageContext';

type ThreadItem =
  | { kind: 'text'; role: 'user' | 'assistant'; content: string; imagePreview?: string }
  | { kind: 'result'; data: ChatResultResponse };

const EASE = [0.16, 1, 0.3, 1] as const;

export default function Chat({ onBack }: { onBack: () => void }) {
  const { language, setLanguage, languages, locale, t } = useLanguage();

  const [consentGiven, setConsentGiven] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [policy, setPolicy] = useState<PrivacyPolicy | null>(null);
  const [patientEmail, setPatientEmail] = useState('');

  const [listening, setListening] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(false);

  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [bodyPart, setBodyPart] = useState<BodyPart | null>(null);
  const [input, setInput] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [pendingPreview, setPendingPreview] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [finished, setFinished] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchPrivacyPolicy().then(setPolicy).catch(() => {});
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [thread, sending]);

  useEffect(() => {
    if (consentGiven && thread.length === 0) {
      setThread([{
        kind: 'text', role: 'assistant',
        content: t('chat_welcome'),
      }]);
    }
  }, [consentGiven, t]);

  const [voiceNotice, setVoiceNotice] = useState('');

  const handleSpeak = async (text: string, locale: string) => {
    const status = await speak(text, locale);
    if (status === 'no_voice') {
      const label = languages[language]?.label || locale;
      setVoiceNotice(
        `Your device doesn't have a ${label} voice installed for reading text aloud — this is a browser/OS limitation, not a ClariMed issue. The text above is still accurate.`
      );
      setTimeout(() => setVoiceNotice(''), 6000);
    }
  };

  // Auto-speak the latest assistant message, if enabled. Only fires for
  // genuinely new text-type messages, never re-reads on unrelated re-renders.
  const lastSpokenRef = useRef<number>(-1);
  useEffect(() => {
    if (!autoSpeak || thread.length === 0) return;
    const lastIndex = thread.length - 1;
    const last = thread[lastIndex];
    if (lastIndex === lastSpokenRef.current) return;
    if (last.kind === 'text' && last.role === 'assistant') {
      handleSpeak(last.content, locale);
      lastSpokenRef.current = lastIndex;
    } else if (last.kind === 'result' && last.data.guidance) {
      handleSpeak(last.data.guidance, locale);
      lastSpokenRef.current = lastIndex;
    }
  }, [thread, autoSpeak, language, languages]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleStartChat = async () => {
    try {
      await giveConsent(patientEmail);
    } catch {
      alert('Could not record consent with the server. Please try again.');
      return;
    }
    setConsentGiven(true);
  };

  const handleFileSelect = (f: File) => {
    setPendingFile(f);
    setPendingPreview(URL.createObjectURL(f));
  };

  const handleMicPress = () => {
    if (listening) return;
    setListening(true);
    startListening(
      locale,
      (text) => setInput((prev) => (prev ? `${prev} ${text}` : text)),
      () => setListening(false),
      (message) => setError(message)
    );
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text && !pendingFile) return;
    if (finished || sending) return;

    const userMessages: ChatMessage[] = [
      ...thread.filter((t): t is Extract<ThreadItem, { kind: 'text' }> => t.kind === 'text')
        .map((t) => ({ role: t.role, content: t.content })),
      { role: 'user', content: text || '(shared a photo)' },
    ];

    setThread((prev) => [...prev, {
      kind: 'text', role: 'user', content: text || '(shared a photo)',
      imagePreview: pendingPreview || undefined,
    }]);
    setInput('');
    const fileToSend = pendingFile;
    setPendingFile(null);
    setPendingPreview(null);
    setSending(true);
    setError('');

    try {
      const result = await sendChatTurn({
        messages: userMessages,
        bodyPart,
        language,
        patientEmail,
        consentGiven: true,
        file: fileToSend,
      });

      if (result.type === 'question') {
        if (result.body_part) setBodyPart(result.body_part);
        setThread((prev) => [...prev, { kind: 'text', role: 'assistant', content: result.message }]);
      } else {
        setThread((prev) => [...prev, { kind: 'result', data: result }]);
        setFinished(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Please try again.');
    } finally {
      setSending(false);
    }
  };

  const handleStartOver = () => {
    setThread([]);
    setBodyPart(null);
    setFinished(false);
    setError('');
  };

  if (!consentGiven) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center px-4">
        <motion.div
          initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }}
          className="w-full max-w-md"
        >
          <div className="flex items-center gap-3 mb-6">
            <Logo size={40} />
            <div>
              <h1 className="font-display text-lg font-bold text-slate-100">Chat with ClariMed AI</h1>
              <p className="text-xs text-slate-500">A natural conversation, same trusted screening underneath</p>
            </div>
          </div>

          <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-6 space-y-4">
            <div className="p-4 bg-emerald-500/5 border border-emerald-500/20 rounded-xl space-y-2">
              <div className="flex items-center gap-2 text-emerald-300">
                <Lock size={13} />
                <span className="text-xs font-mono uppercase tracking-wider">{t('chat_before_we_start')}</span>
              </div>
              <ul className="space-y-1.5 text-xs text-slate-300">
                <li className="flex gap-2"><ShieldCheck size={14} className="text-emerald-400 shrink-0 mt-0.5" /> Any photos you share are analyzed live and never stored.</li>
                <li className="flex gap-2"><ShieldCheck size={14} className="text-emerald-400 shrink-0 mt-0.5" /> This is preliminary screening — not a medical diagnosis.</li>
                <li className="flex gap-2"><ShieldCheck size={14} className="text-emerald-400 shrink-0 mt-0.5" /> You can view or delete your data at any time.</li>
              </ul>
              {policy && (
                <details className="pt-1">
                  <summary className="text-[11px] text-slate-500 hover:text-slate-300 cursor-pointer">Read the full privacy details</summary>
                  <div className="mt-2 space-y-2 text-xs text-slate-400">
                    <p>{policy.image_handling}</p>
                    <p className="text-amber-300/80">{policy.scope_limitation}</p>
                  </div>
                </details>
              )}
            </div>

            {Object.keys(languages).length > 0 && (
              <div>
                <label className="flex items-center gap-1.5 text-xs text-slate-400 mb-1.5">
                  <Globe size={12} /> Preferred language
                </label>
                <LanguageSelector className="w-full [&>select]:flex-1" />
                <p className="text-[10px] text-slate-600 mt-1">You can speak or type in this language — replies will come back in it too.</p>
              </div>
            )}

            <input
              type="email" placeholder="Email (optional, to save this conversation)" value={patientEmail}
              onChange={(e) => setPatientEmail(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-emerald-600 text-slate-200"
            />

            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox" checked={consentChecked}
                onChange={(e) => setConsentChecked(e.target.checked)}
                className="mt-0.5 accent-emerald-500 w-4 h-4 shrink-0"
              />
              <span className="text-sm text-slate-300">{t('chat_consent_ready')}</span>
            </label>

            <button
              onClick={handleStartChat}
              disabled={!consentChecked || !policy}
              className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-slate-950 font-semibold py-3 rounded-xl text-sm transition-all active:scale-[0.98]"
            >
              {t('chat_start_chatting_button')}
            </button>
          </div>

          <button onClick={onBack} className="w-full mt-4 text-xs text-slate-600 hover:text-slate-400 flex items-center justify-center gap-1.5">
            <ArrowLeft size={12} /> Back
          </button>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <AnimatePresence>
        {voiceNotice && (
          <motion.div
            initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }}
            className="fixed top-16 left-1/2 -translate-x-1/2 z-50 max-w-sm px-4 py-2.5 bg-amber-500/15 border border-amber-500/30 rounded-xl text-xs text-amber-200 shadow-xl"
          >
            {voiceNotice}
          </motion.div>
        )}
      </AnimatePresence>
      <header className="shrink-0 border-b border-slate-800/60 backdrop-blur-xl bg-slate-950/70 px-4 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2.5">
          <Logo size={28} />
          <div>
            <p className="text-sm font-semibold text-slate-100">ClariMed AI</p>
            {bodyPart && <p className="text-[10px] text-slate-500 font-mono uppercase tracking-wider">{bodyPart}</p>}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {isSpeechSynthesisSupported() && (
            <button
              onClick={() => { if (autoSpeak) stopSpeaking(); setAutoSpeak((v) => !v); }}
              title={autoSpeak ? 'Auto-read replies aloud: on' : 'Auto-read replies aloud: off'}
              className={`p-1.5 rounded-lg transition-colors ${autoSpeak ? 'text-emerald-400 bg-emerald-500/10' : 'text-slate-500 hover:text-slate-300'}`}
            >
              {autoSpeak ? <Volume2 size={15} /> : <VolumeX size={15} />}
            </button>
          )}
          {languages[language] && (
            <span className="text-[10px] text-slate-500 font-mono uppercase tracking-wider flex items-center gap-1">
              <Globe size={10} /> {languages[language].label}
            </span>
          )}
          <button onClick={onBack} className="text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1.5">
            <ArrowLeft size={12} /> {t('chat_exit')}
          </button>
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-5 space-y-4 max-w-2xl w-full mx-auto">
        {thread.map((item, i) => (
          <ThreadBubble key={i} item={item} locale={locale} onSpeak={handleSpeak} />
        ))}

        {sending && (
          <div className="flex items-center gap-2 text-slate-500 text-xs pl-1">
            <Loader2 size={13} className="animate-spin" /> ClariMed AI is thinking...
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 px-4 py-2.5 bg-red-500/10 border border-red-500/20 rounded-xl text-xs text-red-300">
            <AlertTriangle size={14} className="shrink-0 mt-0.5" /> {error}
          </div>
        )}

        {finished && (
          <div className="flex justify-center pt-2">
            <button
              onClick={handleStartOver}
              className="text-xs bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 px-4 py-2 rounded-lg transition-colors"
            >
              {t('chat_start_new')}
            </button>
          </div>
        )}
      </div>

      {!finished && (
        <div className="shrink-0 border-t border-slate-800/60 bg-slate-950/90 backdrop-blur-xl px-4 py-3">
          <div className="max-w-2xl mx-auto">
            {pendingPreview && (
              <div className="mb-2 flex items-center gap-2">
                <img src={pendingPreview} alt="attached" className="w-12 h-12 rounded-lg object-cover border border-slate-700" />
                <button
                  onClick={() => { setPendingFile(null); setPendingPreview(null); }}
                  className="text-[11px] text-slate-500 hover:text-slate-300"
                >
                  Remove photo
                </button>
              </div>
            )}
            <div className="flex items-end gap-2 bg-slate-900 border border-slate-800 rounded-2xl px-3 py-2 focus-within:border-emerald-600 transition-colors">
              <label className="shrink-0 p-1.5 text-slate-500 hover:text-emerald-400 cursor-pointer transition-colors">
                <Camera size={18} />
                <input
                  type="file" accept="image/jpeg,image/png,image/webp" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); e.target.value = ''; }}
                />
              </label>
              {isSpeechRecognitionSupported() && (
                <button
                  onClick={handleMicPress}
                  disabled={listening}
                  title="Speak instead of typing"
                  className={`shrink-0 p-1.5 rounded-lg transition-colors ${listening ? 'text-red-400 animate-pulse' : 'text-slate-500 hover:text-emerald-400'}`}
                >
                  <Mic size={18} />
                </button>
              )}
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                placeholder={listening ? t('chat_listening_placeholder') : t('chat_input_placeholder')}
                rows={1}
                className="flex-1 bg-transparent text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none resize-none py-1.5 max-h-32"
              />
              <button
                onClick={handleSend}
                disabled={sending || (!input.trim() && !pendingFile)}
                className="shrink-0 p-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-30 disabled:hover:bg-emerald-500 text-slate-950 rounded-xl transition-all active:scale-95"
              >
                <Send size={15} />
              </button>
            </div>
            <p className="text-[10px] text-slate-600 text-center mt-2">
              AI-assisted preliminary screening only. Not a medical diagnosis.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function ThreadBubble({ item, locale, onSpeak }: { item: ThreadItem; locale: string; onSpeak: (text: string, locale: string) => void }) {
  if (item.kind === 'result') {
    return <ResultCard data={item.data} locale={locale} onSpeak={onSpeak} />;
  }

  const isUser = item.role === 'user';
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} items-end gap-1.5`}
    >
      <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
        isUser ? 'bg-emerald-500 text-slate-950 font-medium' : 'bg-slate-900 border border-slate-800 text-slate-200'
      }`}>
        {item.imagePreview && (
          <img src={item.imagePreview} alt="shared" className="rounded-lg mb-2 max-w-full max-h-48 object-cover" />
        )}
        {item.content}
      </div>
      {!isUser && isSpeechSynthesisSupported() && (
        <button
          onClick={() => onSpeak(item.content, locale)}
          title="Listen"
          className="shrink-0 p-1 text-slate-600 hover:text-emerald-400 transition-colors"
        >
          <Volume2 size={13} />
        </button>
      )}
    </motion.div>
  );
}

const RISK_STYLES: Record<string, { label: string; cls: string }> = {
  red: { label: 'Needs urgent attention', cls: 'bg-red-500/15 text-red-300 border-red-500/40' },
  yellow: { label: 'Worth getting checked', cls: 'bg-amber-500/15 text-amber-300 border-amber-500/40' },
  green: { label: 'Likely routine', cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40' },
};

function ResultCard({ data, locale, onSpeak }: { data: ChatResultResponse; locale: string; onSpeak: (text: string, locale: string) => void }) {
  const risk = RISK_STYLES[data.metadata?.risk_level || 'yellow'];
  const isEmergency = data.emergency?.is_emergency;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE }}
      className="w-full space-y-3"
    >
      {isEmergency && (
        <div className="p-4 bg-red-500/10 border border-red-500/40 rounded-xl flex items-start gap-3">
          <AlertTriangle className="text-red-400 shrink-0 mt-0.5" size={18} />
          <div>
            <p className="text-sm font-semibold text-red-300">This needs urgent, in-person medical attention.</p>
            <p className="text-xs text-red-300/80 mt-1 flex items-center gap-1.5">
              <Phone size={11} /> Emergency: {data.emergency?.national_emergency_number}
            </p>
          </div>
        </div>
      )}

      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-emerald-400" />
          <span className={`text-[11px] px-2 py-1 rounded-md border font-medium ${risk?.cls}`}>{risk?.label}</span>
          {data.result?.top?.name && !data.result?.out_of_coverage && (
            <span className="text-xs text-slate-400">· preliminary match: <span className="text-slate-200">{data.result.top.name}</span></span>
          )}
        </div>

        {data.result?.top && (
          <ReasoningPanel top={data.result.top} evidence={data.result.evidence} rankingReliable={data.result.ranking_reliable} />
        )}

        {data.guidance && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              {data.guidance_source === 'general_llm_unverified' && (
                <span className="text-[10px] font-mono uppercase tracking-wide text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded flex items-center gap-1">
                  <AlertTriangle size={10} /> General AI info — unverified
                </span>
              )}
              {data.guidance_source === 'curated_kb' && (
                <span className="text-[10px] font-mono uppercase tracking-wide text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
                  Curated knowledge base
                </span>
              )}
            </div>
            <div className={`flex items-start gap-2 rounded-xl p-3 border ${
              data.guidance_source === 'general_llm_unverified' ? 'bg-amber-500/5 border-amber-500/20' : 'border-transparent'
            }`}>
              <div className="text-sm text-slate-300 leading-relaxed whitespace-pre-line flex-1">{data.guidance}</div>
              {isSpeechSynthesisSupported() && (
                <button
                  onClick={() => onSpeak(data.guidance!, locale)}
                  title="Listen to guidance"
                  className="shrink-0 p-1 text-slate-600 hover:text-emerald-400 transition-colors"
                >
                  <Volume2 size={14} />
              </button>
            )}
          </div>
          </div>
        )}

        {data.routed_specialist && (
          <div className="flex items-center gap-2 text-xs text-slate-400 pt-2 border-t border-slate-800/60">
            <MapPin size={12} /> Recommended: {data.routed_specialist}
          </div>
        )}

        <p className="text-[10px] text-slate-600 pt-1">
          AI-assisted preliminary screening only. Not a medical diagnosis. Clinical judgment from a real doctor always takes priority.
        </p>
      </div>
    </motion.div>
  );
}