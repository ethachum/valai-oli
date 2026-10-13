/**
 * useDownloadHistory — Hybrid download history:
 *
 * - Active (queued/downloading/merging/converting/validating/paused) jobs are
 *   always fetched live from GET /api/jobs.
 * - Completed/failed/cancelled jobs are mirrored into localStorage so they
 *   survive backend restarts.
 * - The merged list is sorted newest-first and deduped by job_id.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { JobStatus, JobState } from "../types/api";
import {
  listJobs,
  syncJobs,
  deleteJob as apiDeleteJob,
  clearJobs as apiClearJobs,
  pauseJob as apiPauseJob,
  resumeJob as apiResumeJob,
  cancelJob as apiCancelJob,
  createJob as apiCreateJob,
  retryJob as apiRetryJob,
} from "../services/api";

// -- localStorage helpers ------------------------------------------------------

const LS_KEY = "valaioli:history:v1";
const LS_PLAYLIST_TITLE_KEY = "valaioli:playlist_titles:v1";
const TERMINAL_STATES: JobState[] = ["completed", "failed", "cancelled"];

function loadHistory(): JobStatus[] {
  try {
    const raw = localStorage.getItem(LS_KEY);
    return raw ? (JSON.parse(raw) as JobStatus[]) : [];
  } catch {
    return [];
  }
}

function saveHistory(jobs: JobStatus[]) {
  try {
    const terminal = jobs
      .filter((j) => TERMINAL_STATES.includes(j.state))
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, 200);
    localStorage.setItem(LS_KEY, JSON.stringify(terminal));
  } catch { /* quota exceeded */ }
}

/** Load the job_id -> playlist_title map from localStorage. */
function loadPlaylistTitles(): Record<string, string> {
  try {
    const raw = localStorage.getItem(LS_PLAYLIST_TITLE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, string>) : {};
  } catch {
    return {};
  }
}

/** Persist the job_id -> playlist_title map (cap at 500 entries). */
function savePlaylistTitles(map: Record<string, string>) {
  try {
    const entries = Object.entries(map);
    const trimmed = Object.fromEntries(entries.slice(-500));
    localStorage.setItem(LS_PLAYLIST_TITLE_KEY, JSON.stringify(trimmed));
  } catch { /* quota exceeded */ }
}

/** Store playlist_title for a list of job IDs so history entries carry it. */
export function registerPlaylistJobTitles(jobIds: string[], playlistTitle: string) {
  const existing = loadPlaylistTitles();
  for (const id of jobIds) existing[id] = playlistTitle;
  savePlaylistTitles(existing);
}

// -- Hook ----------------------------------------------------------------------

export interface HistoryEntry extends JobStatus {
  _source: "live" | "local";
}

