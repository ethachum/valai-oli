import { registerPlugin } from '@capacitor/core';
import type {
  MetadataResponse,
  JobRequest,
  JobStatus,
  PlaylistMetadataResponse,
  PlaylistJobsRequest,
  PlaylistJobsResponse,
} from '../../types/api';

export interface ProgressEventPayload {
  job_id: string;
  state: string;
  progress_percent: number;
  message: string;
  speed?: string;
  eta?: string;
  file_path?: string;
}

export interface EngineInfoResponse {
  library_version: string;
  ytdlp_version: string;
  ffmpeg_version: string;
  status: string;
}

export interface ValaioliNativePlugin {
  initEngine(): Promise<{ status: string; ytdlp_version: string }>;
  fetchMetadata(options: { url: string }): Promise<MetadataResponse>;
  createJob(options: JobRequest): Promise<JobStatus>;
  getJob(options: { jobId: string }): Promise<JobStatus>;
  listJobs(): Promise<{ jobs: JobStatus[] }>;
  deleteJob(options: { jobId: string }): Promise<{ success: boolean }>;
  clearJobs(): Promise<{ cleared: number }>;
  cancelJob(options: { jobId: string }): Promise<JobStatus>;
  pauseJob(options: { jobId: string }): Promise<JobStatus>;
  resumeJob(options: { jobId: string }): Promise<JobStatus>;
  retryJob(options: { jobId: string }): Promise<JobStatus>;
  fetchPlaylistMetadata(options: { url: string }): Promise<PlaylistMetadataResponse>;
  createPlaylistJobs(options: PlaylistJobsRequest): Promise<PlaylistJobsResponse>;
  getEngineInfo(): Promise<EngineInfoResponse>;
  updateYoutubeDlp(): Promise<{ updated: boolean; version: string; message: string }>;
  checkReleaseUpdate(): Promise<{ hasUpdate: boolean; latestVersion: string; releaseUrl: string; notes: string }>;
  addListener(
    eventName: 'downloadProgress',
    listenerFunc: (event: ProgressEventPayload) => void
  ): Promise<{ remove: () => Promise<void> }>;
}

export const ValaioliNative = registerPlugin<ValaioliNativePlugin>('ValaioliNative');
