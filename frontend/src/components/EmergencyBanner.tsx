// frontend/src/components/EmergencyBanner.tsx
import React from 'react';
import { motion } from 'framer-motion';
import { AlertOctagon, Phone, Navigation, Share2, MapPin } from 'lucide-react';
import type { EmergencyInfo, Clinic } from '../api';
import type { UserLocation } from '../useUserLocation';
import { distanceKm, formatDistance } from '../useUserLocation';
import MapView from './MapView';

function directionsUrl(lat: number, lng: number): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`;
}

/** Same logic as Wizard.tsx's sortByDistance — duplicated locally to keep
 * this component independently usable without a prop-drilled helper. */
function withRealDistances(hospitals: Clinic[], userLocation: UserLocation | null): Clinic[] {
  if (!userLocation) return hospitals;
  return [...hospitals]
    .map((h) => {
      if (h.lat == null || h.lng == null) return { ...h, __km: Infinity };
      const km = distanceKm(userLocation, { lat: h.lat, lng: h.lng });
      return { ...h, distance: formatDistance(km), __km: km };
    })
    .sort((a: any, b: any) => a.__km - b.__km);
}

export default function EmergencyBanner({
  emergency, riskReason, screeningId, patientName, interpretedRedflags,
  userLocation, locationStatus, requestLocation,
}: {
  emergency: EmergencyInfo; riskReason: string; screeningId?: string; patientName?: string;
  interpretedRedflags?: string[];
  userLocation?: UserLocation | null; locationStatus?: string; requestLocation?: () => void;
}) {
  // In a genuine emergency, "nearest" must reflect real distance when we
  // have it — not just whichever entry happens to sit first in mock data.
  const orderedHospitals = withRealDistances(emergency.hospitals, userLocation ?? null);
  const nearest = orderedHospitals[0];

  const handleShare = async () => {
    const text = `ClariMed AI flagged a potential emergency${patientName ? ` for ${patientName}` : ''}. ` +
      `Reason: ${riskReason}${screeningId ? ` (screening ${screeningId.slice(0, 8)})` : ''}.`;
    if (navigator.share) {
      try {
        await navigator.share({ title: 'ClariMed emergency alert', text });
      } catch {
        /* user cancelled the native share sheet — nothing to do */
      }
    } else {
      await navigator.clipboard.writeText(text);
      alert('Copied a summary to your clipboard — paste it to whoever you\'re calling.');
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }}
      className="rounded-2xl border-2 border-red-500/50 bg-red-500/10 p-6 space-y-4"
    >
      <div className="flex items-start gap-3">
        <AlertOctagon className="text-red-400 shrink-0 mt-0.5" size={26} />
        <div>
          <h2 className="font-display text-xl font-bold text-red-300">This may need urgent attention</h2>
          <p className="text-sm text-red-300/80 mt-1">{riskReason}</p>
          {interpretedRedflags && interpretedRedflags.length > 0 && (
            <p className="text-xs text-red-300/70 mt-2">
              Detected from your description: <span className="font-medium">{interpretedRedflags.join(', ')}</span>
              {' '}— you didn't need to tick a box for this.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <a
          href={`tel:${emergency.national_emergency_number}`}
          className="flex-1 min-w-[160px] flex items-center justify-center gap-2 py-3 bg-red-500 hover:bg-red-400 text-white font-semibold rounded-xl text-sm transition-colors"
        >
          <Phone size={16} /> Call {emergency.national_emergency_number} (Emergency)
        </a>
        {nearest && (
          <>
            <a
              href={`tel:${nearest.phone}`}
              className="flex-1 min-w-[160px] flex items-center justify-center gap-2 py-3 bg-slate-900 hover:bg-slate-800 border border-red-500/30 text-red-300 font-semibold rounded-xl text-sm transition-colors"
            >
              <Phone size={16} /> Call {nearest.name}
            </a>
            <a
              href={directionsUrl(nearest.lat!, nearest.lng!)}
              target="_blank" rel="noopener noreferrer"
              className="flex-1 min-w-[160px] flex items-center justify-center gap-2 py-3 bg-slate-900 hover:bg-slate-800 border border-red-500/30 text-red-300 font-semibold rounded-xl text-sm transition-colors"
            >
              <Navigation size={16} /> Directions
            </a>
          </>
        )}
        <button
          onClick={handleShare}
          className="flex-1 min-w-[160px] flex items-center justify-center gap-2 py-3 bg-slate-900 hover:bg-slate-800 border border-red-500/30 text-red-300 font-semibold rounded-xl text-sm transition-colors"
        >
          <Share2 size={16} /> Share this alert
        </button>
      </div>

      {emergency.hospitals.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-red-300/70 font-mono uppercase tracking-wide">Nearest emergency hospitals</p>
            {!userLocation && requestLocation && (
              <button
                onClick={requestLocation}
                disabled={locationStatus === 'requesting'}
                className="text-[10px] text-red-300 hover:text-red-200 flex items-center gap-1 disabled:opacity-50"
              >
                <MapPin size={10} />
                {locationStatus === 'requesting' ? 'Locating...' :
                 locationStatus === 'timeout' ? "Couldn't locate you in time - tap to retry" :
                 locationStatus === 'unavailable' ? 'Location signal unavailable - tap to retry' :
                 locationStatus === 'denied' ? 'Permission denied - tap to try again' :
                 'Use my real location'}
              </button>
            )}
          </div>
          <MapView clinics={orderedHospitals} userLocation={userLocation ?? undefined} />
          <div className="mt-2 space-y-1.5">
            {orderedHospitals.map((h) => (
              <div key={h.name} className="flex justify-between text-xs text-red-300/80">
                <span>{h.name} · {h.clinic}</span>
                <span className="font-mono">{h.distance}{userLocation && ' (live)'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-[10px] text-red-300/60 leading-relaxed">
        ClariMed is a screening tool, not a substitute for emergency medical care. If you or someone
        with you is in danger, call {emergency.national_emergency_number} or go to the nearest emergency
        room now — don't wait for an online response.
      </p>
    </motion.div>
  );
}