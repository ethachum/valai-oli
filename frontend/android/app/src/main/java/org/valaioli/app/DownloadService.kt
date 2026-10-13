package org.valaioli.app

import android.app.*
import android.content.*
import android.os.*
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import com.yausername.youtubedl_android.YoutubeDLResponse
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.util.*
import java.util.concurrent.*
import java.util.concurrent.atomic.AtomicBoolean

/**
 * DownloadService
 *
 * Android foreground service that manages all yt-dlp download jobs.
 * Runs persistently in the foreground with a persistent notification
 * so Android does not terminate active downloads.
 *
 * Max concurrency: 2 simultaneous downloads (configurable via CONCURRENCY_LIMIT).
 *
 * Storage: Android MediaStore / Downloads directory for completed files.
 */
class DownloadService : Service() {

    companion object {
        private const val TAG = "ValaioliDownload"
        private const val NOTIFICATION_CHANNEL_ID = "valaioli_downloads"
        private const val NOTIFICATION_ID = 1001
        private const val CONCURRENCY_LIMIT = 2

        // These extras are used by notification action intents
        const val ACTION_CANCEL_JOB = "org.valaioli.app.ACTION_CANCEL_JOB"
        const val EXTRA_JOB_ID = "jobId"
    }

    // ── Binder ────────────────────────────────────────────────────────────

    inner class LocalBinder : Binder() {
        fun getService(): DownloadService = this@DownloadService
    }

    private val binder = LocalBinder()

    override fun onBind(intent: Intent?): IBinder = binder

    // ── Job state ─────────────────────────────────────────────────────────

    private val jobs = ConcurrentHashMap<String, ValaioliJob>()
    private val cancellationFlags = ConcurrentHashMap<String, AtomicBoolean>()
    private val executor = Executors.newFixedThreadPool(CONCURRENCY_LIMIT + 1)
    private var progressListener: ((JSObject) -> Unit)? = null

