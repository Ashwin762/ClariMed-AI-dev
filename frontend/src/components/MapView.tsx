// frontend/src/components/MapView.tsx
import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Clinic } from '../api';
import type { UserLocation } from '../useUserLocation';

// Leaflet's default marker icons reference relative image paths that break
// under most bundlers. Point them at the CDN instead of fighting Vite's
// asset resolution this close to a deadline.
const DEFAULT_ICON = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

// A visually distinct marker for "you are here" — blue circle, not a pin,
// so it's never mistaken for a clinic.
const USER_ICON = L.divIcon({
  className: '',
  html: '<div style="width:16px;height:16px;border-radius:50%;background:#3b82f6;border:3px solid white;box-shadow:0 0 0 2px #3b82f6,0 2px 6px rgba(0,0,0,0.4);"></div>',
  iconSize: [16, 16],
  iconAnchor: [8, 8],
});

export default function MapView({ clinics, userLocation }: { clinics: Clinic[]; userLocation?: UserLocation | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);

  const withCoords = clinics.filter(
    (c): c is Clinic & { lat: number; lng: number } => c.lat != null && c.lng != null
  );

  useEffect(() => {
    if (!containerRef.current || withCoords.length === 0) return;

    const center: [number, number] = userLocation
      ? [userLocation.lat, userLocation.lng]
      : [withCoords[0].lat, withCoords[0].lng];
    const map = L.map(containerRef.current, { scrollWheelZoom: false }).setView(center, 12);
    mapRef.current = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);

    const markers: L.Marker[] = withCoords.map((c) => {
      const marker = L.marker([c.lat, c.lng], { icon: DEFAULT_ICON }).addTo(map);
      marker.bindPopup(
        `<strong>${c.name}</strong><br/>${c.clinic}<br/>${c.distance}<br/><a href="tel:${c.phone}">${c.phone}</a>`
      );
      return marker;
    });

    if (userLocation) {
      const you = L.marker([userLocation.lat, userLocation.lng], { icon: USER_ICON }).addTo(map);
      you.bindPopup('You are here');
      markers.push(you);
    }

    if (markers.length > 1) {
      const group = L.featureGroup(markers);
      map.fitBounds(group.getBounds().pad(0.25));
    }

    // Leaflet needs an explicit size recalculation when its container was
    // hidden/animated in (e.g. behind a framer-motion fade) at mount time.
    setTimeout(() => map.invalidateSize(), 150);

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinics, userLocation]);

  if (withCoords.length === 0) return null;

  return (
    <div className="rounded-xl overflow-hidden border border-slate-800" style={{ height: 260 }}>
      <div ref={containerRef} style={{ height: '100%', width: '100%' }} />
    </div>
  );
}