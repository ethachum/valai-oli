import { Capacitor } from '@capacitor/core';
import type { DownloadEngine } from './DownloadEngine';
import { ValaioliNative } from '../native/ValaioliNative';
import type {
  MetadataResponse,
  JobRequest,
  JobStatus,
  ToolsResponse,
  UpdaterStatusResponse,
  PlaylistMetadataResponse,
  PlaylistJobsRequest,
  PlaylistJobsResponse,
} from '../../types/api';

export class AndroidDownloadEngine implements DownloadEngine {
  readonly platform = 'android' as const;
  private initialized = false;

  private async ensureInitialized(): Promise<void> {
    if (this.initialized) return;
    if (Capacitor.isNativePlatform()) {
      try {
        await ValaioliNative.initEngine();
        this.initialized = true;
      } catch (err) {
        console.warn('Native engine init failed:', err);
      }
    }
  }

  async fetchMetadata(url: string): Promise<MetadataResponse> {
    await this.ensureInitialized();
    return ValaioliNative.fetchMetadata({ url });
  }

  async createJob(request: JobRequest): Promise<JobStatus> {
    await this.ensureInitialized();
    return ValaioliNative.createJob(request);
  }

  async getJob(jobId: string): Promise<JobStatus> {
    return ValaioliNative.getJob({ jobId });
  }

  async listJobs(): Promise<JobStatus[]> {
    const res = await ValaioliNative.listJobs();
    return res.jobs || [];
  }

  async deleteJob(jobId: string): Promise<void> {
    await ValaioliNative.deleteJob({ jobId });
  }

  async clearJobs(): Promise<{ cleared: number }> {
    return ValaioliNative.clearJobs();
  }

  async cancelJob(jobId: string): Promise<JobStatus> {
    return ValaioliNative.cancelJob({ jobId });
  }

  async pauseJob(jobId: string): Promise<JobStatus> {
    return ValaioliNative.pauseJob({ jobId });
  }

  async resumeJob(jobId: string): Promise<JobStatus> {
    return ValaioliNative.resumeJob({ jobId });
  }

  async retryJob(jobId: string): Promise<JobStatus> {
    return ValaioliNative.retryJob({ jobId });
  }

  async syncJobs(jobs: JobStatus[]): Promise<{ restored: number }> {
    return { restored: jobs.length };
  }

  pollJob(
    jobId: string,
    onUpdate: (status: JobStatus) => void,
    onError: (err: Error) => void
  ): () => void {
    let cancelled = false;
    let listenerPromise: Promise<{ remove: () => Promise<void> }> | null = null;

    if (Capacitor.isNativePlatform()) {
      listenerPromise = ValaioliNative.addListener('downloadProgress', (event) => {
        if (cancelled || event.job_id !== jobId) return;
        const jobStatus: JobStatus = {
          job_id: event.job_id,
          state: event.state as any,
          progress_percent: event.progress_percent,
          message: event.message,
          created_at: new Date().toISOString(),
          completed_at: event.state === 'completed' ? new Date().toISOString() : null,
          error: event.state === 'failed' ? event.message : null,
        };
        onUpdate(jobStatus);
      });
    }

    // Also run poll fallback to ensure status transitions are never missed
    async function runPolling() {
      while (!cancelled) {
        try {
          const res = await ValaioliNative.getJob({ jobId });
          if (cancelled) return;
          onUpdate(res);
          if (
            res.state === 'completed' ||
            res.state === 'failed' ||
            res.state === 'cancelled'
          ) {
            return;
          }
          await new Promise((r) => setTimeout(r, 1500));
        } catch (err) {
          if (!cancelled) {
            onError(err instanceof Error ? err : new Error(String(err)));
          }
          return;
        }
      }
    }

    runPolling().catch(onError);

    return () => {
      cancelled = true;
      if (listenerPromise) {
        listenerPromise.then((handle) => handle.remove()).catch(() => {});
      }
    };
  }

  async fetchTools(): Promise<ToolsResponse> {
    try {
      const info = await ValaioliNative.getEngineInfo();
      return {
        tools: [
          {
            name: 'yt-dlp (on-device Android)',
            active_version: info.ytdlp_version || 'Embedded',
            last_check_utc: new Date().toISOString(),
            last_outcome: 'ready',
          },
          {
            name: 'ffmpeg (Android kit)',
            active_version: info.ffmpeg_version || 'Embedded',
            last_check_utc: new Date().toISOString(),
            last_outcome: 'ready',
          },
        ],
      };
    } catch {
      return {
        tools: [
          {
            name: 'yt-dlp (on-device Android)',
            active_version: 'Embedded',
            last_check_utc: new Date().toISOString(),
            last_outcome: 'ready',
          },
          {
            name: 'ffmpeg (Android kit)',
            active_version: 'Embedded',
            last_check_utc: new Date().toISOString(),
            last_outcome: 'ready',
          },
        ],
      };
    }
  }

  async fetchUpdaterStatus(): Promise<UpdaterStatusResponse> {
    try {
      const info = await ValaioliNative.getEngineInfo();
      const updateCheck = await ValaioliNative.checkReleaseUpdate();
      return {
        tools: [
          {
            name: 'yt-dlp',
            active_version: info.ytdlp_version,
            last_check_utc: new Date().toISOString(),
            last_outcome: 'up-to-date',
            candidate: null,
          },
          {
            name: 'ffmpeg',
            active_version: info.ffmpeg_version,
            last_check_utc: new Date().toISOString(),
            last_outcome: 'up-to-date',
            candidate: null,
          },
        ],
        update_available: updateCheck.hasUpdate,
      };
    } catch {
      return {
        tools: [
          {
            name: 'yt-dlp',
            active_version: 'Dynamic verified',
            last_check_utc: new Date().toISOString(),
            last_outcome: 'up-to-date',
            candidate: null,
          },
        ],
        update_available: false,
      };
    }
  }

  async fetchPlaylistMetadata(url: string): Promise<PlaylistMetadataResponse> {
    await this.ensureInitialized();
    return ValaioliNative.fetchPlaylistMetadata({ url });
  }

  async createPlaylistJobs(request: PlaylistJobsRequest): Promise<PlaylistJobsResponse> {
    await this.ensureInitialized();
    return ValaioliNative.createPlaylistJobs(request);
  }
}
