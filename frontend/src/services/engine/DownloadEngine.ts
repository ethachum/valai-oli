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

export interface DownloadEngine {
  readonly platform: 'desktop' | 'android' | 'web';
  fetchMetadata(url: string): Promise<MetadataResponse>;
  createJob(request: JobRequest): Promise<JobStatus>;
  getJob(jobId: string): Promise<JobStatus>;
  listJobs(): Promise<JobStatus[]>;
  deleteJob(jobId: string): Promise<void>;
  clearJobs(): Promise<{ cleared: number }>;
  cancelJob(jobId: string): Promise<JobStatus>;
  pauseJob(jobId: string): Promise<JobStatus>;
  resumeJob(jobId: string): Promise<JobStatus>;
  retryJob(jobId: string): Promise<JobStatus>;
  syncJobs(jobs: JobStatus[]): Promise<{ restored: number }>;
  pollJob(
    jobId: string,
    onUpdate: (status: JobStatus) => void,
    onError: (err: Error) => void
  ): () => void;
  fetchTools(): Promise<ToolsResponse>;
  fetchUpdaterStatus(): Promise<UpdaterStatusResponse>;
  fetchPlaylistMetadata(url: string): Promise<PlaylistMetadataResponse>;
  createPlaylistJobs(request: PlaylistJobsRequest): Promise<PlaylistJobsResponse>;
}
