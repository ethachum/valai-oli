import './PlaylistQueuedCard.css';

interface PlaylistQueuedCardProps {
  playlistTitle: string;
  enqueuedCount: number;
  onReset: () => void;
}

export function PlaylistQueuedCard({
  playlistTitle,
  enqueuedCount,
  onReset,
}: PlaylistQueuedCardProps) {
  const openHistory = () => {
    // Dispatch click or focus on navbar history button
    const btn = document.querySelector('.navbar__history-btn') as HTMLButtonElement | null;
    if (btn) {
      btn.click();
    }
  };

  return (
    <div className="pl-queued-card animate-fade-up">
      <div className="pl-queued-card__glow-icon" aria-hidden="true">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      </div>

      <div className="pl-queued-card__header">
        <span className="pl-queued-badge">Sequential Queue Active</span>
        <h2 className="pl-queued-card__title">
          {enqueuedCount} Videos Enqueued
        </h2>
        <p className="pl-queued-card__sub" title={playlistTitle}>
          From playlist: <strong>{playlistTitle}</strong>
        </p>
      </div>

      <div className="pl-queued-card__features">
        <div className="pl-feature-item">
          <div className="pl-feature-icon">🔢</div>
          <div className="pl-feature-text">
            <strong>Numbered Filenames</strong>
            <span>Saved as <code>01 - Title</code>, <code>02 - Title</code> in sequence.</span>
          </div>
        </div>

        <div className="pl-feature-item">
          <div className="pl-feature-icon">🛡️</div>
          <div className="pl-feature-text">
            <strong>Fault Tolerant</strong>
            <span>If an individual video errors, the queue automatically advances to the next track.</span>
          </div>
        </div>

        <div className="pl-feature-item">
          <div className="pl-feature-icon">⚡</div>
          <div className="pl-feature-text">
            <strong>Live Navbar History</strong>
            <span>Watch real-time download and conversion progress in the Navbar menu above.</span>
          </div>
        </div>
      </div>

      <div className="pl-queued-card__actions">
        <button
          type="button"
          className="pl-queued-btn-primary"
          onClick={openHistory}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          View Downloads in Navbar
        </button>

        <button
          type="button"
          className="pl-queued-btn-secondary"
          onClick={onReset}
        >
          Download Another URL
        </button>
      </div>
    </div>
  );
}
