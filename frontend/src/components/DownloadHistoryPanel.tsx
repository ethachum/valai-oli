import { useEffect, useRef, useState } from "react";
import type { HistoryEntry } from "../hooks/useDownloadHistory";
import "./DownloadHistoryPanel.css";

// ── Inline SVGs (Encoding-safe) ──────────────────────────────────────────────

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="6" y="4" width="4" height="16" rx="1" />
      <rect x="14" y="4" width="4" height="16" rx="1" />
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

function StopIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="5" y="5" width="14" height="14" rx="2" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function VideoPlaceholderIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

function ZipIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
      <line x1="12" y1="22.08" x2="12" y2="12" />
    </svg>
  );
}

function RetryIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 4v6h6" />
      <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
    </svg>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtState(state: string): string {
  const map: Record<string, string> = {
    queued: "Queued",
    downloading: "Downloading",
    merging: "Merging",
    converting: "Converting",
    validating: "Validating",
    completed: "Completed",
    failed: "Failed",
    cancelled: "Cancelled",
    paused: "Paused",
  };
  return map[state] ?? state;
}

function stateClass(state: string): string {
  if (state === "completed") return "dhp-entry--completed";
  if (state === "failed") return "dhp-entry--failed";
  if (state === "cancelled") return "dhp-entry--cancelled";
  if (state === "paused") return "dhp-entry--paused";
  if (["downloading", "merging", "converting", "validating"].includes(state))
    return "dhp-entry--active";
  return "dhp-entry--queued";
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function ProgressBar({ pct }: { pct: number | null }) {
  if (pct === null || pct === undefined) return null;
  return (
    <div className="dhp-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="dhp-bar__fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

// ── Entry component ──────────────────────────────────────────────────────────

interface EntryProps {
  entry: HistoryEntry;
  onRemove: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onCancel: (id: string) => void;
  onRetry: (entry: HistoryEntry) => void;
}

function HistoryEntryRow({ entry, onRemove, onPause, onResume, onCancel, onRetry }: EntryProps) {
  const isTerminal = ["completed", "failed", "cancelled"].includes(entry.state);
  const isPaused = entry.state === "paused";
  const isDownloading = ["downloading", "merging", "converting", "validating"].includes(entry.state);
  const isQueued = entry.state === "queued";
  const showProgress = (isDownloading || isPaused) && entry.progress_percent !== null;
  const canDownload = entry.state === "completed";

  return (
    <li className={`dhp-entry ${stateClass(entry.state)}`}>
      {/* Thumbnail */}
      <div className="dhp-entry__thumb">
        {entry.thumbnail ? (
          <img src={entry.thumbnail} alt="" loading="lazy" className="dhp-entry__thumb-img" />
        ) : (
          <span className="dhp-entry__thumb-placeholder" aria-hidden="true">
            <VideoPlaceholderIcon />
          </span>
        )}
      </div>

      {/* Info */}
      <div className="dhp-entry__info">
        <p className="dhp-entry__title hud-label" title={entry.title ?? entry.job_id}>
          {entry.title ?? "Untitled"}
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
          <span className="dhp-entry__meta hud-label text-faint">
            {fmtState(entry.state)}
            {entry.is_gif ? " · GIF" : entry.output_format ? ` · ${entry.output_format.toUpperCase()}` : ""}
            {entry.channel ? ` · ${entry.channel}` : ""}
            {entry.completed_at ? ` · ${fmtTime(entry.completed_at)}` : ""}
            {entry.created_at && !entry.completed_at ? ` · ${fmtTime(entry.created_at)}` : ""}
          </span>
          {entry.is_gif && (
            <span style={{ fontSize: "10px", fontWeight: 700, padding: "1px 4px", borderRadius: "3px", background: "hsl(280 80% 50% / 0.3)", color: "hsl(280 90% 75%)" }}>
              GIF
            </span>
          )}
        </div>
        {/* Waveform preview if available */}
        {entry.state === "completed" && entry.waveform_path && (
          <div style={{ marginTop: "3px", height: "16px", borderRadius: "3px", overflow: "hidden", background: "hsl(220 15% 14%)" }}>
            <img
              src={`/api/jobs/${entry.job_id}/waveform`}
              alt="Audio Waveform"
              style={{ width: "100%", height: "100%", objectFit: "cover", opacity: 0.85 }}
              loading="lazy"
            />
          </div>
        )}
        {showProgress && <ProgressBar pct={entry.progress_percent} />}
        {entry.state === "failed" && entry.error && (
          <p className="dhp-entry__error hud-label">{entry.error}</p>
        )}
      </div>

      {/* Actions */}
      <div className="dhp-entry__actions">
        {/* Active: Downloading -> Pause + Stop */}
        {isDownloading && (
          <>
            <button
              type="button"
              className="dhp-action-btn dhp-action-btn--pause"
              onClick={() => onPause(entry.job_id)}
              title="Pause download"
              aria-label={`Pause ${entry.title ?? entry.job_id}`}
            >
              <PauseIcon />
            </button>
            <button
              type="button"
              className="dhp-action-btn dhp-action-btn--cancel"
              onClick={() => onCancel(entry.job_id)}
              title="Stop / Cancel download"
              aria-label={`Stop ${entry.title ?? entry.job_id}`}
            >
              <StopIcon />
            </button>
          </>
        )}

        {/* Active: Paused -> Play / Resume + Stop */}
        {isPaused && (
          <>
            <button
              type="button"
              className="dhp-action-btn dhp-action-btn--resume"
              onClick={() => onResume(entry.job_id)}
              title="Resume download"
              aria-label={`Resume ${entry.title ?? entry.job_id}`}
            >
              <PlayIcon />
            </button>
            <button
              type="button"
              className="dhp-action-btn dhp-action-btn--cancel"
              onClick={() => onCancel(entry.job_id)}
              title="Stop / Cancel download"
              aria-label={`Stop ${entry.title ?? entry.job_id}`}
            >
              <StopIcon />
            </button>
          </>
        )}

        {/* Active: Queued -> Stop */}
        {isQueued && (
          <button
            type="button"
            className="dhp-action-btn dhp-action-btn--cancel"
            onClick={() => onCancel(entry.job_id)}
            title="Cancel queued download"
            aria-label={`Cancel ${entry.title ?? entry.job_id}`}
          >
            <StopIcon />
          </button>
        )}

        {/* Completed: Save File + Remove */}
        {canDownload && (
          <a
            href={`/api/jobs/${entry.job_id}/download`}
            className="dhp-action-btn dhp-action-btn--download"
            download
            title="Save file to computer"
            aria-label={`Save ${entry.title}`}
          >
            <DownloadIcon />
          </a>
        )}

        {/* Failed items: Retry (curved arrow) */}
        {entry.state === "failed" && (
          <button
            type="button"
            className="dhp-action-btn dhp-action-btn--retry"
            onClick={() => onRetry(entry)}
            title="Retry download"
            aria-label={`Retry ${entry.title ?? entry.job_id}`}
          >
            <RetryIcon />
          </button>
        )}

        {/* Terminal items: Remove */}
        {isTerminal && (
          <button
            type="button"
            className="dhp-action-btn dhp-action-btn--remove"
            onClick={() => onRemove(entry.job_id)}
            title="Remove from history"
            aria-label={`Remove ${entry.title ?? entry.job_id}`}
          >
            <CloseIcon />
          </button>
        )}
      </div>
    </li>
  );
}

// ── Panel component ──────────────────────────────────────────────────────────

interface DownloadHistoryPanelProps {
  entries: HistoryEntry[];
  hasFinished: boolean;
  anchorRef: React.RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onRemove: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onCancel: (id: string) => void;
  onRetry: (entry: HistoryEntry) => void;
  onClearFinished: () => void;
}

export function DownloadHistoryPanel({
  entries,
  hasFinished,
  anchorRef,
  onClose,
  onRemove,
  onPause,
  onResume,
  onCancel,
  onRetry,
  onClearFinished,
}: DownloadHistoryPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on click-outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        panelRef.current &&
        !panelRef.current.contains(e.target as Node) &&
        anchorRef.current &&
        !anchorRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [anchorRef, onClose]);

  // Close on Escape
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const completedEntries = entries.filter((e) => e.state === "completed");
  const [isZipping, setIsZipping] = useState(false);

  const handleDownloadAll = () => {
    if (completedEntries.length === 0) return;
    completedEntries.forEach((entry, idx) => {
      setTimeout(() => {
        const link = document.createElement("a");
        link.href = `/api/jobs/${entry.job_id}/download`;
        link.download = "";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }, idx * 450);
    });
  };

  const handleDownloadZip = async () => {
    if (completedEntries.length === 0 || isZipping) return;
    setIsZipping(true);
    try {
      const ids = completedEntries.map((e) => e.job_id).join(",");
      let cachedTitle = "";
      try {
        cachedTitle = sessionStorage.getItem("valaioli:last_playlist_title") || "";
      } catch {}
      const detectedTitle = completedEntries.find((e) => e.playlist_title)?.playlist_title || cachedTitle;
      const titleParam = detectedTitle ? `&title=${encodeURIComponent(detectedTitle)}` : "";
      const res = await fetch(`/api/jobs/zip?ids=${encodeURIComponent(ids)}${titleParam}`);
      if (!res.ok) {
        let msg = "No completed download files found to package.";
        try {
          const data = await res.json();
          if (data.detail) msg = data.detail;
        } catch {}
        alert(msg);
        return;
      }

      let filename = detectedTitle ? `${detectedTitle}.zip` : "playlist.zip";
      const disposition = res.headers.get("content-disposition");
      if (disposition) {
        const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
        if (utf8Match && utf8Match[1]) {
          filename = decodeURIComponent(utf8Match[1].replace(/["']/g, ""));
        } else {
          const match = disposition.match(/filename="?([^";]+)"?/i);
          if (match && match[1]) {
            filename = match[1].trim();
          }
        }
      }

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (err) {
      console.error("ZIP download failed", err);
      alert("ZIP download request failed. Please check backend connection.");
    } finally {
      setIsZipping(false);
    }
  };

  const [searchQuery, setSearchQuery] = useState("");
  const [filterType, setFilterType] = useState<"all" | "video" | "audio" | "gif">("all");

  const filteredEntries = entries.filter((e) => {
    // Text search by title or channel
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchTitle = (e.title ?? "").toLowerCase().includes(q);
      const matchChannel = (e.channel ?? "").toLowerCase().includes(q);
      if (!matchTitle && !matchChannel) return false;
    }
    // Type filter
    if (filterType === "gif") return Boolean(e.is_gif);
    if (filterType === "audio") return ["mp3", "m4a", "wav", "flac"].includes((e.output_format ?? "").toLowerCase()) && !e.is_gif;
    if (filterType === "video") return !["mp3", "m4a", "wav", "flac"].includes((e.output_format ?? "").toLowerCase()) && !e.is_gif;
    return true;
  });

  return (
    <div
      ref={panelRef}
      id="download-history-panel"
      role="dialog"
      aria-label="Download history"
      className="dhp-panel animate-fade-up"
    >
      {/* Header */}
      <div className="dhp-header">
        <span className="dhp-header__title hud-label">Downloads Library</span>
        <div className="dhp-header__actions">
          {hasFinished && (
            <button
              className="dhp-header__clear hud-label"
              onClick={onClearFinished}
              title="Clear completed, failed and cancelled"
            >
              Clear finished
            </button>
          )}
          <button
            type="button"
            className="dhp-header__close"
            onClick={onClose}
            aria-label="Close download history"
          >
            <CloseIcon />
          </button>
        </div>
      </div>

      {/* Library Filter & Search Toolbar */}
      {entries.length > 0 && (
        <div style={{ padding: "8px 12px", borderBottom: "1px solid hsl(220 15% 18% / 0.6)", display: "flex", flexDirection: "column", gap: "6px" }}>
          <input
            type="text"
            placeholder="Search title or channel…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: "100%",
              padding: "5px 8px",
              fontSize: "0.75rem",
              borderRadius: "6px",
              background: "hsl(220 20% 13%)",
              border: "1px solid hsl(220 15% 24%)",
              color: "#fff",
              outline: "none",
            }}
          />
          <div style={{ display: "flex", gap: "4px" }}>
            {(["all", "video", "audio", "gif"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setFilterType(t)}
                style={{
                  padding: "2px 8px",
                  fontSize: "0.68rem",
                  borderRadius: "4px",
                  border: "1px solid",
                  cursor: "pointer",
                  background: filterType === t ? "hsl(220 15% 25%)" : "transparent",
                  borderColor: filterType === t ? "hsl(220 15% 45%)" : "hsl(220 15% 20%)",
                  color: filterType === t ? "#fff" : "hsl(220 15% 65%)",
                  textTransform: "capitalize",
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Download All bar on top of downloads list */}
      {completedEntries.length > 0 && (
        <div className="dhp-bulk-bar">
          <div className="dhp-bulk-bar__info">
            <strong>{completedEntries.length}</strong> {completedEntries.length === 1 ? "file" : "files"} ready
          </div>
          <div className="dhp-bulk-bar__actions">
            <button
              type="button"
              className="dhp-bulk-btn dhp-bulk-btn--primary"
              onClick={handleDownloadAll}
              title="Download all completed files"
            >
              <DownloadIcon />
              Download All ({completedEntries.length})
            </button>
            {completedEntries.length > 1 && (
              <button
                type="button"
                className="dhp-bulk-btn dhp-bulk-btn--zip"
                onClick={handleDownloadZip}
                disabled={isZipping}
                title="Download all completed files packed in a ZIP archive"
              >
                <ZipIcon />
                {isZipping ? "Packaging…" : "ZIP"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* List */}
      {filteredEntries.length === 0 ? (
        <div className="dhp-empty">
          <span className="hud-label text-faint">
            {entries.length === 0 ? "No downloads yet." : "No matching items found."}
          </span>
        </div>
      ) : (
        <ul className="dhp-list">
          {filteredEntries.map((e) => (
            <HistoryEntryRow
              key={e.job_id}
              entry={e}
              onRemove={onRemove}
              onPause={onPause}
              onResume={onResume}
              onCancel={onCancel}
              onRetry={onRetry}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
