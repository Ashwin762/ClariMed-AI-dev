// frontend/src/components/DoctorPortal.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Loader2, AlertTriangle, User, Clock, ClipboardList,
  ChevronDown, Plus, Hand, LogOut, Activity, Inbox,
} from 'lucide-react';
import Logo from './Logo';
import {
  registerDoctor, loginDoctor, fetchDepartments, fetchDoctorMe,
  logoutDoctor, fetchDoctorAppointments, claimAppointment, addClinicalNote,
  getStoredDoctorToken, storeDoctorToken, clearDoctorToken,
  type DoctorAppointment, type DoctorProfile,
} from '../api';

// ===========================================================================
// Root: decides between auth screen and the board, restoring any saved session
// ===========================================================================

export default function DoctorPortal({ onBack }: { onBack: () => void }) {
  const [token, setToken] = useState<string | null>(getStoredDoctorToken());
  const [doctor, setDoctor] = useState<DoctorProfile | null>(null);
  const [restoring, setRestoring] = useState<boolean>(!!getStoredDoctorToken());

  useEffect(() => {
    if (!token) return;
    fetchDoctorMe(token)
      .then((d) => setDoctor(d))
      .catch(() => { clearDoctorToken(); setToken(null); })
      .finally(() => setRestoring(false));
  }, [token]);

  const handleAuthed = (t: string, d: DoctorProfile) => {
    storeDoctorToken(t);
    setToken(t);
    setDoctor(d);
  };

  const handleLogout = async () => {
    if (token) await logoutDoctor(token).catch(() => {});
    clearDoctorToken();
    setToken(null);
    setDoctor(null);
  };

  if (restoring) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="animate-spin text-slate-600" size={22} />
      </div>
    );
  }

  if (!token || !doctor) {
    return <AuthScreen onAuthed={handleAuthed} onBack={onBack} />;
  }

  return <TriageBoard token={token} doctor={doctor} onLogout={handleLogout} />;
}

// ===========================================================================
// Auth
// ===========================================================================

