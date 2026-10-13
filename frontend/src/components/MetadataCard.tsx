import type { MetadataResponse } from '../types/api';
import './MetadataCard.css';

interface MetadataCardProps {
  metadata: MetadataResponse;
  onReset: () => void;
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function MetadataCard({ metadata, onReset }: MetadataCardProps) {
  const videoCount = metadata.formats.filter((f) => f.has_video).length;
  const audioCount = metadata.formats.filter((f) => !f.has_video).length;

  return (
    <div className="metadata-card animate-fade-up panel" id="metadata-section" role="region" aria-label="Video information">
      {/* Thumbnail */}
      <div className="metadata-card__thumb-wrap">
        {metadata.thumbnail ? (
          <img
            className="metadata-card__thumb"
            src={metadata.thumbnail}
            alt={`Thumbnail for ${metadata.title}`}
            loading="lazy"
          />
        ) : (
          <div className="metadata-card__thumb-placeholder" aria-label="No thumbnail available">
            <ThumbnailIcon />
          </div>
        )}
        {metadata.duration_seconds != null && (
          <span className="metadata-card__duration hud-label" aria-label={`Duration: ${formatDuration(metadata.duration_seconds)}`}>
            {formatDuration(metadata.duration_seconds)}
          </span>
        )}
      </div>

      {/* Info */}
      <div className="metadata-card__info">
        <div className="metadata-card__eyebrow">
          <span className="hud-label text-faint">
            <span>02</span>
            <span aria-hidden="true" style={{ margin: '0 6px' }}>/</span>
            Video
          </span>
          <button
            className="metadata-card__change-btn hud-label text-muted"
            onClick={onReset}
            aria-label="Change URL"
          >
            ← Change URL
          </button>
        </div>

        <h2 className="metadata-card__title display-md">{metadata.title}</h2>

        {metadata.uploader && (
          <p className="metadata-card__uploader body-sm text-muted">
            <ChannelIcon />
            {metadata.uploader}
          </p>
        )}

        <div className="metadata-card__badges" role="list" aria-label="Format availability">
          {videoCount > 0 && (
            <span className="badge badge-accent" role="listitem">
              {videoCount} Video format{videoCount !== 1 ? 's' : ''}
            </span>
          )}
          {audioCount > 0 && (
            <span className="badge" role="listitem" style={{ borderColor: 'var(--line-strong)', color: 'var(--muted)' }}>
              {audioCount} Audio format{audioCount !== 1 ? 's' : ''}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function ThumbnailIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <rect x="2" y="4" width="20" height="16" rx="2"/>
      <circle cx="8.5" cy="9.5" r="1.5"/>
      <polyline points="21 15 16 10 5 21"/>
    </svg>
  );
}

function ChannelIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" style={{ marginRight: 6, flexShrink: 0 }}>
      <circle cx="12" cy="8" r="4"/>
      <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
    </svg>
  );
}
