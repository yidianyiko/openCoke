'use client';

import { useLocale } from './locale-provider';

export function LocaleSwitch() {
  const { locale, setLocale, messages } = useLocale();

  return (
    <div className="locale-switch" role="group" aria-label={messages.publicShell.languageSwitchLabel}>
      <button
        type="button"
        className="locale-switch__opt"
        aria-pressed={locale === 'en'}
        onClick={() => setLocale('en')}
      >
        EN
      </button>
      <button
        type="button"
        className="locale-switch__opt"
        aria-pressed={locale === 'zh'}
        onClick={() => setLocale('zh')}
      >
        中文
      </button>
    </div>
  );
}
