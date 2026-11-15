import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

export type Language = 'zh' | 'en';
const storageKey = 'finpilot-language';

function readLanguage(fallback: Language = 'zh'): Language {
  try { return localStorage.getItem(storageKey) === 'en' ? 'en' : 'zh'; }
  catch { return fallback; }
}

type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (zh: string, en: string) => string;
};
const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, updateLanguage] = useState<Language>(() => readLanguage());
  const value = useMemo<LanguageContextValue>(() => ({
    language,
    setLanguage(next) {
      updateLanguage(next);
      try { localStorage.setItem(storageKey, next); } catch { /* The interface still works without storage. */ }
    },
    t: (zh, en) => language === 'zh' ? zh : en,
  }), [language]);

  useLayoutEffect(() => {
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    document.title = language === 'zh' ? 'FinPilot · 把金融看得更清楚' : 'FinPilot · See finance more clearly';
    document.querySelector('meta[name="description"]')?.setAttribute('content', language === 'zh'
      ? 'FinPilot 金融学习工作台。通过可核查来源、公式计算和交互教练，把复杂金融看得更清楚。'
      : 'Understand finance with FinPilot: explore traceable sources, formula-based calculations and an interactive learning companion.');
  }, [language]);

  useEffect(() => {
    const refresh = () => updateLanguage(previous => readLanguage(previous));
    const storage = (event: StorageEvent) => { if (event.key === storageKey || event.key === null) refresh(); };
    const visible = () => { if (!document.hidden) refresh(); };
    window.addEventListener('storage', storage);
    window.addEventListener('pageshow', refresh);
    document.addEventListener('visibilitychange', visible);
    return () => {
      window.removeEventListener('storage', storage);
      window.removeEventListener('pageshow', refresh);
      document.removeEventListener('visibilitychange', visible);
    };
  }, []);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const value = useContext(LanguageContext);
  if (!value) throw new Error('useLanguage requires LanguageProvider');
  return value;
}