export function useDownloadHistory() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const syncedRef = useRef<boolean>(false);
  const removedIdsRef = useRef<Set<string>>(new Set());

  const sync = useCallback(async () => {
    let liveJobs: JobStatus[] = [];
    try {
      liveJobs = await listJobs();
    } catch { /* backend unreachable */ }

    // Filter out jobs that were removed or retried
    if (removedIdsRef.current.size > 0) {
      liveJobs = liveJobs.filter((j) => !removedIdsRef.current.has(j.job_id));
    }

    const localHistory = loadHistory().filter(
      (j) => !removedIdsRef.current.has(j.job_id),
    );

    // Sync localStorage jobs missing from backend memory
    if (localHistory.length > 0 && !syncedRef.current) {
      const liveIds = new Set(liveJobs.map((j) => j.job_id));
      const missingInLive = localHistory.filter((j) => !liveIds.has(j.job_id));
      if (missingInLive.length > 0) {
        syncedRef.current = true;
        syncJobs(missingInLive).catch(() => { syncedRef.current = false; });
      }
    }

    const playlistTitles = loadPlaylistTitles();
    const map = new Map<string, HistoryEntry>();

    for (const j of localHistory) {
      const pt = j.playlist_title || playlistTitles[j.job_id] || null;
      map.set(j.job_id, { ...j, playlist_title: pt, _source: "local" });
    }
    for (const j of liveJobs) {
      const pt = j.playlist_title || playlistTitles[j.job_id] || null;
      map.set(j.job_id, { ...j, playlist_title: pt, _source: "live" });
    }

    const merged = Array.from(map.values()).sort(
      (a, b) => b.created_at.localeCompare(a.created_at),
    );

    const newTerminal = liveJobs.filter((j) => TERMINAL_STATES.includes(j.state));
    if (newTerminal.length > 0) {
      const existing = loadHistory().filter(
        (j) => !removedIdsRef.current.has(j.job_id),
      );
      const existingIds = new Set(existing.map((j) => j.job_id));
      const toAdd = newTerminal
        .filter((j) => !existingIds.has(j.job_id) && !removedIdsRef.current.has(j.job_id))
        .map((j) => ({ ...j, playlist_title: playlistTitles[j.job_id] || j.playlist_title || null }));
      if (toAdd.length > 0) saveHistory([...toAdd, ...existing]);
    }

    setEntries(merged);
  }, []);

  useEffect(() => {
    sync();
    pollRef.current = setInterval(sync, 2500);
    return () => { if (pollRef.current !== null) clearInterval(pollRef.current); };
  }, [sync]);

  const activeCount = entries.filter((e) => !TERMINAL_STATES.includes(e.state)).length;
  const hasFinished = entries.some((e) => TERMINAL_STATES.includes(e.state));

  const pauseEntry = useCallback(async (jobId: string) => {
    try {
      await apiPauseJob(jobId);
      await sync();
    } catch { /* best-effort */ }
  }, [sync]);

  const resumeEntry = useCallback(async (jobId: string) => {
    try {
      await apiResumeJob(jobId);
      await sync();
    } catch { /* best-effort */ }
  }, [sync]);

  const cancelEntry = useCallback(async (jobId: string) => {
    try {
      await apiCancelJob(jobId);
      await sync();
    } catch { /* best-effort */ }
  }, [sync]);

  const retryEntry = useCallback(
    async (entry: HistoryEntry) => {
      // 1. Mark as removed so sync/polling never revives it
      removedIdsRef.current.add(entry.job_id);

      // 2. Immediately remove the failed entry from UI state and localStorage
      setEntries((prev) => prev.filter((e) => e.job_id !== entry.job_id));
      saveHistory(loadHistory().filter((j) => j.job_id !== entry.job_id));

      try {
        let newJob: JobStatus | null = null;
        if (entry.url && entry.format_id) {
          // Delete old failed job from backend so listJobs() won't include it
          await apiDeleteJob(entry.job_id).catch(() => {});
          newJob = await apiCreateJob({
            url: entry.url,
            format_id: entry.format_id,
            output_format: entry.output_format ?? undefined,
            title: entry.title,
            thumbnail: entry.thumbnail,
          });
        } else {
          // apiRetryJob already deletes old job on backend
          newJob = await apiRetryJob(entry.job_id);
        }

        const playlistTitle = entry.playlist_title || loadPlaylistTitles()[entry.job_id];
        if (newJob?.job_id && playlistTitle) {
          registerPlaylistJobTitles([newJob.job_id], playlistTitle);
        }

        await sync();
      } catch {
        await sync();
      }
    },
    [sync],
  );

  const removeEntry = useCallback(async (jobId: string) => {
    removedIdsRef.current.add(jobId);
    setEntries((prev) => prev.filter((e) => e.job_id !== jobId));
    saveHistory(loadHistory().filter((j) => j.job_id !== jobId));
    try { await apiDeleteJob(jobId); } catch { /* best-effort */ }
  }, []);

  const clearFinished = useCallback(async () => {
    for (const e of entries) {
      if (TERMINAL_STATES.includes(e.state)) {
        removedIdsRef.current.add(e.job_id);
      }
    }
    setEntries((prev) => prev.filter((e) => !TERMINAL_STATES.includes(e.state)));
    saveHistory([]);
    try { await apiClearJobs(); } catch { /* best-effort */ }
  }, [entries]);

  return {
    entries,
    activeCount,
    hasFinished,
    sync,
    pauseEntry,
    resumeEntry,
    cancelEntry,
    retryEntry,
    removeEntry,
    clearFinished,
  };
}

