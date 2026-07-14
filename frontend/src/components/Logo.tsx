// frontend/src/components/Logo.tsx
import React from 'react';

/** The ClariMed AI mark: an open eye on a glass emerald badge — "Clari" as in
 * clarity/seeing clearly, tying directly to AI-assisted screening. Inlined as
 * JSX (not an imported .svg file) so it works with zero build config and
 * scales cleanly at any size via the `size` prop. */
export default function Logo({ size = 32, badge = true }: { size?: number; badge?: boolean }) {
  if (!badge) {
    // Mark-only variant, no background badge — for placement on colored surfaces.
    return (
      <svg width={size} height={size} viewBox="0 0 140 140" xmlns="http://www.w3.org/2000/svg">
        <path d="M 32 70 C 44 50, 96 50, 108 70 C 96 90, 44 90, 32 70 Z"
          fill="none" stroke="#10b981" strokeWidth="7" strokeLinejoin="round" />
        <circle cx="70" cy="70" r="13" fill="#10b981" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 140 140" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="clarimedBadge" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#10b981" />
          <stop offset="100%" stopColor="#059669" />
        </linearGradient>
        <linearGradient id="clarimedGlass" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.35" />
          <stop offset="50%" stopColor="#ffffff" stopOpacity="0.05" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect x="10" y="10" width="120" height="120" rx="32" fill="url(#clarimedBadge)" />
      <rect x="10" y="10" width="120" height="120" rx="32" fill="url(#clarimedGlass)" />
      <path d="M 32 70 C 44 50, 96 50, 108 70 C 96 90, 44 90, 32 70 Z"
        fill="none" stroke="white" strokeWidth="7" strokeLinejoin="round" />
      <circle cx="70" cy="70" r="13" fill="white" />
      <circle cx="70" cy="70" r="13" fill="none" stroke="#059669" strokeWidth="3" />
    </svg>
  );
}