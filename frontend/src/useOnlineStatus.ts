// frontend/src/useOnlineStatus.ts
import { useState, useEffect } from 'react';

/**
 * Tracks browser connectivity. Used to gate features that genuinely need
 * the live hospital network (booking, specialist directory sync, history
 * sync) while the core AI screening keeps working regardless — its logic
 * has no external API/cloud dependency once the app is loaded.
 */
export function useOnlineStatus(): boolean {
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  return isOnline;
}