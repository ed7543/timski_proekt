import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from './AuthContext';
import { HelpTourModal } from '../components/onboarding/HelpTourModal';

const STORAGE_KEY = 'lw_help_seen';

interface HelpTourContextValue {
  openTour: () => void;
}

const HelpTourContext = createContext<HelpTourContextValue | undefined>(undefined);

function hasSeenTour(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function markTourSeen(): void {
  try {
    localStorage.setItem(STORAGE_KEY, '1');
  } catch {
    /* ignore - tour will just auto-show again next visit */
  }
}

export function HelpTourProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const [open, setOpen] = useState(false);
  const autoShown = useRef(false);

  useEffect(() => {
    // Only ever auto-triggers once per mount of the provider (App.tsx mounts
    // it once) - guards against status flipping loading -> authenticated ->
    // (a re-render) from firing this more than once.
    if (status === 'authenticated' && !autoShown.current && !hasSeenTour()) {
      autoShown.current = true;
      setOpen(true);
    }
  }, [status]);

  const openTour = useCallback(() => setOpen(true), []);

  const closeTour = useCallback(() => {
    setOpen(false);
    markTourSeen();
  }, []);

  return (
    <HelpTourContext.Provider value={{ openTour }}>
      {children}
      {open && <HelpTourModal onClose={closeTour} />}
    </HelpTourContext.Provider>
  );
}

export function useHelpTour(): HelpTourContextValue {
  const ctx = useContext(HelpTourContext);
  if (!ctx) throw new Error('useHelpTour must be used within HelpTourProvider');
  return ctx;
}
