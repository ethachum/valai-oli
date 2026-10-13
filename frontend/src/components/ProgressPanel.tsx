import { useState, useEffect, useRef, useCallback } from 'react';
import type { AppPhase, JobState, FormatInfo, MetadataResponse, JobStatus } from '../types/api';
import './ProgressPanel.css';

// ── State label map ────────────────────────────────────────────────────────
const STATE_LABELS: Record<JobState, string> = {
  queued:      'QUEUED',
  downloading: 'DOWNLOADING',
  merging:     'MERGING',
  converting:  'CONVERTING',
  validating:  'VALIDATING',
  completed:   'COMPLETED',
  failed:      'FAILED',
  cancelled:   'CANCELLED',
  paused:      'PAUSED',
};

function formatFileSize(bytes: number | null): string {
  if (!bytes) return '';
  if (bytes < 1_000_000) return `~${(bytes / 1024).toFixed(0)} KB`;
  return `~${(bytes / 1_000_000).toFixed(1)} MB`;
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function sanitizeFilename(name: string): string {
  const cleaned = name
    .replace(/[\x00-\x1f*?"<>|]/g, '')
    .replace(/[/\\:]+/g, ' - ')
    .replace(/\s+/g, ' ')
    .replace(/(\s*-\s*)+/g, ' - ')
    .trim()
    .replace(/^[. -]+|[. -]+$/g, '');
  return cleaned.slice(0, 200) || 'download';
}

/** Trigger a browser file-save by navigating to the download endpoint. */
function triggerFileDownload(jobId: string, filename?: string): void {
  const a = document.createElement('a');
  const encodedName = filename ? encodeURIComponent(filename) : '';
  a.href = encodedName
    ? `/api/jobs/${jobId}/download/${encodedName}`
    : `/api/jobs/${jobId}/download`;
  if (filename) {
    a.download = filename;
  }
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ─────────────────────────────────────────────────────────────────────────────
// Song / Video Template Card (displayed on the side)
// ─────────────────────────────────────────────────────────────────────────────
interface SongTemplateCardProps {
  metadata: MetadataResponse;
  format?: FormatInfo;
}

function SongTemplateCard({ metadata, format }: SongTemplateCardProps) {
  return (
    <aside className="panel song-template-card" aria-label="Media preview">
      <div className="song-template__thumb-wrap">
        {metadata.thumbnail ? (
          <img
            className="song-template__thumb"
            src={metadata.thumbnail}
            alt={`Thumbnail for ${metadata.title}`}
            loading="lazy"
          />
        ) : (
          <div className="song-template__thumb-placeholder" aria-label="No thumbnail">
            <ThumbnailIcon />
          </div>
        )}
        {metadata.duration_seconds != null && (
          <span className="song-template__duration hud-label">
            {formatDuration(metadata.duration_seconds)}
          </span>
        )}
      </div>

      <div className="song-template__info">
        <span className="song-template__eyebrow hud-label text-accent">MEDIA DETAILS</span>
        <h4 className="song-template__title" title={metadata.title}>
          {metadata.title}
        </h4>
        {metadata.uploader && (
          <p className="song-template__uploader body-sm text-muted">
            <ChannelIcon />
            {metadata.uploader}
          </p>
        )}
        {format && (
          <div className="song-template__meta-row">
            <span className="badge badge-accent">{format.ext.toUpperCase()}</span>
            {format.resolution && <span className="badge">{format.resolution}</span>}
            {format.filesize_approx && (
              <span className="hud-label text-muted">{formatFileSize(format.filesize_approx)}</span>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Processing state
// ─────────────────────────────────────────────────────────────────────────────
interface ProcessingPanelProps {
  metadata: MetadataResponse;
  format: FormatInfo;
  job: JobStatus;
  onCancel: () => void;
  onPause?: () => void;
  onResume?: () => void;
}

function ProcessingPanel({
  metadata,
  format,
  job,
  onCancel,
  onPause,
  onResume,
}: ProcessingPanelProps) {
  const isPaused = job.state === 'paused';
  const pct = job.progress_percent ?? 0;
  const isIndeterminate = job.progress_percent === null;
  const stateLabel = STATE_LABELS[job.state] ?? job.state.toUpperCase();

  return (
    <section
      className="progress-section animate-fade-up"
      id="progress-section"
      aria-label="Download in progress"
      aria-live="polite"
      aria-atomic="false"
    >
      <div className="download-layout">
        {/* Song template on the side */}
        <SongTemplateCard metadata={metadata} format={format} />

        {/* Processing Box */}
        <div className="panel progress-panel">
          {/* Header */}
          <div className="progress-panel__header">
            <div className="progress-panel__status-group">
              <div
                className={`progress-panel__icon ${isPaused ? 'progress-panel__icon--paused' : ''}`}
                aria-hidden="true"
              >
                {isPaused ? <PauseIcon /> : <SpinnerIcon />}
              </div>
              <div className="progress-panel__state-block">
                <span className={`progress-panel__state-label hud-label ${isPaused ? 'text-muted' : 'text-accent'}`}>
                  {stateLabel}
                </span>
                <h3 className="progress-panel__message">
                  {job.message ?? (isPaused ? 'Download paused.' : 'Processing…')}
                </h3>
              </div>
            </div>

            {/* Controls: Pause / Play & Cancel */}
            <div className="progress-panel__actions-group">
              {isPaused ? (
                <button
                  type="button"
                  className="btn-accent progress-panel__play-btn"
                  onClick={onResume}
                  id="resume-job-btn"
                  aria-label="Resume download"
                  title="Resume download"
                >
                  <PlayIcon />
                  Resume
                </button>
              ) : (
                <button
                  type="button"
                  className="btn-ghost progress-panel__pause-btn"
                  onClick={onPause}
                  id="pause-job-btn"
                  aria-label="Pause download"
                  title="Pause download"
                  disabled={job.state !== 'downloading'}
                >
                  <PauseIcon />
                  Pause
                </button>
              )}
              <button
                type="button"
                className="btn-ghost progress-panel__cancel-btn"
                onClick={onCancel}
                id="cancel-job-btn"
                aria-label="Cancel this download"
              >
                <XIcon />
                Cancel
              </button>
            </div>
          </div>

          {/* Download metrics / details */}
          <div className="progress-panel__meta-grid">
            <div className="progress-panel__meta-cell">
              <span className="hud-label text-muted">Status</span>
              <span className="hud-label text-strong">{stateLabel}</span>
            </div>
            <div className="progress-panel__meta-cell">
              <span className="hud-label text-muted">Format</span>
              <span className="hud-label text-strong">
                {format.ext.toUpperCase()} {format.resolution ? `(${format.resolution})` : ''}
              </span>
            </div>
            <div className="progress-panel__meta-cell">
              <span className="hud-label text-muted">Est. Size</span>
              <span className="hud-label text-strong">{formatFileSize(format.filesize_approx) || '—'}</span>
            </div>
          </div>

          {/* Progress bar */}
          <div
            className="progress-bar-wrap"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Download progress: ${pct.toFixed(1)}%`}
          >
            <div className="progress-bar-label">
              <span className="hud-label text-muted">Download Progress</span>
              <span className={`progress-bar-pct hud-label ${isPaused ? 'text-muted' : 'text-accent'}`}>
                {isIndeterminate ? '…' : `${pct.toFixed(1)}%`}
              </span>
            </div>
            <div className="progress-bar-track">
              <div
                className={`progress-bar-fill${
                  isIndeterminate && !isPaused ? ' progress-bar-fill--indeterminate' : ''
                }${isPaused ? ' progress-bar-fill--paused' : ''}`}
                style={isIndeterminate ? undefined : { width: `${pct}%` }}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Completed state
// ─────────────────────────────────────────────────────────────────────────────
interface CompletedPanelProps {
  metadata: MetadataResponse;
  format: FormatInfo;
  job: JobStatus;
  onReset: () => void;
}

function CompletedPanel({ metadata, format, job, onReset }: CompletedPanelProps) {
  const [saving, setSaving] = useState(false);
  const autoDownloadedRef = useRef(false);

  const cleanTitle = sanitizeFilename(metadata.title || job.title || 'download');
  const targetFilename = `${cleanTitle}.${format.ext}`;

  const handleSave = useCallback(() => {
    setSaving(true);
    triggerFileDownload(job.job_id, targetFilename);
    setTimeout(() => setSaving(false), 2000);
  }, [job.job_id, targetFilename]);

  useEffect(() => {
    if (!autoDownloadedRef.current) {
      autoDownloadedRef.current = true;
      handleSave();
    }
  }, [handleSave]);

  return (
    <section
      className="progress-section animate-fade-up"
      id="completed-section"
      aria-label="Download complete"
      aria-live="polite"
    >
      <div className="download-layout">
        {/* Song template on the side */}
        <SongTemplateCard metadata={metadata} format={format} />

        {/* Ready to save panel */}
        <div className="panel completed-panel">
          <div className="completed-panel__header">
            <div className="completed-panel__check" aria-hidden="true">
              <CheckLargeIcon />
            </div>
            <div>
              <span className="hud-label text-success">AUTOMATIC DOWNLOAD</span>
              <h2 className="completed-panel__title display-md">Processing complete</h2>
            </div>
          </div>

          <p className="completed-panel__subtitle body-md text-muted">
            Your file <strong>{targetFilename}</strong> is automatically downloading. If your browser didn&apos;t start the download, click below to save it again.
          </p>

          <div className="completed-panel__meta-summary">
            <span className="badge badge-accent">{format.ext.toUpperCase()}</span>
            {format.resolution && <span className="badge">{format.resolution}</span>}
            <span className="hud-label text-muted">{formatFileSize(format.filesize_approx)}</span>
          </div>

          <div className="completed-panel__actions">
            <button
              type="button"
              className="btn-accent btn-lg"
              onClick={handleSave}
              disabled={saving}
              id="save-file-btn"
              aria-label={`Save ${format.ext.toUpperCase()} file`}
            >
              {saving ? (
                <>
                  <span className="format-spinner" aria-hidden="true" />
                  Saving…
                </>
              ) : (
                <>
                  <SaveIcon />
                  Save file
                </>
              )}
            </button>
            <button
              type="button"
              className="btn-ghost"
              onClick={onReset}
              id="download-another-btn"
            >
              Download another
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Error state
// ─────────────────────────────────────────────────────────────────────────────
interface ErrorPanelProps {
  message: string;
  detail?: string;
  onReset: () => void;
  onRetry?: () => void;
}

function ErrorPanel({ message, detail, onReset, onRetry }: ErrorPanelProps) {
  return (
    <section
      className="progress-section animate-fade-up"
      id="error-section"
      aria-label="Download error"
      aria-live="assertive"
    >
      <div className="panel error-panel">
        <div className="error-panel__header">
          <div className="error-panel__icon" aria-hidden="true">
            <AlertIcon />
          </div>
          <div>
            <span className="hud-label text-error">DOWNLOAD FAILED</span>
            <h2 className="error-panel__title display-md">Something went wrong</h2>
          </div>
        </div>

        <p className="error-panel__detail body-md">{message}</p>
        {detail && (
          <p className="body-sm text-faint error-panel__tech-detail">{detail}</p>
        )}

        <div className="error-panel__actions">
          {onRetry && (
            <button type="button" className="btn-primary" onClick={onRetry} id="retry-btn">
              <RefreshIcon />
              Try again
            </button>
          )}
          <button type="button" className="btn-ghost" onClick={onReset} id="start-over-btn">
            Start over
          </button>
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Dispatcher
// ─────────────────────────────────────────────────────────────────────────────
interface ProgressPanelProps {
  phase: AppPhase;
  onCancel: () => void;
  onPause?: () => void;
  onResume?: () => void;
  onReset: () => void;
}

export function ProgressPanel({
  phase,
  onCancel,
  onPause,
  onResume,
  onReset,
}: ProgressPanelProps) {
  if (phase.kind === 'processing') {
    return (
      <ProcessingPanel
        metadata={phase.metadata}
        format={phase.format}
        job={phase.job}
        onCancel={onCancel}
        onPause={onPause}
        onResume={onResume}
      />
    );
  }
  if (phase.kind === 'completed') {
    return (
      <CompletedPanel
        metadata={phase.metadata}
        format={phase.format}
        job={phase.job}
        onReset={onReset}
      />
    );
  }
  if (phase.kind === 'error') {
    return (
      <ErrorPanel
        message={phase.message}
        detail={phase.detail}
        onReset={onReset}
      />
    );
  }
  return null;
}

/* ── Icons ─────────────────────────────────────────────────────────────── */
function SpinnerIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true" style={{ animation: 'spin 1s linear infinite' }}>
      <path d="M21 12a9 9 0 1 1-6.219-8.56" strokeLinecap="round"/>
    </svg>
  );
}

function CheckLargeIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  );
}

function XIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="5" y="4" width="4" height="16" />
      <rect x="15" y="4" width="4" height="16" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <polygon points="6 4 20 12 6 20 6 4" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
    </svg>
  );
}

function SaveIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
      <polyline points="17 21 17 13 7 13 7 21"/>
      <polyline points="7 3 7 8 15 8"/>
    </svg>
  );
}

function ThumbnailIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="2" y="4" width="20" height="16"/>
      <circle cx="8.5" cy="9.5" r="1.5"/>
      <polyline points="21 15 16 10 5 21"/>
    </svg>
  );
}

function ChannelIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" style={{ marginRight: 6, flexShrink: 0 }}>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
      <circle cx="12" cy="7" r="4"/>
    </svg>
  );
}
