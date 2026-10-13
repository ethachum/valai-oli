import { useState, useMemo } from 'react';
import type { PlaylistMetadataResponse, PlaylistItem } from '../types/api';
import './PlaylistSelector.css';

interface PlaylistSelectorProps {
  playlist: PlaylistMetadataResponse;
  onDownload: (items: PlaylistItem[], preset: string) => void;
  onCancel: () => void;
}

const PRESETS = [
  { id: '1080p', label: '1080p Full HD', sub: 'MP4 · High Definition', icon: '🎬' },
  { id: '720p', label: '720p HD', sub: 'MP4 · Standard HD', icon: '📺' },
  { id: '480p', label: '480p SD', sub: 'MP4 · Compact size', icon: '📱' },
  { id: 'best', label: 'Maximum Quality', sub: 'MP4 · Best Available', icon: '🌟' },
  { id: 'mp3', label: 'Audio MP3', sub: '192 kbps · Music', icon: '🎵' },
  { id: 'm4a', label: 'Audio M4A', sub: 'AAC · High Efficiency', icon: '🎧' },
];

function formatDuration(seconds: number | null): string {
  if (!seconds || seconds <= 0) return '--:--';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const remM = m % 60;
    return `${h}:${remM.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function PlaylistSelector({ playlist, onDownload, onCancel }: PlaylistSelectorProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => {
    // Default to all selected
    return new Set(playlist.entries.map((e) => e.video_id || String(e.index)));
  });
  const [selectedPreset, setSelectedPreset] = useState<string>('1080p');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const filteredEntries = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return playlist.entries;
    return playlist.entries.filter((entry) =>
      entry.title.toLowerCase().includes(q)
    );
  }, [playlist.entries, searchQuery]);

  const allVisibleSelected = useMemo(() => {
    if (filteredEntries.length === 0) return false;
    return filteredEntries.every((e) => selectedIds.has(e.video_id || String(e.index)));
  }, [filteredEntries, selectedIds]);

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        filteredEntries.forEach((e) => next.delete(e.video_id || String(e.index)));
      } else {
        filteredEntries.forEach((e) => next.add(e.video_id || String(e.index)));
      }
      return next;
    });
  };

  const toggleItem = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectedCount = selectedIds.size;
  const totalCount = playlist.entries.length;

  const handleDownload = () => {
    if (selectedCount === 0 || isSubmitting) return;
    setIsSubmitting(true);
    const chosen = playlist.entries.filter((e) =>
      selectedIds.has(e.video_id || String(e.index))
    );
    onDownload(chosen, selectedPreset);
  };

  return (
    <div className="pl-container animate-fade-up">
      {/* ── Playlist Header ────────────────────────────────────────────── */}
      <header className="pl-header">
        <div className="pl-header__info">
          <div className="pl-header__badge-row">
            <span className="pl-badge pl-badge--playlist">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 15V6" />
                <path d="M18.5 18a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z" />
                <path d="M12 12H3" />
                <path d="M16 6H3" />
                <path d="M12 18H3" />
              </svg>
              YouTube Playlist
            </span>
            <span className="pl-badge pl-badge--count">{totalCount} videos</span>
          </div>

          <h2 className="pl-header__title" title={playlist.title}>
            {playlist.title}
          </h2>

          {playlist.uploader && (
            <p className="pl-header__uploader">
              By <span className="pl-uploader-name">{playlist.uploader}</span>
            </p>
          )}
        </div>

        <button
          type="button"
          className="pl-btn-secondary"
          onClick={onCancel}
          aria-label="Cancel and change URL"
        >
          Cancel
        </button>
      </header>

      {/* ── Quality Presets ─────────────────────────────────────────────── */}
      <section className="pl-section" aria-labelledby="quality-preset-heading">
        <div className="pl-section__title-row">
          <h3 id="quality-preset-heading" className="pl-section__title">
            1. Select Shared Quality Preset
          </h3>
          <span className="pl-section__hint">Applied to all downloaded sequence files</span>
        </div>

        <div className="pl-presets-grid" role="radiogroup" aria-label="Quality Preset">
          {PRESETS.map((preset) => {
            const isSelected = selectedPreset === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                role="radio"
                aria-checked={isSelected}
                className={`pl-preset-card ${isSelected ? 'pl-preset-card--selected' : ''}`}
                onClick={() => setSelectedPreset(preset.id)}
              >
                <div className="pl-preset-card__top">
                  <span className="pl-preset-card__icon" aria-hidden="true">{preset.icon}</span>
                  <span className="pl-preset-card__label">{preset.label}</span>
                </div>
                <span className="pl-preset-card__sub">{preset.sub}</span>
              </button>
            );
          })}
        </div>
      </section>

      {/* ── Item Selection Section ─────────────────────────────────────── */}
      <section className="pl-section" aria-labelledby="select-items-heading">
        <div className="pl-selection-bar">
          <div className="pl-selection-bar__left">
            <h3 id="select-items-heading" className="pl-section__title">
              2. Choose Videos to Download
            </h3>
            <span className="pl-count-indicator">
              <strong>{selectedCount}</strong> of {totalCount} selected
            </span>
          </div>

          <div className="pl-selection-bar__actions">
            <button
              type="button"
              className="pl-action-btn"
              onClick={toggleSelectAll}
            >
              {allVisibleSelected ? 'Deselect Visible' : 'Select All'}
            </button>
          </div>
        </div>

        {/* Filter Input */}
        <div className="pl-search-wrap">
          <svg className="pl-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            className="pl-search-input"
            placeholder="Search playlist videos…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search playlist videos"
          />
          {searchQuery && (
            <button
              type="button"
              className="pl-search-clear"
              onClick={() => setSearchQuery('')}
              aria-label="Clear search"
            >
              ✕
            </button>
          )}
        </div>

        {/* Video List */}
        <div className="pl-list" role="list">
          {filteredEntries.map((entry) => {
            const entryId = entry.video_id || String(entry.index);
            const isChecked = selectedIds.has(entryId);

            return (
              <div
                key={entryId}
                role="listitem"
                className={`pl-item ${isChecked ? 'pl-item--checked' : ''}`}
                onClick={() => toggleItem(entryId)}
              >
                <div className="pl-item__checkbox-wrap" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    id={`pl-chk-${entryId}`}
                    className="pl-item__checkbox"
                    checked={isChecked}
                    onChange={() => toggleItem(entryId)}
                    aria-label={`Select ${entry.title}`}
                  />
                </div>

                <div className="pl-item__track-num">
                  #{entry.index}
                </div>

                <div className="pl-item__thumb-wrap">
                  {entry.thumbnail ? (
                    <img
                      src={entry.thumbnail}
                      alt=""
                      className="pl-item__thumb"
                      loading="lazy"
                    />
                  ) : (
                    <div className="pl-item__thumb-placeholder">
                      ▶
                    </div>
                  )}
                  {entry.duration_seconds ? (
                    <span className="pl-item__duration">
                      {formatDuration(entry.duration_seconds)}
                    </span>
                  ) : null}
                </div>

                <div className="pl-item__meta">
                  <span className="pl-item__title" title={entry.title}>
                    {entry.title}
                  </span>
                  <span className="pl-item__filename-preview">
                    File: {String(entry.index).padStart(2, '0')} - {entry.title}
                  </span>
                </div>
              </div>
            );
          })}

          {filteredEntries.length === 0 && (
            <div className="pl-empty-search">
              No videos matched &ldquo;{searchQuery}&rdquo;
            </div>
          )}
        </div>
      </section>

      {/* ── Bottom Action Footer ───────────────────────────────────────── */}
      <footer className="pl-footer">
        <div className="pl-footer__note">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <span>
            Downloads execute sequentially to avoid rate limiting. If any item fails, the sequence continues.
          </span>
        </div>

        <button
          type="button"
          className="pl-download-btn"
          disabled={selectedCount === 0 || isSubmitting}
          onClick={handleDownload}
        >
          {isSubmitting ? (
            'Queueing sequence…'
          ) : (
            <>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Download {selectedCount} Videos Sequentially
            </>
          )}
        </button>
      </footer>
    </div>
  );
}
