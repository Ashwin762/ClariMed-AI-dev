// frontend/src/useUserLocation.ts
import { useState, useCallback } from 'react';

export interface UserLocation {
  lat: number;
  lng: number;
}

type Status = 'idle' | 'requesting' | 'granted' | 'denied' | 'timeout' | 'unavailable' | 'unsupported';

/**
 * Opt-in browser geolocation. Deliberately NOT requested automatically on
 * page load — the browser's own permission prompt is a consent gate, but we
 * only trigger it when the user explicitly asks (e.g. clicks "Use my
 * location"), consistent with the rest of the app never acting without an
 * explicit signal from the user.
 */
export function useUserLocation() {
  const [location, setLocation] = useState<UserLocation | null>(null);
  const [status, setStatus] = useState<Status>('idle');

  const requestLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setStatus('unsupported');
      return;
    }
    setStatus('requesting');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setStatus('granted');
      },
      (err) => {
        // GeolocationPositionError codes: 1=PERMISSION_DENIED, 2=POSITION_UNAVAILABLE,
        // 3=TIMEOUT. These were previously all collapsed into "denied", which
        // actively lies to a user who DID click Allow but hit a timeout or a
        // weak GPS/network fix instead — a real report from outside the
        // dense urban core (Anekal), where positioning genuinely takes longer.
        if (err.code === err.PERMISSION_DENIED) setStatus('denied');
        else if (err.code === err.TIMEOUT) setStatus('timeout');
        else setStatus('unavailable');
      },
      // 15s (was 8s) — network/GPS positioning can genuinely take longer
      // outside dense urban areas; 8s was cutting off legitimate attempts.
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 5 * 60 * 1000 }
    );
  }, []);

  return { location, status, requestLocation };
}

/** Great-circle distance in km between two lat/lng points (Haversine formula). */
export function distanceKm(a: UserLocation, b: UserLocation): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
}

export function formatDistance(km: number): string {
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(1)} km`;
}