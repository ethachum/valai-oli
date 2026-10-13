/**
 * ToolsPanel � Popover accessible from the Navbar "Tools" badge.
 *
 * Fetches /api/updater/status on open and renders per-tool rows
 * showing the active version, last-check time, and any pending
 * update candidate.  A "Run verify" button calls /api/updater/verify.
 */
import React, { useEffect, useRef, useState } from 'react';
import { fetchUpdaterStatus } from '../services/api';
import type { UpdaterStatusResponse, ToolUpdateStatus } from '../types/api';
import './ToolsPanel.css';

// -- helpers ------------------------------------------------------------------

function fmtDate(iso: string | null): string {
  if (!iso) return '�';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function outcomeLabel(outcome: string | null): { text: string; cls: string } {
  switch (outcome) {
    case 'update-available': return { text: 'Update available', cls: 'outcome--update' };
    case 'up-to-date':       return { text: 'Up to date',       cls: 'outcome--ok'     };
    case 'not-checked':      return { text: 'Not checked',      cls: 'outcome--neutral' };
    default:                  return { text: outcome ?? '�',     cls: 'outcome--neutral' };
  }
}

// -- icons ---------------------------------------------------------------------

function ToolIcon({ name }: { name: string }) {
  if (name.toLowerCase().includes('ffmpeg')) {
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M2 12h20M12 2v20M4.9 4.9l14.2 14.2M19.1 4.9 4.9 19.1"/>
      </svg>
    );
  }
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  );
}

function RefreshSmIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
      <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
    </svg>
  );
}

function CheckSmIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  );
}

function AlertSmIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  );
}

function ExternalIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
    </svg>
  );
}

// -- ToolRow -------------------------------------------------------------------

function ToolRow({ tool }: { tool: ToolUpdateStatus }) {
  const { text: outcomeText, cls: outcomeCls } = outcomeLabel(tool.last_outcome);
  const hasUpdate = tool.last_outcome === 'update-available' && tool.candidate;

  return (
    <div className={`tools-row ${hasUpdate ? 'tools-row--update' : ''}`}>
      <div className="tools-row__header">
        <span className="tools-row__icon" aria-hidden="true">
          <ToolIcon name={tool.name} />
        </span>
        <span className="tools-row__name hud-label">{tool.name}</span>
        {tool.active_version ? (
          <code className="tools-row__version">{tool.active_version}</code>
        ) : (
          <span className="tools-row__version tools-row__version--missing hud-label">not installed</span>
        )}
        <span className={`tools-row__outcome ${outcomeCls}`}>
          {hasUpdate ? <AlertSmIcon /> : tool.active_version ? <CheckSmIcon /> : null}
          {outcomeText}
        </span>
      </div>

      {hasUpdate && tool.candidate && (
        <div className="tools-row__candidate">
          <span className="hud-label text-faint">Candidate</span>
          <code className="tools-row__candidate-ver">{tool.candidate.version}</code>
          {tool.candidate.release_url && (
            <a
              href={tool.candidate.release_url}
              target="_blank"
              rel="noopener noreferrer"
              className="tools-row__release-link hud-label"
              aria-label={`Release notes for ${tool.name} ${tool.candidate.version}`}
            >
              Release notes
              <ExternalIcon />
            </a>
          )}
        </div>
      )}

      <div className="tools-row__meta">
        <span className="hud-label text-faint">
          Last checked: {fmtDate(tool.last_check_utc)}
        </span>
      </div>
    </div>
  );
}

// -- VerifyButton --------------------------------------------------------------

type VerifyState = 'idle' | 'running' | 'passed' | 'failed';

function VerifyButton() {
  const [state, setState] = useState<VerifyState>('idle');
  const [output, setOutput] = useState<string>('');

  async function runVerify() {
    setState('running');
    setOutput('');
    try {
      const res = await fetch('/api/updater/verify', { method: 'POST' });
      const data: { passed: boolean; output: string } = await res.json();
      setOutput(data.output);
      setState(data.passed ? 'passed' : 'failed');
    } catch (err) {
      setOutput(String(err));
      setState('failed');
    }
  }

  return (
    <div className="verify-section">
      <button
        id="run-verify-btn"
        type="button"
        className={`verify-btn${state === 'running' ? ' verify-btn--running' : ''}`}
        onClick={runVerify}
        disabled={state === 'running'}
        aria-label="Run tool verification"
      >
        {state === 'running' ? (
          <><span className="format-spinner" aria-hidden="true" /> Verifying...</>
        ) : state === 'passed' ? (
          <><CheckSmIcon /> Verify passed</>
        ) : state === 'failed' && output ? (
          <><AlertSmIcon /> Verify failed</>
        ) : (
          <><RefreshSmIcon /> Run verify</>
        )}
      </button>
      {output && (
        <pre className="verify-output" aria-live="polite">{output}</pre>
      )}
    </div>
  );
}

// -- ToolsPanel (main export) --------------------------------------------------

interface ToolsPanelProps {
  /** The anchor element this popover is attached to */
  anchorRef: React.RefObject<HTMLElement | null>;
  onClose: () => void;
}

export function ToolsPanel({ anchorRef, onClose }: ToolsPanelProps) {
  const [data, setData] = useState<UpdaterStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Fetch on mount
  useEffect(() => {
    fetchUpdaterStatus()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Close on outside click
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
    const id = setTimeout(() => document.addEventListener('mousedown', handleClick), 50);
    return () => {
      clearTimeout(id);
      document.removeEventListener('mousedown', handleClick);
    };
  }, [anchorRef, onClose]);

  // Close on Escape
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <div
      ref={panelRef}
      className="tools-panel animate-fade-up"
      role="dialog"
      aria-label="Tools status panel"
      aria-modal="false"
      id="tools-panel"
    >
      {/* Header */}
      <div className="tools-panel__header">
        <span className="tools-panel__title hud-label">Tools &amp; Updates</span>
        <button
          type="button"
          className="tools-panel__close"
          onClick={onClose}
          aria-label="Close tools panel"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      {/* Body */}
      <div className="tools-panel__body">
        {loading && (
          <div className="tools-panel__loading">
            <span className="format-spinner" aria-hidden="true" />
            <span className="hud-label text-faint">Loading...</span>
          </div>
        )}

        {error && (
          <div className="tools-panel__error">
            <AlertSmIcon />
            <span className="body-sm">{error}</span>
          </div>
        )}

        {data && (
          <>
            <div className="tools-panel__rows">
              {data.tools.map((tool) => (
                <ToolRow key={tool.name} tool={tool} />
              ))}
            </div>

            <div className="tools-panel__divider" />

            <VerifyButton />

            <p className="tools-panel__hint hud-label text-faint">
              To apply updates, run <code>install-candidate.ps1</code> from the scripts directory.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
