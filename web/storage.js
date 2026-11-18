/* Preferences must remain optional when site storage is blocked or full. */
(() => {
  'use strict';
  const fallback = new Map();
  window.FinPilotStorage = Object.freeze({
    getItem(key) {
      if (fallback.has(key)) return fallback.get(key);
      try { return window.localStorage.getItem(key); } catch { return null; }
    },
    setItem(key, value) {
      const text = String(value);
      try { window.localStorage.setItem(key, text); fallback.delete(key); }
      catch { fallback.set(key, text); }
    },
    removeItem(key) {
      try { window.localStorage.removeItem(key); fallback.delete(key); }
      catch { fallback.set(key, null); }
    },
  });
})();