function AuthScreen({ onAuthed, onBack }: { onAuthed: (t: string, d: DoctorProfile) => void; onBack: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [departments, setDepartments] = useState<string[]>([]);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [department, setDepartment] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchDepartments().then(setDepartments).catch(() => {});
  }, []);

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      if (mode === 'register') {
        if (!department) { setError('Please choose your department.'); setBusy(false); return; }
        await registerDoctor(name, email, password, department);
      }
      const { token, doctor } = await loginDoctor(email, password);
      onAuthed(token, doctor);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 opacity-[0.04] flex items-center">
        <svg viewBox="0 0 1200 200" className="w-full" preserveAspectRatio="none">
          <path d="M0,100 L300,100 L330,100 L345,40 L360,160 L375,100 L420,100 L1200,100"
            fill="none" stroke="#10b981" strokeWidth="2" />
        </svg>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-md relative"
      >
        <div className="flex items-center gap-3 mb-8">
          <Logo size={48} />
          <div>
            <h1 className="font-display text-xl font-bold text-slate-100 leading-tight">Clinician Portal</h1>
            <p className="text-xs text-slate-500 font-mono">ClariMed AI</p>
          </div>
        </div>

        <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-7 backdrop-blur-sm">
          <div className="flex gap-1 mb-6 bg-slate-950/60 rounded-lg p-1">
            {(['login', 'register'] as const).map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setError(''); }}
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
                  mode === m ? 'bg-slate-800 text-slate-100' : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {m === 'login' ? 'Sign in' : 'Register'}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            <AnimatePresence mode="popLayout">
              {mode === 'register' && (
                <motion.div key="name"
                  initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                  <Field label="Full name">
                    <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Dr Jane Rao" className="input-field" />
                  </Field>
                </motion.div>
              )}
            </AnimatePresence>

            <Field label="Email">
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="you@hospital.org" className="input-field" />
            </Field>

            <Field label="Password">
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && mode === 'login' && submit()}
                placeholder={mode === 'register' ? 'At least 6 characters' : 'Your password'} className="input-field" />
            </Field>

            <AnimatePresence mode="popLayout">
              {mode === 'register' && (
                <motion.div key="dept"
                  initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                  <Field label="Department">
                    <select value={department} onChange={(e) => setDepartment(e.target.value)} className="input-field">
                      <option value="">Select your specialty…</option>
                      {departments.map((d) => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </Field>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {error && (
            <p className="text-xs text-red-400 mt-3 flex items-center gap-1.5">
              <AlertTriangle size={12} /> {error}
            </p>
          )}

          <button
            onClick={submit}
            disabled={busy || !email || !password || (mode === 'register' && (!name || !department))}
            className="w-full mt-6 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 disabled:hover:bg-emerald-500 text-slate-950 font-semibold py-3 rounded-xl text-sm flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
          >
            {busy ? <Loader2 size={16} className="animate-spin" /> : null}
            {mode === 'login' ? 'Sign in to portal' : 'Create account & enter'}
          </button>
        </div>

        <button onClick={onBack} className="w-full mt-4 text-xs text-slate-600 hover:text-slate-400 transition-colors">
          ← Back to patient app
        </button>
      </motion.div>

      <style>{`
        .input-field {
          width: 100%; background: rgb(2 6 23 / 0.6); border: 1px solid rgb(30 41 59);
          border-radius: 0.6rem; padding: 0.6rem 0.8rem; font-size: 0.875rem;
          color: rgb(226 232 240); outline: none; transition: border-color 0.15s;
        }
        .input-field:focus { border-color: rgb(16 185 129); }
      `}</style>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[11px] uppercase tracking-wide text-slate-500 mb-1.5 font-mono">{label}</span>
      {children}
    </label>
  );
}

// ===========================================================================
// The Triage Board
// ===========================================================================

function TriageBoard({ token, doctor, onLogout }: { token: string; doctor: DoctorProfile; onLogout: () => void }) {
  const [appointments, setAppointments] = useState<DoctorAppointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const { appointments } = await fetchDoctorAppointments(token);
      setAppointments(appointments);
      setError('');
    } catch (e) {
      if (e instanceof Error && e.message === 'SESSION_EXPIRED') { onLogout(); return; }
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [token, onLogout]);

  useEffect(() => {
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [load]);

  const handleClaim = async (id: string) => {
    try {
      await claimAppointment(token, id);
      await load();
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Could not claim');
    }
  };

  const isEmergency = (a: DoctorAppointment) => a.screening?.risk_level === 'red';
  const emergencies = appointments.filter((a) => a.is_mine && isEmergency(a));
  const mine = appointments.filter((a) => a.is_mine && !isEmergency(a));
  const pool = appointments.filter((a) => a.is_pooled);

  const firstName = doctor.name.replace(/^Dr\.?\s*/i, '').split(' ')[0];

  return (
    <div className="min-h-screen max-w-3xl mx-auto px-4 py-8">
      <motion.header
        initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
        className="flex items-start justify-between mb-8"
      >
        <div>
          <p className="text-sm text-slate-500 font-mono mb-1">{doctor.department}</p>
          <h1 className="font-display text-2xl font-bold text-slate-100">
            Good {timeOfDay()}, Dr {firstName}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {emergencies.length > 0
              ? `${emergencies.length} case${emergencies.length > 1 ? 's' : ''} need${emergencies.length > 1 ? '' : 's'} your attention now`
              : mine.length > 0
              ? `${mine.length} case${mine.length > 1 ? 's' : ''} in your care`
              : "No active cases — you're all caught up"}
          </p>
        </div>
        <button onClick={onLogout}
          className="text-slate-500 hover:text-slate-300 transition-colors flex items-center gap-1.5 text-xs mt-1">
          <LogOut size={14} /> Sign out
        </button>
      </motion.header>

      {error && (
        <div className="mb-5 rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={load} className="underline hover:no-underline text-xs">Retry</button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-24 text-slate-600">
          <Loader2 className="animate-spin mr-2" size={18} /> Loading your board…
        </div>
      ) : (
        <div className="space-y-8">
          {emergencies.length > 0 && (
            <Section icon={<Activity size={15} className="text-red-400" />} title="Needs attention now" accent="text-red-300">
              {emergencies.map((a) => <Case key={a.id} appt={a} token={token} onChanged={load} />)}
            </Section>
          )}

          <Section icon={<User size={15} className="text-emerald-400" />} title="In your care" count={mine.length}>
            {mine.length === 0
              ? <Empty text="Cases assigned to you will appear here." />
              : mine.map((a) => <Case key={a.id} appt={a} token={token} onChanged={load} />)}
          </Section>

          <Section icon={<Inbox size={15} className="text-slate-400" />} title="Available in your department"
            count={pool.length} subtitle="Not yet assigned — claim to take a case">
            {pool.length === 0
              ? <Empty text="Nothing waiting in the pool right now." />
              : pool.map((a) => <Case key={a.id} appt={a} token={token} onChanged={load} onClaim={() => handleClaim(a.id)} />)}
          </Section>
        </div>
      )}

      <p className="text-center text-[10px] text-slate-700 mt-12 leading-relaxed">
        AI screenings are preliminary and never diagnostic. Clinical judgment supersedes all output.<br />
        Patient images are never stored and are not shown here.
      </p>
    </div>
  );
}

function Section({
  icon, title, count, subtitle, accent, children,
}: {
  icon: React.ReactNode; title: string; count?: number; subtitle?: string; accent?: string; children: React.ReactNode;
}) {
  return (
    <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
      <div className="flex items-center gap-2 mb-3">
        {icon}
        <h2 className={`text-xs font-mono uppercase tracking-wider ${accent || 'text-slate-400'}`}>{title}</h2>
        {count != null && (
          <span className="text-[10px] font-mono text-slate-600 bg-slate-900 px-1.5 py-0.5 rounded">{count}</span>
        )}
        {subtitle && <span className="text-[10px] text-slate-600 ml-1">· {subtitle}</span>}
      </div>
      <div className="space-y-2.5">{children}</div>
    </motion.section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="text-xs text-slate-600 py-3 px-1">{text}</p>;
}

// ===========================================================================
// A single case card
// ===========================================================================

function Case({
  appt, token, onChanged, onClaim,
}: {
  appt: DoctorAppointment; token: string; onChanged: () => void; onClaim?: () => void;
}) {
  const s = appt.screening;
  const emergency = s?.risk_level === 'red';
  const [expanded, setExpanded] = useState(emergency);
  const [noteText, setNoteText] = useState('');
  const [savingNote, setSavingNote] = useState(false);
  const [showNoteBox, setShowNoteBox] = useState(false);

  const riskMeta = s?.risk_level === 'red'
    ? { label: 'Emergency', cls: 'text-red-300 bg-red-500/15 border-red-500/40' }
    : s?.risk_level === 'yellow'
    ? { label: 'Caution', cls: 'text-amber-300 bg-amber-500/15 border-amber-500/40' }
    : s?.risk_level === 'green'
    ? { label: 'Routine', cls: 'text-emerald-300 bg-emerald-500/15 border-emerald-500/40' }
    : null;

  const saveNote = async () => {
    if (!noteText.trim()) return;
    setSavingNote(true);
    try {
      await addClinicalNote(token, appt.id, noteText.trim());
      setNoteText('');
      setShowNoteBox(false);
      onChanged();
    } catch {
      alert('Could not save the note. Please try again.');
    } finally {
      setSavingNote(false);
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className={`bg-slate-900/40 border rounded-xl overflow-hidden ${
        emergency ? 'emergency-pulse border-red-500/50' : 'border-slate-800'
      }`}
    >
      <button onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 p-4 text-left hover:bg-slate-900/40 transition-colors">
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
          emergency ? 'bg-red-500/15' : 'bg-slate-800'
        }`}>
          {emergency ? <div className="w-2.5 h-2.5 rounded-full bg-red-400 vital-dot" /> : <User size={16} className="text-slate-400" />}
        </div>

        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-100 truncate">{appt.patient_name || 'Anonymous patient'}</p>
          <p className="text-xs text-slate-500 flex items-center gap-1.5 mt-0.5">
            <Clock size={11} /> {appt.slot}
            {s?.top_condition_name && !s.out_of_coverage && (
              <span className="text-slate-600">· {s.top_condition_name}</span>
            )}
          </p>
        </div>

        {riskMeta && (
          <span className={`text-[10px] px-2 py-1 rounded-md border shrink-0 font-medium ${riskMeta.cls}`}>{riskMeta.label}</span>
        )}

        {onClaim ? (
          <button onClick={(e) => { e.stopPropagation(); onClaim(); }}
            className="shrink-0 text-xs bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-semibold px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all active:scale-95">
            <Hand size={12} /> Claim
          </button>
        ) : (
          <motion.div animate={{ rotate: expanded ? 180 : 0 }}>
            <ChevronDown size={16} className="text-slate-500 shrink-0" />
          </motion.div>
        )}
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }} className="overflow-hidden">
            <div className="px-4 pb-4 pt-1 space-y-4 border-t border-slate-800/60">
              {s ? (
                <div className="space-y-3 pt-3">
                  <div className="flex items-center gap-1.5 text-[11px] font-mono uppercase tracking-wider text-slate-500">
                    <ClipboardList size={12} /> AI preliminary screening
                  </div>

                  <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
                    <Detail label="Body area" value={s.body_part ? cap(s.body_part) : '—'} />
                    <Detail label="Preliminary match"
                      value={s.out_of_coverage ? 'Outside coverage'
                        : `${s.top_condition_name || '—'}${s.top_confidence_pct != null ? ` · ${s.top_confidence_pct}%` : ''}`} />
                  </div>

                  {s.symptoms.length > 0 && <Chips label="Reported symptoms" items={s.symptoms} />}
                  {s.redflags.length > 0 && <Chips label="Red-flag symptoms" items={s.redflags} danger />}

                  {s.guidance && (
                    <div className="text-xs">
                      <span className="text-[11px] uppercase tracking-wide text-slate-500 font-mono">Guidance shown to patient</span>
                      <p className="text-slate-300 mt-1 leading-relaxed">{s.guidance}</p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-slate-500 pt-3">No AI screening is linked to this appointment.</p>
              )}

              <div className="space-y-2 pt-1">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] uppercase tracking-wide text-slate-500 font-mono">Clinical notes</span>
                  {!showNoteBox && (
                    <button onClick={() => setShowNoteBox(true)}
                      className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1">
                      <Plus size={12} /> Add note
                    </button>
                  )}
                </div>

                {appt.notes.map((n) => (
                  <div key={n.id} className="text-xs bg-slate-950/50 border border-slate-800/60 rounded-lg p-2.5">
                    <p className="text-slate-300 leading-relaxed">{n.note}</p>
                    <p className="text-[10px] text-slate-600 mt-1 font-mono">{new Date(n.created_at).toLocaleString()}</p>
                  </div>
                ))}

                {showNoteBox && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
                    <textarea value={noteText} onChange={(e) => setNoteText(e.target.value)} rows={3} autoFocus
                      placeholder="Add a clinical note…"
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-600 resize-none" />
                    <div className="flex gap-2">
                      <button onClick={saveNote} disabled={savingNote || !noteText.trim()}
                        className="bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-slate-950 font-medium px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5">
                        {savingNote ? <Loader2 size={12} className="animate-spin" /> : null} Save
                      </button>
                      <button onClick={() => { setShowNoteBox(false); setNoteText(''); }}
                        className="text-xs text-slate-500 hover:text-slate-300 px-2">Cancel</button>
                    </div>
                  </motion.div>
                )}

                {appt.notes.length === 0 && !showNoteBox && <p className="text-xs text-slate-600">No notes yet.</p>}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-slate-500">{label}</span>
      <p className="text-slate-200 mt-0.5">{value}</p>
    </div>
  );
}

function Chips({ label, items, danger }: { label: string; items: string[]; danger?: boolean }) {
  return (
    <div className="text-xs">
      <span className={`text-[11px] uppercase tracking-wide font-mono ${danger ? 'text-red-400' : 'text-slate-500'}`}>
        {danger && <AlertTriangle size={10} className="inline mr-1 -mt-0.5" />}{label}
      </span>
      <div className="flex flex-wrap gap-1.5 mt-1.5">
        {items.map((it) => (
          <span key={it} className={`px-2 py-0.5 rounded ${
            danger ? 'bg-red-500/15 text-red-300 border border-red-500/30' : 'bg-slate-800 text-slate-300'
          }`}>{it}</span>
        ))}
      </div>
    </div>
  );
}

function timeOfDay(): string {
  const h = new Date().getHours();
  if (h < 12) return 'morning';
  if (h < 17) return 'afternoon';
  return 'evening';
}
function cap(s: string): string { return s.charAt(0).toUpperCase() + s.slice(1); }