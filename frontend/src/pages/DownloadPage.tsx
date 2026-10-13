import { useDownload } from '../hooks/useDownload';
import { Navbar } from '../components/Navbar';
import { UrlInput } from '../components/UrlInput';
import { MetadataCard } from '../components/MetadataCard';
import { FormatSelector } from '../components/FormatSelector';
import { ProgressPanel } from '../components/ProgressPanel';
import { PlaylistSelector } from '../components/PlaylistSelector';
import { PlaylistQueuedCard } from '../components/PlaylistQueuedCard';
import './DownloadPage.css';

// ── DownloadPage — orchestrates all phase transitions ─────────────────────

export function DownloadPage() {
  const {
    phase,
    submitUrl,
    selectFormat,
    startPlaylistDownload,
    requestCancel,
    requestPause,
    requestResume,
    reset,
  } = useDownload();

  return (
    <div className="download-page">
      {/* Subtle background grid */}
      <div className="download-page__bg-grid" aria-hidden="true" />

      {/* Navigation */}
      <Navbar onReset={reset} />

      {/* Main content — phase-driven */}
      <main id="main-content" className="download-page__main">

        {/* ── IDLE ─────────────────────────────────────────────────────── */}
        {phase.kind === 'idle' && (
          <UrlInput onSubmit={submitUrl} isLoading={false} />
        )}

        {/* ── LOADING METADATA ────────────────────────────────────────── */}
        {phase.kind === 'loading-metadata' && (
          <>
            {/* Keep the URL input but disable it during fetch */}
            <UrlInput onSubmit={submitUrl} isLoading={true} />
            <div className="loading-indicator animate-fade-up" aria-live="polite" aria-label="Fetching video information">
              <div className="loading-indicator__spinner" aria-hidden="true" />
              <p className="loading-indicator__label hud-label">Fetching media info…</p>
            </div>
          </>
        )}

        {/* ── SELECT FORMAT ────────────────────────────────────────────── */}
        {phase.kind === 'select-format' && (
          <div className="select-format-layout animate-fade-up">
            <MetadataCard metadata={phase.metadata} onReset={reset} />
            <FormatSelector
              metadata={phase.metadata}
              onSelect={selectFormat}
              isLoading={false}
            />
          </div>
        )}

        {/* ── PLAYLIST SELECT ──────────────────────────────────────────── */}
        {phase.kind === 'playlist-select' && (
          <PlaylistSelector
            playlist={phase.playlist}
            onDownload={startPlaylistDownload}
            onCancel={reset}
          />
        )}

        {/* ── PLAYLIST QUEUED ──────────────────────────────────────────── */}
        {phase.kind === 'playlist-queued' && (
          <PlaylistQueuedCard
            playlistTitle={phase.playlistTitle}
            enqueuedCount={phase.enqueuedCount}
            onReset={reset}
          />
        )}

        {/* ── PROCESSING ───────────────────────────────────────────────── */}
        {phase.kind === 'processing' && (
          <ProgressPanel
            phase={phase}
            onCancel={requestCancel}
            onPause={requestPause}
            onResume={requestResume}
            onReset={reset}
          />
        )}

        {/* ── COMPLETED ────────────────────────────────────────────────── */}
        {phase.kind === 'completed' && (
          <ProgressPanel
            phase={phase}
            onCancel={requestCancel}
            onPause={requestPause}
            onResume={requestResume}
            onReset={reset}
          />
        )}

        {/* ── ERROR ────────────────────────────────────────────────────── */}
        {phase.kind === 'error' && (
          <ProgressPanel
            phase={phase}
            onCancel={requestCancel}
            onPause={requestPause}
            onResume={requestResume}
            onReset={reset}
          />
        )}

      </main>

      {/* Footer */}
      <footer className="download-page__footer" aria-label="Site footer">
        <span className="footer__note hud-label text-faint">Valai-oli</span>
        <span className="footer__dot hud-label text-faint" aria-hidden="true">·</span>
        <span className="footer__note hud-label text-faint">YouTube Media Downloader</span>
        <span className="footer__dot hud-label text-faint" aria-hidden="true">·</span>
        <span className="footer__note hud-label text-faint">v0.2.0</span>
      </footer>
    </div>
  );
}
