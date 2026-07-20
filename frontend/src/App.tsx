import React, { useState } from 'react';
import Hero from './components/Hero';
import Wizard from './components/Wizard';
import Chat from './components/Chat';
import DoctorPortal from './components/DoctorPortal';
import { LanguageProvider } from './i18n/LanguageContext';

type Mode = 'landing' | 'wizard' | 'chat';

export default function App() {
  // The doctor portal lives at /doctor — checked once on load so patients
  // never see it, but clinicians can bookmark the URL directly. Uses the
  // existing path rather than adding a router library for one extra view.
  const [isDoctor, setIsDoctor] = useState<boolean>(
    () => typeof window !== 'undefined' && window.location.pathname.startsWith('/doctor')
  );

  // Landing page, guided step-by-step wizard, or conversational chat --
  // chat is a NEW, additive presentation layer over the exact same
  // safety-tested backend the wizard already uses, not a replacement for
  // it. Both stay available; the proven wizard is never removed.
  const [mode, setMode] = useState<Mode>('landing');

  const leaveDoctor = () => {
    // Return to the patient app and tidy the URL back to root.
    if (typeof window !== 'undefined' && window.history) {
      window.history.pushState({}, '', '/');
    }
    setIsDoctor(false);
  };

  if (isDoctor) {
    return (
      <div className="min-h-screen bg-slate-950 selection:bg-emerald-500/30 overflow-x-clip">
        <DoctorPortal onBack={leaveDoctor} />
      </div>
    );
  }

  // LanguageProvider wraps the whole patient-facing app (not the doctor
  // portal, which is a clinical tool used by staff, not patients) so the
  // selected language and its translated UI strings are shared consistently
  // across the landing page, wizard, and chat -- one selection, one place,
  // instead of each flow managing its own separate language state.
  return (
    <LanguageProvider>
      <div className="min-h-screen bg-slate-950 selection:bg-emerald-500/30 overflow-x-clip">
        {mode === 'landing' && (
          <Hero onStart={() => setMode('wizard')} onStartChat={() => setMode('chat')} />
        )}
        {mode === 'wizard' && <Wizard onBack={() => setMode('landing')} />}
        {mode === 'chat' && <Chat onBack={() => setMode('landing')} />}
      </div>
    </LanguageProvider>
  );
}