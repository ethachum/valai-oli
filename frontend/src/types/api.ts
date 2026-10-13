// ── API response types — mirror backend Pydantic schemas ──────────────────

export interface HealthResponse {
  status: string;
  version: string;
}

export interface ToolInfo {
  name: string;
  active_version: string | null;
  last_check_utc: string | null;
  last_outcome: string | null;
}

export interface ToolsResponse {
  tools: ToolInfo[];
}

// ── Updater status types — mirror backend updater schemas ─────────────────

export interface CandidateInfo {
  version: string | null;
  status: string | null;
  release_url: string | null;
  checked_at_utc: string | null;
}

export interface ToolUpdateStatus {
  name: string;
  active_version: string | null;
  last_check_utc: string | null;
  last_outcome: string | null;
  candidate: CandidateInfo | null;
}

export interface UpdaterStatusResponse {
  tools: ToolUpdateStatus[];
  update_available: boolean;
}

export interface FormatInfo {
  format_id: string;
  ext: string;
  resolution: string | null;
  vcodec: string | null;
  acodec: string | null;
  filesize_approx: number | null;
  has_video: boolean;
  has_audio: boolean;
  note: string | null;
}

export interface MetadataResponse {
  title: string;
  thumbnail: string | null;
  duration_seconds: number | null;
  uploader: string | null;
  formats: FormatInfo[];
}

export type JobState =
  | 'queued'
  | 'downloading'
  | 'merging'
  | 'converting'
  | 'validating'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'paused';

export interface JobStatus {
  job_id: string;
  state: JobState;
  progress_percent: number | null;
  message: string | null;
  created_at: string;
  completed_at: string | null;
  error: string | null;
  title?: string | null;
  thumbnail?: string | null;
  url?: string | null;
  format_id?: string | null;
  output_format?: string | null;
  playlist_title?: string | null;
  channel?: string | null;
  is_gif?: boolean | null;
  waveform_path?: string | null;
}

export interface JobRequest {
  url: string;
  format_id: string;
  output_format?: string;
  title?: string | null;
  thumbnail?: string | null;
  start_time?: string | null;  // e.g. "0:30" clip start
  end_time?: string | null;    // e.g. "1:45" clip end
  channel?: string | null;
  is_gif?: boolean;
}

export interface PlaylistItem {
  index: number;
  video_id: string;
  title: string;
  thumbnail: string | null;
  duration_seconds: number | null;
  url: string;
}

export interface PlaylistMetadataResponse {
  playlist_id: string;
  title: string;
  uploader: string | null;
  entry_count: number;
  entries: PlaylistItem[];
}

export interface PlaylistEnqueueItem {
  index: number;
  title: string;
  url: string;
  thumbnail: string | null;
}

export interface PlaylistJobsRequest {
  items: PlaylistEnqueueItem[];
  preset?: string;
  format_id?: string;
  output_format?: string;
  playlist_title?: string | null;
}

export interface PlaylistJobsResponse {
  enqueued_count: number;
  job_ids: string[];
}

// ── App-level state machine ───────────────────────────────────────────────

export type AppPhase =
  | { kind: 'idle' }
  | { kind: 'loading-metadata'; url: string }
  | { kind: 'select-format'; url: string; metadata: MetadataResponse }
  | { kind: 'playlist-select'; url: string; playlist: PlaylistMetadataResponse }
  | {
      kind: 'playlist-queued';
      playlistTitle: string;
      enqueuedCount: number;
      jobIds: string[];
    }
  | {
      kind: 'processing';
      url: string;
      metadata: MetadataResponse;
      format: FormatInfo;
      job: JobStatus;
    }
  | {
      kind: 'completed';
      metadata: MetadataResponse;
      format: FormatInfo;
      job: JobStatus;
    }
  | { kind: 'error'; message: string; detail?: string };