    // ── Service lifecycle ─────────────────────────────────────────────────

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification("Valaioli ready", 0))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CANCEL_JOB -> {
                val jobId = intent.getStringExtra(EXTRA_JOB_ID)
                if (!jobId.isNullOrBlank()) cancelJob(jobId)
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }

    // ── Engine init ───────────────────────────────────────────────────────

    fun initEngine(context: Context, onReady: (version: String) -> Unit) {
        executor.submit {
            try {
                YoutubeDL.getInstance().init(context)
                FFmpeg.getInstance().init(context)
                val version = try {
                    YoutubeDL.getInstance().version(context) ?: "embedded"
                } catch (_: Exception) { "embedded" }
                Log.i(TAG, "Engine ready. yt-dlp version: $version")
                onReady(version)
            } catch (e: Exception) {
                Log.e(TAG, "Engine init failed", e)
                onReady("error")
            }
        }
    }

    // ── Metadata fetch ────────────────────────────────────────────────────

    fun fetchMetadata(url: String): JSObject {
        validateUrl(url)
        val request = YoutubeDLRequest(url).apply {
            addOption("--dump-json")
            addOption("--no-playlist")
            addOption("--no-warnings")
            addOption("--skip-download")
        }

        val response: YoutubeDLResponse = YoutubeDL.getInstance().execute(request, null) { _, _ -> }
        val raw = response.out
        val json = JSONObject(raw)

        val formatsJson = json.optJSONArray("formats") ?: org.json.JSONArray()
        val formats = JSArray()

        // Always offer best audio options
        listOf(
            Triple("bestaudio/m4a", "m4a", "Audio · M4A (AAC)"),
            Triple("bestaudio/mp3", "mp3", "Audio · MP3 192kbps"),
        ).forEach { (fid, ext, note) ->
            formats.put(JSObject().apply {
                put("format_id", fid)
                put("ext", ext)
                put("resolution", JSONObject.NULL)
                put("vcodec", JSONObject.NULL)
                put("acodec", if (ext == "mp3") "mp3" else "aac")
                put("filesize_approx", JSONObject.NULL)
                put("has_video", false)
                put("has_audio", true)
                put("note", note)
            })
        }

        // Deduplicate video formats by height
        val seenHeights = mutableSetOf<Int>()
        for (i in formatsJson.length() - 1 downTo 0) {
            val f = formatsJson.optJSONObject(i) ?: continue
            val height = f.optInt("height", 0)
            val hasVideo = !f.optString("vcodec", "none").equals("none", ignoreCase = true)
            val hasAudio = !f.optString("acodec", "none").equals("none", ignoreCase = true)
            if (!hasVideo || height < 360) continue
            if (!seenHeights.add(height)) continue

            formats.put(JSObject().apply {
                put("format_id", f.optString("format_id"))
                put("ext", f.optString("ext", "mp4"))
                put("resolution", "${f.optInt("width")}×${height}")
                put("vcodec", f.optString("vcodec"))
                put("acodec", if (hasAudio) f.optString("acodec") else "opus (merged)")
                put("filesize_approx", if (f.has("filesize_approx")) f.getLong("filesize_approx") else JSONObject.NULL)
                put("has_video", true)
                put("has_audio", true)
                put("note", "${height}p · ${f.optString("ext", "mp4").uppercase()}")
            })
        }

        return JSObject().apply {
            put("title", json.optString("title", "Unknown"))
            put("thumbnail", json.optString("thumbnail", null))
            put("duration_seconds", json.optDouble("duration"))
            put("uploader", json.optString("uploader", null))
            put("formats", formats)
        }
    }

    fun fetchPlaylistMetadata(url: String): JSObject {
        validateUrl(url)
        val request = YoutubeDLRequest(url).apply {
            addOption("--dump-json")
            addOption("--flat-playlist")
            addOption("--yes-playlist")
            addOption("--no-warnings")
        }

        val response: YoutubeDLResponse = YoutubeDL.getInstance().execute(request, null) { _, _ -> }
        val lines = response.out.trim().split("\n")

        val entries = JSArray()
        lines.forEachIndexed { idx, line ->
            try {
                val e = JSONObject(line)
                entries.put(JSObject().apply {
                    put("index", idx + 1)
                    put("video_id", e.optString("id"))
                    put("title", e.optString("title", "Video ${idx + 1}"))
                    put("thumbnail", e.optString("thumbnail", null))
                    put("duration_seconds", e.optDouble("duration"))
                    put("url", "https://www.youtube.com/watch?v=${e.optString("id")}")
                })
            } catch (_: Exception) {}
        }

        return JSObject().apply {
            put("playlist_id", UUID.randomUUID().toString())
            put("title", "Playlist")
            put("uploader", null)
            put("entry_count", entries.length())
            put("entries", entries)
        }
    }

    // ── Job management ────────────────────────────────────────────────────

    fun createAndEnqueueJob(
        url: String,
        formatId: String,
        outputFormat: String,
        title: String?,
        thumbnail: String?,
        startTime: String?,
        endTime: String?,
        channel: String?,
        isGif: Boolean,
    ): ValaioliJob {
        validateUrl(url)
        val jobId = "android-${UUID.randomUUID()}"
        val job = ValaioliJob(
            jobId = jobId,
            state = "queued",
            createdAt = Instant.now().toString(),
            title = title,
            thumbnail = thumbnail,
            url = url,
            formatId = formatId,
            outputFormat = outputFormat,
            channel = channel,
            isGif = isGif,
            startTime = startTime,
            endTime = endTime,
        )
        jobs[jobId] = job
        cancellationFlags[jobId] = AtomicBoolean(false)
        executor.submit { executeJob(job) }
        return job
    }

    fun createPlaylistJobs(items: JSArray, preset: String, playlistTitle: String?): JSObject {
        val jobIds = mutableListOf<String>()
        val formatId = when {
            preset.contains("720") -> "bestvideo[height<=720]+bestaudio/best"
            preset.contains("480") -> "bestvideo[height<=480]+bestaudio/best"
            preset.contains("mp3") || preset.contains("audio") -> "bestaudio/mp3"
            else -> "bestvideo[height<=1080]+bestaudio/best"
        }
        val outputFormat = if (formatId.contains("mp3") || formatId.contains("audio")) "mp3" else "mp4"

        for (i in 0 until items.length()) {
            val item = items.getJSONObject(i)
            val job = createAndEnqueueJob(
                url = item.optString("url"),
                formatId = formatId,
                outputFormat = outputFormat,
                title = item.optString("title"),
                thumbnail = item.optString("thumbnail"),
                startTime = null,
                endTime = null,
                channel = playlistTitle,
                isGif = false,
            )
            jobIds.add(job.jobId)
        }

        return JSObject().apply {
            put("enqueued_count", jobIds.size)
            val arr = JSArray(); jobIds.forEach { arr.put(it) }
            put("job_ids", arr)
        }
    }

    fun getJob(jobId: String): ValaioliJob? = jobs[jobId]

    fun listJobs(): List<ValaioliJob> = jobs.values.sortedByDescending { it.createdAt }

    fun deleteJob(jobId: String) {
        cancellationFlags[jobId]?.set(true)
        jobs.remove(jobId)
        cancellationFlags.remove(jobId)
    }

    fun clearJobs(): Int {
        val terminal = jobs.values.filter { it.state in listOf("completed", "failed", "cancelled") }
        terminal.forEach { jobs.remove(it.jobId) }
        return terminal.size
    }

    fun cancelJob(jobId: String): ValaioliJob? {
        val job = jobs[jobId] ?: return null
        cancellationFlags[jobId]?.set(true)
        if (job.state in listOf("queued", "downloading", "merging", "converting", "paused")) {
            job.state = "cancelled"
            job.message = "Cancelled by user."
            job.completedAt = Instant.now().toString()
            emitProgress(job)
        }
        return job
    }

    fun pauseJob(jobId: String): ValaioliJob? {
        val job = jobs[jobId] ?: return null
        if (job.state == "downloading") {
            // youtubedl-android does not natively support pause;
            // we cancel and mark as paused so the user can retry.
            cancellationFlags[jobId]?.set(true)
            job.state = "paused"
            job.message = "Download paused (will restart on resume)."
            emitProgress(job)
        }
        return job
    }

    fun resumeJob(jobId: String): ValaioliJob? {
        val job = jobs[jobId] ?: return null
        if (job.state == "paused") {
            job.state = "queued"
            job.message = "Resuming…"
            val newFlag = AtomicBoolean(false)
            cancellationFlags[jobId] = newFlag
            executor.submit { executeJob(job) }
            emitProgress(job)
        }
        return job
    }

    fun retryJob(jobId: String): ValaioliJob? {
        val job = jobs[jobId] ?: return null
        if (job.state in listOf("failed", "cancelled")) {
            job.state = "queued"
            job.progressPercent = null
            job.message = "Retrying…"
            job.error = null
            job.completedAt = null
            val newFlag = AtomicBoolean(false)
            cancellationFlags[jobId] = newFlag
            executor.submit { executeJob(job) }
        }
        return job
    }

    // ── Core download execution ───────────────────────────────────────────

    private fun executeJob(job: ValaioliJob) {
        val cancelFlag = cancellationFlags[job.jobId] ?: AtomicBoolean(false)
        if (cancelFlag.get()) return

        try {
            job.state = "downloading"
            job.message = "Starting download…"
            emitProgress(job)
            updateNotification("Downloading: ${job.title ?: "media"}", 0)

            val outputDir = AndroidStorageHelper.getOutputDirectory(this, job.outputFormat ?: "mp4")
            val sanitizedTitle = sanitizeFilename(job.title ?: "valaioli_${job.jobId}")
            val ext = job.outputFormat ?: "mp4"

            // Build yt-dlp request through structured API only — never shell-concat user input
            val request = YoutubeDLRequest(job.url!!).apply {
                addOption("-f", buildFormatSelector(job.formatId!!, job.outputFormat ?: "mp4"))
                addOption("-o", "${outputDir.absolutePath}/${sanitizedTitle}.%(ext)s")
                addOption("--no-playlist")
                addOption("--no-warnings")
                addOption("--merge-output-format", if (ext == "mp3") "mp3" else "mp4")
                if (ext == "mp3") {
                    addOption("-x")
                    addOption("--audio-format", "mp3")
                    addOption("--audio-quality", "192k")
                }
                job.startTime?.let { addOption("--postprocessor-args", "ffmpeg:-ss $it") }
            }

            YoutubeDL.getInstance().execute(request, job.jobId) { progress, _, line ->
                if (cancelFlag.get()) return@execute
                job.progressPercent = progress.toDouble()
                job.message = "Downloading… ${progress.toInt()}%"
                emitProgress(job)
                updateNotification("Downloading: ${job.title ?: "media"}", progress.toInt())
            }

            if (cancelFlag.get()) {
                job.state = "cancelled"
                job.message = "Cancelled."
                job.completedAt = Instant.now().toString()
                emitProgress(job)
                return
            }

            job.state = "validating"
            job.progressPercent = 98.0
            job.message = "Validating output…"
            emitProgress(job)

            // Locate the output file
            val outputFile = outputDir.listFiles()?.firstOrNull {
                it.name.startsWith(sanitizedTitle) && it.extension.isNotEmpty() && !it.name.endsWith(".part")
            }

            if (outputFile == null || !outputFile.exists() || outputFile.length() == 0L) {
                throw Exception("Output file not found or empty after download.")
            }

            // Publish to MediaStore so it appears in Downloads/Music apps
            AndroidStorageHelper.publishToMediaStore(this, outputFile, job.outputFormat ?: "mp4")

            job.state = "completed"
            job.progressPercent = 100.0
            job.message = "Download complete."
            job.completedAt = Instant.now().toString()
            job.filePath = outputFile.absolutePath
            emitProgress(job)
            updateNotification("Completed: ${job.title ?: "download"}", 100)

        } catch (e: Exception) {
            if (cancelFlag.get()) {
                job.state = "cancelled"
                job.message = "Cancelled."
            } else {
                Log.e(TAG, "Job ${job.jobId} failed", e)
                job.state = "failed"
                job.error = sanitizeError(e)
                job.message = "Download failed."
            }
            job.completedAt = Instant.now().toString()
            emitProgress(job)
            updateNotification("Failed: ${job.title ?: "download"}", 0)
        }
    }

    private fun buildFormatSelector(formatId: String, outputFormat: String): String {
        if (outputFormat == "mp3" || formatId.startsWith("bestaudio")) {
            return "bestaudio/best"
        }
        return when {
            formatId.contains("+") -> formatId
            else -> "$formatId+bestaudio/best[ext=m4a]/$formatId/best"
        }
    }

    // ── Engine info & update check ────────────────────────────────────────

    fun getEngineInfo(): JSObject {
        return JSObject().apply {
            put("library_version", "0.18.1")
            put("ytdlp_version", try {
                YoutubeDL.getInstance().version(this@DownloadService) ?: "dynamic"
            } catch (_: Exception) { "dynamic" })
            put("ffmpeg_version", "embedded")
            put("status", "ready")
        }
    }

    fun checkReleaseUpdate(context: Context): JSObject {
        return try {
            val url = java.net.URL("https://api.github.com/repos/valaioli/valaioli/releases/latest")
            val conn = url.openConnection() as java.net.HttpURLConnection
            conn.setRequestProperty("Accept", "application/vnd.github+json")
            conn.connectTimeout = 8000
            conn.readTimeout = 8000
            val resp = conn.inputStream.bufferedReader().readText()
            val json = JSONObject(resp)
            val latest = json.optString("tag_name", "")
            val currentVersion = "v1.0.0" // Matches versionName in build.gradle
            JSObject().apply {
                put("hasUpdate", latest.isNotEmpty() && latest != currentVersion)
                put("latestVersion", latest)
                put("releaseUrl", json.optString("html_url", "https://github.com/"))
                put("notes", json.optString("body", "").take(500))
            }
        } catch (_: Exception) {
            JSObject().apply {
                put("hasUpdate", false)
                put("latestVersion", "unknown")
                put("releaseUrl", "https://github.com/")
                put("notes", "")
            }
        }
    }

    // ── Notification ──────────────────────────────────────────────────────

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            NOTIFICATION_CHANNEL_ID,
            "Valaioli Downloads",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Active and queued media downloads"
            setShowBadge(false)
        }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(title: String, progress: Int): Notification {
        val openIntent = PendingIntent.getActivity(
            this, 0,
            packageManager.getLaunchIntentForPackage(packageName),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val builder = NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle("Valaioli")
            .setContentText(title)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)

        if (progress in 1..99) {
            builder.setProgress(100, progress, false)
        } else if (progress == 0 && title.contains("ready", ignoreCase = true)) {
            builder.setProgress(0, 0, false)
        }

        return builder.build()
    }

    private fun updateNotification(title: String, progress: Int) {
        val notification = buildNotification(title, progress)
        try {
            NotificationManagerCompat.from(this).notify(NOTIFICATION_ID, notification)
        } catch (_: Exception) {}
    }

    // ── Event emission ────────────────────────────────────────────────────

    fun setProgressListener(listener: (JSObject) -> Unit) {
        progressListener = listener
    }

    private fun emitProgress(job: ValaioliJob) {
        val event = JSObject().apply {
            put("job_id", job.jobId)
            put("state", job.state)
            put("progress_percent", job.progressPercent ?: 0.0)
            put("message", job.message ?: "")
            put("file_path", job.filePath ?: "")
        }
        progressListener?.invoke(event)
    }

    // ── Filename sanitisation ─────────────────────────────────────────────

    private fun sanitizeFilename(name: String): String {
        return name
            .replace(Regex("[/\\\\:*?\"<>|]"), "_")
            .replace(Regex("\\s+"), "_")
            .take(100)
            .trimEnd('.')
            .ifBlank { "valaioli_download" }
    }

    private fun sanitizeError(e: Exception): String {
        return e.message?.take(200) ?: "Unknown error"
    }

    // ── URL validation ────────────────────────────────────────────────────

    private fun validateUrl(url: String) {
        if (url.isBlank()) throw IllegalArgumentException("URL must not be empty")
        val lower = url.lowercase()
        if (!lower.startsWith("https://") && !lower.startsWith("http://")) {
            throw IllegalArgumentException("Only HTTP/HTTPS URLs are permitted")
        }
        val banned = listOf("169.254.", "127.0.", "localhost", "file://", "::1")
        if (banned.any { lower.contains(it) }) {
            throw IllegalArgumentException("URL rejected for security reasons")
        }
    }
}
