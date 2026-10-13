import { useState, useRef, useId, type FormEvent, type ClipboardEvent } from 'react';
import './UrlInput.css';

interface UrlInputProps {
  onSubmit: (url: string) => void;
  isLoading?: boolean;
}

export function UrlInput({ onSubmit, isLoading = false }: UrlInputProps) {
  const [value, setValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  const isEmpty = value.trim().length === 0;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (isEmpty || isLoading) return;
    onSubmit(value.trim());
  }

  function handlePaste(e: ClipboardEvent) {
    // Auto-submit on paste if field was empty
    const pasted = e.clipboardData.getData('text').trim();
    if (isEmpty && pasted.length > 0) {
      setValue(pasted);
      setTimeout(() => onSubmit(pasted), 50);
    }
  }

  return (
    <section className="url-section animate-fade-up" id="url-input-section" aria-label="Enter YouTube URL">
      {/* ── Hero text ───────────────────────────────────────────────────── */}
      <div className="url-section__hero">
        <p className="url-section__eyebrow hud-label text-faint">
          <span>01</span>
          <span aria-hidden="true" className="url-section__slash">/</span>
          YouTube Downloads
        </p>

        <h1 className="display-xl url-section__heading">
          Download YouTube<br />
          <span className="text-accent">your&nbsp;way.</span>
        </h1>

        <p className="body-lg text-muted url-section__subtext">
          Paste a YouTube URL to fetch available formats&thinsp;—&thinsp;select
          your preferred video resolution or audio quality, then download.
        </p>
      </div>

      {/* ── URL input form ───────────────────────────────────────────────── */}
      <form
        className="url-form"
        onSubmit={handleSubmit}
        aria-label="YouTube URL input form"
      >
        <div className="url-form__field">
          <label htmlFor={inputId} className="sr-only">YouTube URL</label>
          <input
            id={inputId}
            ref={inputRef}
            className="url-form__input input-field"
            type="url"
            inputMode="url"
            autoComplete="url"
            spellCheck={false}
            placeholder="https://www.youtube.com/watch?v=..."
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onPaste={handlePaste}
            disabled={isLoading}
            aria-describedby="url-form-hint"
          />
          <button
            type="submit"
            className="btn-primary url-form__btn"
            disabled={isEmpty || isLoading}
            aria-label="Fetch video information"
            id="url-fetch-btn"
          >
            {isLoading ? (
              <span className="url-form__spinner" aria-hidden="true" />
            ) : (
              <ArrowIcon />
            )}
            <span>{isLoading ? 'Fetching…' : 'Fetch'}</span>
          </button>
        </div>

        <p id="url-form-hint" className="url-form__hint hud-label text-faint">
          Supports YouTube, YouTube Music & Playlist Links
        </p>
      </form>

      {/* ── Feature pills ───────────────────────────────────────────────── */}
      <div className="url-section__pills" aria-label="Supported features">
        {['MP4 Video', 'MP3 Audio', 'M4A Audio', 'WAV Audio', '8K · 4K · 2K · 1080p · 720p · 480p'].map((label) => (
          <span key={label} className="badge url-pill">{label}</span>
        ))}
      </div>
    </section>
  );
}

function ArrowIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <path d="M2 7H12M8 3L12 7L8 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
