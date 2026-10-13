// ── Valaioli API service layer (Platform-Independent Facade) ────────────────
//
// Delegates to DesktopDownloadEngine or AndroidDownloadEngine based on runtime.

import type {
  MetadataResponse,
  JobRequest,
  JobStatus,
  ToolsResponse,
  UpdaterStatusResponse,
  PlaylistMetadataResponse,
  PlaylistJobsRequest,
  PlaylistJobsResponse,
} from '../types/api';
import { getDownloadEngine } from './engine/getEngine';

export function isPlaylistUrl(url: string): boolean {
  try {
    const trimmed = url.trim();
    if (!trimmed.includes('youtube.com') && !trimmed.includes('youtu.be')) return false;
    const parsed = new URL(trimmed);
    return Boolean(parsed.searchParams.get('list'));
  } catch {
    return false;
  }
}

export async function fetchMetadata(url: string): Promise<MetadataResponse> {
  return getDownloadEngine().fetchMetadata(url);
}

export async function createJob(request: JobRequest): Promise<JobStatus> {
  return getDownloadEngine().createJob(request);
}

export async function getJob(jobId: string): Promise<JobStatus> {
  return getDownloadEngine().getJob(jobId);
}

export async function listJobs(): Promise<JobStatus[]> {
  return getDownloadEngine().listJobs();
}

export async function deleteJob(jobId: string): Promise<void> {
  return getDownloadEngine().deleteJob(jobId);
}

export async function clearJobs(): Promise<{ cleared: number }> {
  return getDownloadEngine().clearJobs();
}

export async function cancelJob(jobId: string): Promise<JobStatus> {
  return getDownloadEngine().cancelJob(jobId);
}

export async function pauseJob(jobId: string): Promise<JobStatus> {
  return getDownloadEngine().pauseJob(jobId);
}

export async function resumeJob(jobId: string): Promise<JobStatus> {
  return getDownloadEngine().resumeJob(jobId);
}

export async function retryJob(jobId: string): Promise<JobStatus> {
  return getDownloadEngine().retryJob(jobId);
}

export async function syncJobs(jobs: JobStatus[]): Promise<{ restored: number }> {
  return getDownloadEngine().syncJobs(jobs);
}

export function pollJob(
  jobId: string,
  onUpdate: (status: JobStatus) => void,
  onError: (err: Error) => void
): () => void {
  return getDownloadEngine().pollJob(jobId, onUpdate, onError);
}

export async function fetchTools(): Promise<ToolsResponse> {
  return getDownloadEngine().fetchTools();
}

export async function fetchUpdaterStatus(): Promise<UpdaterStatusResponse> {
  return getDownloadEngine().fetchUpdaterStatus();
}

export async function fetchPlaylistMetadata(url: string): Promise<PlaylistMetadataResponse> {
  return getDownloadEngine().fetchPlaylistMetadata(url);
}

export async function createPlaylistJobs(request: PlaylistJobsRequest): Promise<PlaylistJobsResponse> {
  return getDownloadEngine().createPlaylistJobs(request);
}
