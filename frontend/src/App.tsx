import React, { useState } from 'react';
import Hero from './components/Hero';
import Wizard from './components/Wizard';

export default function App() {
  // State 0: Show Landing/Scrollytelling Page (Hero)
  // State 1: Show Interactive Screening Wizard
  const [engineActive, setEngineActive] = useState<boolean>(false);

  return (
    <div className="min-h-screen bg-slate-950 selection:bg-emerald-500/30 overflow-x-hidden">
      {!engineActive ? (
        // When the user clicks "Launch Screening Engine", switch to the wizard
        <Hero onStart={() => setEngineActive(true)} />
      ) : (
        // When the user clicks "Exit Engine", return to the landing page
        <Wizard onBack={() => setEngineActive(false)} />
      )}
    </div>
  );
}