import { useState, useCallback, useEffect, useRef } from 'react';
import type { AppPhase, FormatInfo, PlaylistItem } from '../types/api';
import {
  fetchMetadata,
  createJob,
  pollJob,
  cancelJob,
  pauseJob,
  resumeJob,
  isPlaylistUrl,
  fetchPlaylistMetadata,
  createPlaylistJobs,
} from '../services/api';
import { registerPlaylistJobTitles } from './useDownloadHistory';

// ── Main download state machine hook ─────────────────────────────────────

export function useDownload() {
  const [phase, setPhase] = useState<AppPhase>({ kind: 'idle' });
  const cancelPollRef = useRef<(() => void) | null>(null);

  // Clean up polling when unmounting
  useEffect(() => {
    return () => { cancelPollRef.current?.(); };
  }, []);

  // ── Actions ─────────────────────────────────────────────────────────────

  const submitUrl = useCallback(async (url: string) => {
    setPhase({ kind: 'loading-metadata', url });
    try {
      if (isPlaylistUrl(url)) {
        const playlist = await fetchPlaylistMetadata(url);
        setPhase({ kind: 'playlist-select', url, playlist });
      } else {
        const metadata = await fetchMetadata(url);
        setPhase({ kind: 'select-format', url, metadata });
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Failed to fetch media information.';
      const isConnectionIssue =
        errMsg.toLowerCase().includes('connect') ||
        errMsg.toLowerCase().includes('unreachable') ||
        errMsg.toLowerCase().includes('failed to fetch');
      setPhase({
        kind: 'error',
        message: errMsg,
        detail: isConnectionIssue
          ? 'Make sure the FastAPI backend is running (uvicorn app.main:app --port 8000).'
          : 'Check that the URL is a public YouTube video or playlist and try again.',
      });
    }
  }, []);

  const selectFormat = useCallback(
    async (format: FormatInfo, startTime?: string, endTime?: string, isGif?: boolean) => {
      if (phase.kind !== 'select-format') return;
      const { url, metadata } = phase;

      try {
        const job = await createJob({
          url,
          format_id: format.format_id,
          output_format: isGif ? 'gif' : format.ext,
          title: metadata.title,
          thumbnail: metadata.thumbnail ?? undefined,
          start_time: startTime ?? null,
          end_time: endTime ?? null,
          channel: metadata.uploader ?? null,
          is_gif: isGif ?? false,
        });

        setPhase({ kind: 'processing', url, metadata, format, job });

        // Stop any previous poll
        cancelPollRef.current?.();

        cancelPollRef.current = pollJob(
          job.job_id,
          (updated) => {
            setPhase((prev) => {
              if (prev.kind !== 'processing' && prev.kind !== 'completed') return prev;
              if (updated.state === 'completed') {
                return { kind: 'completed', metadata, format, job: updated };
              }
              if (updated.state === 'failed') {
                return {
                  kind: 'error',
                  message: updated.error ?? 'Download failed.',
                  detail: 'Check the URL and format, then try again.',
                };
              }
              if (updated.state === 'cancelled') {
                return { kind: 'idle' };
              }
              return { kind: 'processing', url, metadata, format, job: updated };
            });
          },
          (err) => {
            setPhase({
              kind: 'error',
              message: err.message,
              detail: 'Connection to the server was lost.',
            });
          },
        );
      } catch (err) {
        setPhase({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Failed to start download.',
        });
      }
    },
    [phase],
  );

  const requestCancel = useCallback(async () => {
    if (phase.kind !== 'processing') return;
    cancelPollRef.current?.();
    cancelPollRef.current = null;
    try {
      await cancelJob(phase.job.job_id);
    } catch { /* ignore — UI resets regardless */ }
    setPhase({ kind: 'idle' });
  }, [phase]);

  const requestPause = useCallback(async () => {
    if (phase.kind !== 'processing') return;
    try {
      const updated = await pauseJob(phase.job.job_id);
      setPhase((prev) =>
        prev.kind === 'processing' ? { ...prev, job: updated } : prev
      );
    } catch {
      setPhase((prev) =>
        prev.kind === 'processing'
          ? { ...prev, job: { ...prev.job, state: 'paused', message: 'Download paused.' } }
          : prev
      );
    }
  }, [phase]);

  const requestResume = useCallback(async () => {
    if (phase.kind !== 'processing') return;
    try {
      const updated = await resumeJob(phase.job.job_id);
      setPhase((prev) =>
        prev.kind === 'processing' ? { ...prev, job: updated } : prev
      );
    } catch {
      setPhase((prev) =>
        prev.kind === 'processing'
          ? { ...prev, job: { ...prev.job, state: 'downloading', message: 'Resuming download…' } }
          : prev
      );
    }
  }, [phase]);

  const reset = useCallback(() => {
    cancelPollRef.current?.();
    cancelPollRef.current = null;
    setPhase({ kind: 'idle' });
  }, []);

  const backToFormats = useCallback(() => {
    if (phase.kind !== 'processing' && phase.kind !== 'error') return;
    cancelPollRef.current?.();
    cancelPollRef.current = null;
    if (phase.kind === 'processing') {
      setPhase({ kind: 'select-format', url: phase.url, metadata: phase.metadata });
    } else {
      setPhase({ kind: 'idle' });
    }
  }, [phase]);

  const startPlaylistDownload = useCallback(
    async (items: PlaylistItem[], preset: string) => {
      if (phase.kind !== 'playlist-select') return;
      const { playlist } = phase;

      try {
        const payload = items.map((it) => ({
          index: it.index,
          title: it.title,
          url: it.url,
          thumbnail: it.thumbnail,
        }));

        const res = await createPlaylistJobs({
          items: payload,
          preset,
          playlist_title: playlist.title,
        });

        // Persist playlist title per job_id so history panel can name the ZIP
        registerPlaylistJobTitles(res.job_ids, playlist.title);

        try {
          sessionStorage.setItem('valaioli:last_playlist_title', playlist.title);
        } catch { /* ignore */ }

        setPhase({
          kind: 'playlist-queued',
          playlistTitle: playlist.title,
          enqueuedCount: res.enqueued_count,
          jobIds: res.job_ids,
        });
      } catch (err) {
        setPhase({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Failed to enqueue playlist downloads.',
          detail: 'Check network connectivity or backend status.',
        });
      }
    },
    [phase],
  );

  return {
    phase,
    submitUrl,
    selectFormat,
    startPlaylistDownload,
    requestCancel,
    requestPause,
    requestResume,
    reset,
    backToFormats,
  };
}

