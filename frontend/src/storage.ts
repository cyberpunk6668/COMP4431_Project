// Preferences are optional: denied storage must not prevent rendering the app.
export function readPreference(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}

export function writePreference(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* Keep the active in-memory state. */ }
}
