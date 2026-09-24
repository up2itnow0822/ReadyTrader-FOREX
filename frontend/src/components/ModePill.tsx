"use client";

import { useEffect, useState } from 'react';
import { API_URL } from '@/lib/api';

type Mode = 'paper' | 'live' | 'offline' | null;

// Reads the trading mode from the API instead of assuming paper mode.
export default function ModePill() {
  const [mode, setMode] = useState<Mode>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API_URL}/api/health`);
        const data = await res.json();
        if (!cancelled) setMode(data.mode === 'live' ? 'live' : 'paper');
      } catch {
        if (!cancelled) setMode('offline');
      }
    };
    load();
    const timer = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const label = { paper: 'Paper Mode', live: 'LIVE TRADING', offline: 'API offline' }[mode ?? 'paper'];
  return <span className={`status-pill ${mode ?? 'paper'}`}>{mode === null ? 'Checking…' : label}</span>;
}
