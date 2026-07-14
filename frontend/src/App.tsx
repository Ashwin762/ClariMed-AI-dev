import React, { useState } from 'react';
import Hero from './components/Hero';
import Wizard from './components/Wizard';
import DoctorPortal from './components/DoctorPortal';

export default function App() {
  // The doctor portal lives at /doctor — checked once on load so patients
  // never see it, but clinicians can bookmark the URL directly. Uses the
  // existing path rather than adding a router library for one extra view.
  const [isDoctor, setIsDoctor] = useState<boolean>(
    () => typeof window !== 'undefined' && window.location.pathname.startsWith('/doctor')
  );

  // State 0: landing page (Hero). State 1: patient screening wizard.
  const [engineActive, setEngineActive] = useState<boolean>(false);

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

  return (
    <div className="min-h-screen bg-slate-950 selection:bg-emerald-500/30 overflow-x-clip">
      {!engineActive ? (
        <Hero onStart={() => setEngineActive(true)} />
      ) : (
        <Wizard onBack={() => setEngineActive(false)} />
      )}
    </div>
  );
}