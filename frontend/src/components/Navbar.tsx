import { useCallback, useEffect, useRef, useState } from "react";
import { fetchTools } from "../services/api";
import { ToolsPanel } from "./ToolsPanel";
import { DownloadHistoryPanel } from "./DownloadHistoryPanel";
import { useDownloadHistory } from "../hooks/useDownloadHistory";
import type { ToolInfo } from "../types/api";
import "./Navbar.css";

// -- Valaioli wordmark icon --------------------------------------------------
function VIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect width="20" height="20" fill="var(--accent)" />
      <path d="M5 5L10 15L15 5" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

interface NavbarProps {
  onReset?: () => void;
}

type ToolStatus = "loading" | "ready" | "not-installed";

function useToolStatus(): ToolStatus {
  const [status, setStatus] = useState<ToolStatus>("loading");

  useEffect(() => {
    fetchTools()
      .then((resp) => {
        const allReady = resp.tools.every((t: ToolInfo) => t.active_version !== null);
        setStatus(allReady ? "ready" : "not-installed");
      })
      .catch(() => setStatus("not-installed"));
  }, []);

  return status;
}

export function Navbar({ onReset }: NavbarProps) {
  const toolStatus = useToolStatus();
  const [toolsPanelOpen, setToolsPanelOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  const toolsBadgeRef = useRef<HTMLButtonElement>(null);
  const historyBtnRef = useRef<HTMLButtonElement>(null);

  const handleToolsClose = useCallback(() => setToolsPanelOpen(false), []);
  const handleHistoryClose = useCallback(() => setHistoryOpen(false), []);

  // History data
  const {
    entries,
    activeCount,
    hasFinished,
    pauseEntry,
    resumeEntry,
    cancelEntry,
    retryEntry,
    removeEntry,
    clearFinished,
  } = useDownloadHistory();

  const hasActive = activeCount > 0;

  return (
    <nav id="site-nav" className="navbar" aria-label="Main navigation">
      <div className="navbar__inner">
        {/* Left - brand */}
        <div className="navbar__brand">
          <button
            className="navbar__logo-btn"
            onClick={onReset}
            aria-label="Valai-oli - return to home"
            title="Valai-oli home"
          >
            <VIcon />
            <span className="navbar__wordmark hud-label">Valai-oli</span>
          </button>
        </div>

        {/* Right - meta */}
        <div className="navbar__right" style={{ position: "relative" }}>
          <span className="navbar__tag hud-label text-faint">YouTube Downloader</span>

          {/* Download history button */}
          <button
            ref={historyBtnRef}
            id="download-history-btn"
            type="button"
            className={`navbar__history-btn${hasActive ? " navbar__history-btn--active" : ""}`}
            onClick={() => {
              setHistoryOpen((v) => !v);
              setToolsPanelOpen(false);
            }}
            aria-expanded={historyOpen}
            aria-controls="download-history-panel"
            title={
              hasActive
                ? `${activeCount} active download${activeCount !== 1 ? "s" : ""}`
                : "Download history"
            }
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            {activeCount > 0 && (
              <span className="navbar__history-badge" aria-label={`${activeCount} active`}>
                {activeCount}
              </span>
            )}
          </button>

          {historyOpen && (
            <DownloadHistoryPanel
              entries={entries}
              hasFinished={hasFinished}
              anchorRef={historyBtnRef}
              onClose={handleHistoryClose}
              onRemove={removeEntry}
              onPause={pauseEntry}
              onResume={resumeEntry}
              onCancel={cancelEntry}
              onRetry={retryEntry}
              onClearFinished={clearFinished}
            />
          )}

          {/* Tool status badge */}
          {toolStatus === "loading" && (
            <span className="navbar__mock-badge hud-label badge text-faint" title="Checking tool status...">
              Checking...
            </span>
          )}

          {toolStatus === "ready" && (
            <button
              ref={toolsBadgeRef}
              id="tools-badge-btn"
              type="button"
              className="navbar__mock-badge navbar__mock-badge--btn hud-label badge badge-accent"
              title="Click to see tool status and updates"
              aria-expanded={toolsPanelOpen}
              aria-controls="tools-panel"
              onClick={() => {
                setToolsPanelOpen((v) => !v);
                setHistoryOpen(false);
              }}
            >
              * Tools ready
            </button>
          )}

          {toolStatus === "not-installed" && (
            <button
              ref={toolsBadgeRef}
              id="tools-badge-btn"
              type="button"
              className="navbar__mock-badge navbar__mock-badge--btn hud-label badge"
              style={{ borderColor: "hsl(35 90% 55% / 0.5)", color: "hsl(35 90% 65%)" }}
              title="Click to see tool status"
              aria-expanded={toolsPanelOpen}
              aria-controls="tools-panel"
              onClick={() => {
                setToolsPanelOpen((v) => !v);
                setHistoryOpen(false);
              }}
            >
              ! Tools not installed
            </button>
          )}

          {toolsPanelOpen && (
            <ToolsPanel anchorRef={toolsBadgeRef} onClose={handleToolsClose} />
          )}
        </div>
      </div>
    </nav>
  );
}
