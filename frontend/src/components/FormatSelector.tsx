import { useState } from 'react';
import type { FormatInfo, MetadataResponse } from '../types/api';
import './FormatSelector.css';

// ── Extra synthetic audio formats not returned by yt-dlp metadata ────────────
// These are always offered; the backend routes them through --audio-quality.

const EXTRA_AUDIO_FORMATS: FormatInfo[] = [
  {
    format_id: 'bestaudio/mp3:320k',
    ext: 'mp3',
    resolution: null,
    vcodec: null,
    acodec: 'mp3',
    filesize_approx: null,
    has_video: false,
    has_audio: true,
    note: 'MP3 · 320 kbps CBR',
  },
  {
    format_id: 'bestaudio/flac',
    ext: 'flac',
    resolution: null,
    vcodec: null,
    acodec: 'flac',
    filesize_approx: null,
    has_video: false,
    has_audio: true,
    note: 'FLAC · Lossless',
  },
];

// ── Helpers ──────────────────────────────────────────────────────────────────

interface FormatSelectorProps {
  metadata: MetadataResponse;
  onSelect: (format: FormatInfo, startTime?: string, endTime?: string, isGif?: boolean) => void;
  isLoading?: boolean;
}

type Tab = 'video' | 'audio';

function formatFileSize(bytes: number | null): string {
  if (!bytes) return '—';
  if (bytes < 1_000_000) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1_000_000).toFixed(1)} MB`;
}

function resolLabel(f: FormatInfo): string {
  if (f.resolution) {
    const match = f.resolution.match(/\d+/g);
    if (match && match.length >= 2) {
      const w = Math.max(Number(match[0]), Number(match[1]));
      const h = Math.min(Number(match[0]), Number(match[1]));
      if (h >= 4320 || w >= 7680) return '8K';
      if (h >= 2160 || w >= 3840) return '4K';
      if (h >= 1440 || w >= 2560) return '2K';
      return `${h}P`;
    }
    return f.resolution;
  }
  // For audio: show a short quality label from the note
  if (f.ext === 'flac') return 'FLAC';
  if (f.note?.includes('320')) return '320K';
  if (f.note?.includes('192')) return '192K';
  if (f.note?.includes('128')) return '128K';
  return f.ext.toUpperCase();
}

/** Parse "mm:ss" or "hh:mm:ss" or plain seconds; return null if invalid. */
function parseTimestamp(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  // Allow plain number (seconds)
  if (/^\d+(\.\d+)?$/.test(trimmed)) return trimmed;
  // Allow M:SS or H:MM:SS
  if (/^\d+:\d{2}(:\d{2})?$/.test(trimmed)) return trimmed;
  return null;
}

// ── FormatCard ───────────────────────────────────────────────────────────────

function FormatCard({
  format,
  selected,
  onSelect,
  tab,
}: {
  format: FormatInfo;
  selected: boolean;
  onSelect: () => void;
  tab: Tab;
}) {
  const needsMerge = format.note?.toLowerCase().includes('merge');
  const sizeLabel = formatFileSize(format.filesize_approx);
  const codecLabel = tab === 'video'
    ? format.vcodec?.split('.')[0] ?? '—'
    : format.acodec?.toUpperCase() ?? '—';

  // Special badge for FLAC / 320k
  const isLossless = format.format_id.includes('flac');
  const is320k = format.format_id.includes('320k');

  return (
    <button
      type="button"
      className={`format-card panel ${selected ? 'format-card--selected' : ''}`}
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`${resolLabel(format)} ${format.ext.toUpperCase()} format${needsMerge ? ', requires stream merge' : ''}, ${sizeLabel}`}
    >
      {/* Resolution / ext badge */}
      <div className="format-card__top">
        <span className={`format-card__res hud-label ${selected ? 'text-accent' : 'text-strong'}`}>
          {resolLabel(format)}
        </span>
        <span className="format-card__ext badge">{format.ext.toUpperCase()}</span>
      </div>

      {/* Codec + container */}
      <div className="format-card__codec body-sm text-muted">{codecLabel}</div>

      {/* Bottom row */}
      <div className="format-card__bottom">
        {sizeLabel !== '—' && (
          <span className="format-card__size hud-label text-faint">{sizeLabel}</span>
        )}
        {needsMerge && (
          <span className="format-card__merge-badge hud-label" title="Audio and video streams will be merged by FFmpeg">
            <MergeIcon />
            Merge
          </span>
        )}
        {isLossless && (
          <span className="format-card__quality-badge format-card__quality-badge--lossless hud-label" title="Lossless audio">
            <LosslessIcon />
            Lossless
          </span>
        )}
        {is320k && (
          <span className="format-card__quality-badge format-card__quality-badge--hq hud-label" title="High quality 320 kbps CBR">
            <HiQualityIcon />
            Hi-Fi
          </span>
        )}
      </div>

      {/* Note */}
      {format.note && (
        <p className="format-card__note body-sm text-faint">{format.note}</p>
      )}

      {/* Selection indicator */}
      {selected && <span className="format-card__check"><CheckIcon /></span>}
    </button>
  );
}

// ── ClipInputs ───────────────────────────────────────────────────────────────

function ClipInputs({
  enabled,
  onToggle,
  startTime,
  endTime,
  onStartChange,
  onEndChange,
  duration,
}: {
  enabled: boolean;
  onToggle: () => void;
  startTime: string;
  endTime: string;
  onStartChange: (v: string) => void;
  onEndChange: (v: string) => void;
  duration: number | null;
}) {
  const startErr = startTime && !parseTimestamp(startTime);
  const endErr   = endTime   && !parseTimestamp(endTime);

  return (
    <div className="clip-panel">
      <button
        type="button"
        className={`clip-toggle hud-label ${enabled ? 'clip-toggle--active' : ''}`}
        onClick={onToggle}
        aria-pressed={enabled}
        id="clip-toggle-btn"
      >
        <ScissorsIcon />
        {enabled ? 'Clip enabled' : 'Clip / Trim'}
        <span className="clip-toggle__chevron" aria-hidden="true">{enabled ? '▲' : '▼'}</span>
      </button>

      {enabled && (
        <div className="clip-fields animate-fade-up">
          <p className="clip-hint body-sm text-faint">
            <InfoIcon />
            Enter timestamps as <code>M:SS</code>, <code>H:MM:SS</code>, or plain seconds.
            {duration && (
              <> Full length: <strong>{fmtDuration(duration)}</strong></>
            )}
          </p>
          <div className="clip-inputs-row">
            <label className="clip-label" htmlFor="clip-start">
              <span className="hud-label text-faint">Start</span>
              <input
                id="clip-start"
                className={`clip-input${startErr ? ' clip-input--error' : ''}`}
                type="text"
                placeholder="0:00"
                value={startTime}
                onChange={(e) => onStartChange(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
              {startErr && <span className="clip-error body-sm">Invalid timestamp</span>}
            </label>

            <span className="clip-arrow hud-label text-faint" aria-hidden="true">→</span>

            <label className="clip-label" htmlFor="clip-end">
              <span className="hud-label text-faint">End</span>
              <input
                id="clip-end"
                className={`clip-input${endErr ? ' clip-input--error' : ''}`}
                type="text"
                placeholder={duration ? fmtDuration(duration) : 'end'}
                value={endTime}
                onChange={(e) => onEndChange(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
              {endErr && <span className="clip-error body-sm">Invalid timestamp</span>}
            </label>
          </div>
        </div>
      )}
    </div>
  );
}

function fmtDuration(secs: number): string {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ── Main FormatSelector ──────────────────────────────────────────────────────

export function FormatSelector({ metadata, onSelect, isLoading }: FormatSelectorProps) {
  const [tab, setTab] = useState<Tab>('video');
  const [selected, setSelected] = useState<string | null>(null);

  // Clip state
  const [clipEnabled, setClipEnabled] = useState(false);
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');

  // Merge extra audio formats — deduplicate by format_id
  const existingIds = new Set(metadata.formats.map((f) => f.format_id));
  const extraAudio = EXTRA_AUDIO_FORMATS.filter((f) => !existingIds.has(f.format_id));

  const videoFormats = metadata.formats.filter((f) => f.has_video);
  const audioFormats = [
    ...metadata.formats.filter((f) => !f.has_video),
    ...extraAudio,
  ];
  const activeFormats = tab === 'video' ? videoFormats : audioFormats;

  function handleSelect(format: FormatInfo) {
    setSelected(format.format_id);
  }

  const selectedFormat = activeFormats.find((f) => f.format_id === selected) ?? null;

  // Validate timestamps before allowing download
  const startValid = !startTime || Boolean(parseTimestamp(startTime));
  const endValid   = !endTime   || Boolean(parseTimestamp(endTime));
  const clipOk     = !clipEnabled || (startValid && endValid);

  function handleDownload() {
    if (!selectedFormat) return;
    const st = clipEnabled && startTime ? (parseTimestamp(startTime) ?? undefined) : undefined;
    const et = clipEnabled && endTime   ? (parseTimestamp(endTime)   ?? undefined) : undefined;
    onSelect(selectedFormat, st, et, false);
  }

  function handleExportGif() {
    // Pick highest/selected video format or default best
    const videoFmt = selectedFormat?.has_video
      ? selectedFormat
      : (videoFormats[0] ?? { format_id: 'bestvideo+bestaudio/best', ext: 'mp4', resolution: '720p', vcodec: 'avc1', acodec: null, filesize_approx: null, has_video: true, has_audio: false, note: 'Default' });
    const st = clipEnabled && startTime ? (parseTimestamp(startTime) ?? undefined) : (startTime ? parseTimestamp(startTime) ?? undefined : undefined);
    const et = clipEnabled && endTime   ? (parseTimestamp(endTime)   ?? undefined) : (endTime ? parseTimestamp(endTime) ?? undefined : undefined);
    onSelect(videoFmt, st, et, true);
  }

  return (
    <section className="format-section animate-fade-up" id="format-selector-section" aria-label="Select download format">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="format-section__header">
        <div>
          <p className="hud-label text-faint" style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span>03</span>
            <span aria-hidden="true">/</span>
            Select Format
          </p>
          <h2 className="display-md">Choose quality &amp; format</h2>
        </div>
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────────────── */}
      <div className="format-tabs" role="tablist" aria-label="Format type">
        <button
          role="tab"
          className={`format-tab hud-label ${tab === 'video' ? 'format-tab--active' : ''}`}
          aria-selected={tab === 'video'}
          id="tab-video"
          aria-controls="tabpanel-formats"
          onClick={() => { setTab('video'); setSelected(null); }}
        >
          <VideoIcon />
          Video ({videoFormats.length})
        </button>
        <button
          role="tab"
          className={`format-tab hud-label ${tab === 'audio' ? 'format-tab--active' : ''}`}
          aria-selected={tab === 'audio'}
          id="tab-audio"
          aria-controls="tabpanel-formats"
          onClick={() => { setTab('audio'); setSelected(null); }}
        >
          <AudioIcon />
          Audio only ({audioFormats.length})
        </button>
      </div>

      {/* ── Format grid ──────────────────────────────────────────────────── */}
      <div
        id="tabpanel-formats"
        role="tabpanel"
        aria-labelledby={`tab-${tab}`}
        className="format-grid"
      >
        {activeFormats.length === 0 ? (
          <p className="format-empty body-sm text-muted">No {tab} formats available for this video.</p>
        ) : (
          activeFormats.map((f) => (
            <FormatCard
              key={f.format_id}
              format={f}
              selected={selected === f.format_id}
              onSelect={() => handleSelect(f)}
              tab={tab}
            />
          ))
        )}
      </div>

      {/* ── Clip / Trim panel ────────────────────────────────────────────── */}
      <ClipInputs
        enabled={clipEnabled}
        onToggle={() => setClipEnabled((v) => !v)}
        startTime={startTime}
        endTime={endTime}
        onStartChange={setStartTime}
        onEndChange={setEndTime}
        duration={metadata.duration_seconds}
      />

      {/* ── Download CTA ─────────────────────────────────────────────────── */}
      <div className="format-section__cta">
        {tab === 'audio' && selectedFormat && (
          <p className="format-cta__note body-sm text-muted">
            <InfoIcon />
            Audio conversion changes the container; it cannot improve the source bitrate.
          </p>
        )}
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
          <button
            type="button"
            className="btn-accent btn-lg format-section__download-btn"
            disabled={!selectedFormat || isLoading || !clipOk}
            onClick={handleDownload}
            id="start-download-btn"
            aria-label={selectedFormat ? `Download as ${selectedFormat.ext.toUpperCase()} — ${selectedFormat.note ?? ''}` : 'Select a format first'}
          >
            {isLoading ? (
              <>
                <span className="format-spinner" aria-hidden="true" />
                Starting…
              </>
            ) : (
              <>
                <DownloadIcon />
                {selectedFormat
                  ? `Download ${selectedFormat.ext.toUpperCase()}${clipEnabled && (startTime || endTime) ? ' · Clip' : ''}`
                  : 'Select a format'}
              </>
            )}
          </button>

          {/* GIF Export option */}
          <button
            type="button"
            className="btn-secondary btn-lg"
            disabled={isLoading || !clipOk}
            onClick={handleExportGif}
            id="export-gif-btn"
            title="Convert selected portion into an animated GIF clip"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}
          >
            <span style={{ fontSize: '12px', fontWeight: 700, padding: '2px 5px', borderRadius: '4px', background: 'rgba(255,255,255,0.15)' }}>GIF</span>
            Export as GIF {clipEnabled && (startTime || endTime) ? 'Clip' : ''}
          </button>
        </div>
      </div>
    </section>
  );
}

/* ── Icons ─────────────────────────────────────────────────────────────── */
function VideoIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/>
    </svg>
  );
}
function AudioIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>
    </svg>
  );
}
function MergeIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M18 21V8M18 8l-4 4m4-4 4 4M6 3v13M6 16l-4-4m4 4 4-4"/>
    </svg>
  );
}
function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  );
}
function DownloadIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
      <path d="M12 17V3M6 11l6 6 6-6M19 21H5"/>
    </svg>
  );
}
function InfoIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" style={{ flexShrink: 0 }}>
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  );
}
function ScissorsIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>
      <line x1="20" y1="4" x2="8.12" y2="15.88"/>
      <line x1="14.47" y1="14.48" x2="20" y2="20"/>
      <line x1="8.12" y1="8.12" x2="12" y2="12"/>
    </svg>
  );
}
function LosslessIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
    </svg>
  );
}
function HiQualityIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
    </svg>
  );
}
