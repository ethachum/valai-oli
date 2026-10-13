import type { DownloadEngine } from './DownloadEngine';
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

const BASE_URL = '/api';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      ...init,
    });
  } catch (err: unknown) {
    if (err instanceof TypeError || (err instanceof Error && err.message.toLowerCase().includes('fetch'))) {
      throw new Error('Unable to connect to Valaioli backend. Please ensure the backend server is running on http://localhost:8000.');
    }
    throw err;
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = String(body.detail);
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export class DesktopDownloadEngine implements DownloadEngine {
  readonly platform = 'desktop' as const;

  async fetchMetadata(url: string): Promise<MetadataResponse> {
    return apiFetch<MetadataResponse>('/metadata', {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
  }

  async createJob(request: JobRequest): Promise<JobStatus> {
    return apiFetch<JobStatus>('/jobs', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getJob(jobId: string): Promise<JobStatus> {
    return apiFetch<JobStatus>(`/jobs/${jobId}`);
  }

  async listJobs(): Promise<JobStatus[]> {
    return apiFetch<JobStatus[]>('/jobs');
  }

  async deleteJob(jobId: string): Promise<void> {
    await fetch(`${BASE_URL}/jobs/${jobId}`, { method: 'DELETE' });
  }

  async clearJobs(): Promise<{ cleared: number }> {
    const res = await fetch(`${BASE_URL}/jobs`, { method: 'DELETE' });
    return res.json();
  }

  async cancelJob(jobId: string): Promise<JobStatus> {
    return apiFetch<JobStatus>(`/jobs/${jobId}/cancel`, { method: 'POST' });
  }

  async pauseJob(jobId: string): Promise<JobStatus> {
    return apiFetch<JobStatus>(`/jobs/${jobId}/pause`, { method: 'POST' });
  }

  async resumeJob(jobId: string): Promise<JobStatus> {
    return apiFetch<JobStatus>(`/jobs/${jobId}/resume`, { method: 'POST' });
  }

  async retryJob(jobId: string): Promise<JobStatus> {
    return apiFetch<JobStatus>(`/jobs/${jobId}/retry`, { method: 'POST' });
  }

  async syncJobs(jobs: JobStatus[]): Promise<{ restored: number }> {
    if (jobs.length === 0) return { restored: 0 };
    return apiFetch<{ restored: number }>('/jobs/sync', {
      method: 'POST',
      body: JSON.stringify(jobs),
    });
  }

  pollJob(
    jobId: string,
    onUpdate: (status: JobStatus) => void,
    onError: (err: Error) => void
  ): () => void {
    let cancelled = false;

    async function run() {
      while (!cancelled) {
        try {
          const res = await apiFetch<JobStatus>(`/jobs/${jobId}`);
          onUpdate(res);
          if (
            res.state === 'completed' ||
            res.state === 'failed' ||
            res.state === 'cancelled'
          ) return;
          await new Promise((r) => setTimeout(r, 2000));
        } catch (err) {
          onError(err instanceof Error ? err : new Error(String(err)));
          return;
        }
      }
    }

    run().catch(onError);
    return () => {
      cancelled = true;
    };
  }

  async fetchTools(): Promise<ToolsResponse> {
    return apiFetch<ToolsResponse>('/tools');
  }

  async fetchUpdaterStatus(): Promise<UpdaterStatusResponse> {
    return apiFetch<UpdaterStatusResponse>('/updater/status');
  }

  async fetchPlaylistMetadata(url: string): Promise<PlaylistMetadataResponse> {
    return apiFetch<PlaylistMetadataResponse>('/playlist/metadata', {
      method: 'POST',
      body: JSON.stringify({ url }),
    });
  }

  async createPlaylistJobs(request: PlaylistJobsRequest): Promise<PlaylistJobsResponse> {
    return apiFetch<PlaylistJobsResponse>('/playlist/jobs', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }
}
