package org.valaioli.app

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import com.getcapacitor.*
import com.getcapacitor.annotation.CapacitorPlugin
import org.json.JSONArray
import org.json.JSONObject

/**
 * ValaioliNativePlugin
 *
 * Capacitor plugin bridging the React/WebView frontend to the Android
 * download engine (youtubedl-android). All download operations are
 * dispatched to DownloadService (a foreground service) so that jobs
 * continue when the user leaves the app.
 *
 * Plugin ID on the JS side: "ValaioliNative"
 */
@CapacitorPlugin(name = "ValaioliNative")
class ValaioliNativePlugin : Plugin() {

    private var serviceConnection: ValaioliServiceConnection? = null
    private var downloadService: DownloadService? = null
    private var serviceBound = false

    // ── Lifecycle ──────────────────────────────────────────────────────────

    override fun load() {
        super.load()
        bindToService()
    }

    override fun handleOnDestroy() {
        unbindFromService()
        super.handleOnDestroy()
    }

    private fun bindToService() {
        val intent = Intent(context, DownloadService::class.java)
        val conn = object : ValaioliServiceConnection() {
            override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
                val localBinder = binder as? DownloadService.LocalBinder
                downloadService = localBinder?.getService()
                serviceBound = true

                // Forward progress events from service to web layer
                downloadService?.setProgressListener { event ->
                    notifyListeners("downloadProgress", event)
                }
            }

            override fun onServiceDisconnected(name: ComponentName?) {
                downloadService = null
                serviceBound = false
            }
        }
        serviceConnection = conn
        context.bindService(intent, conn, Context.BIND_AUTO_CREATE)
    }

    private fun unbindFromService() {
        serviceConnection?.let {
            try { context.unbindService(it) } catch (_: Exception) {}
        }
        serviceBound = false
        downloadService = null
    }

    // ── Plugin methods ─────────────────────────────────────────────────────

    @PluginMethod
    fun initEngine(call: PluginCall) {
        val svc = downloadService
        if (svc == null) {
            // Start + bind if not yet connected
            val intent = Intent(context, DownloadService::class.java)
            context.startService(intent)
            call.resolve(JSObject().apply {
                put("status", "starting")
                put("ytdlp_version", "dynamic")
            })
            return
        }
        svc.initEngine(context) { version ->
            call.resolve(JSObject().apply {
                put("status", "ok")
                put("ytdlp_version", version)
            })
        }
    }

    @PluginMethod
    fun fetchMetadata(call: PluginCall) {
        val url = call.getString("url")
        if (url.isNullOrBlank()) {
            call.reject("url is required")
            return
        }
        val svc = downloadService
        if (svc == null) {
            call.reject("Engine not initialized. Call initEngine first.")
            return
        }
        bridge.executeOnThread(Runnable {
            try {
                val meta = svc.fetchMetadata(url)
                call.resolve(meta)
            } catch (e: Exception) {
                call.reject(sanitizeErrorMessage(e), null, e)
            }
        })
    }

    @PluginMethod
    fun createJob(call: PluginCall) {
        val url = call.getString("url")
        val formatId = call.getString("format_id")
        if (url.isNullOrBlank() || formatId.isNullOrBlank()) {
            call.reject("url and format_id are required")
            return
        }
        val svc = downloadService
        if (svc == null) {
            call.reject("Engine not initialized.")
            return
        }
        bridge.executeOnThread(Runnable {
            try {
                val jobStatus = svc.createAndEnqueueJob(
                    url = url,
                    formatId = formatId,
                    outputFormat = call.getString("output_format") ?: "mp4",
                    title = call.getString("title"),
                    thumbnail = call.getString("thumbnail"),
                    startTime = call.getString("start_time"),
                    endTime = call.getString("end_time"),
                    channel = call.getString("channel"),
                    isGif = call.getBoolean("is_gif") ?: false
                )
                call.resolve(jobStatusToJSObject(jobStatus))
            } catch (e: Exception) {
                call.reject(sanitizeErrorMessage(e), null, e)
            }
        })
    }

    @PluginMethod
    fun getJob(call: PluginCall) {
        val jobId = call.getString("jobId")
        if (jobId.isNullOrBlank()) {
            call.reject("jobId is required")
            return
        }
        val svc = downloadService
        if (svc == null) {
            call.reject("Engine not initialized.")
            return
        }
        val job = svc.getJob(jobId)
        if (job == null) {
            call.reject("Job not found: $jobId")
            return
        }
        call.resolve(jobStatusToJSObject(job))
    }

    @PluginMethod
    fun listJobs(call: PluginCall) {
        val svc = downloadService
        if (svc == null) {
            call.resolve(JSObject().apply { put("jobs", JSArray()) })
            return
        }
        val jobs = svc.listJobs()
        val arr = JSArray()
        jobs.forEach { arr.put(jobStatusToJSObject(it)) }
        call.resolve(JSObject().apply { put("jobs", arr) })
    }

    @PluginMethod
    fun deleteJob(call: PluginCall) {
        val jobId = call.getString("jobId")
        if (jobId.isNullOrBlank()) {
            call.reject("jobId is required")
            return
        }
        downloadService?.deleteJob(jobId)
        call.resolve(JSObject().apply { put("success", true) })
    }

    @PluginMethod
    fun clearJobs(call: PluginCall) {
        val cleared = downloadService?.clearJobs() ?: 0
        call.resolve(JSObject().apply { put("cleared", cleared) })
    }

    @PluginMethod
    fun cancelJob(call: PluginCall) {
        val jobId = call.getString("jobId")
        if (jobId.isNullOrBlank()) {
            call.reject("jobId is required")
            return
        }
        bridge.executeOnThread(Runnable {
            try {
                val job = downloadService?.cancelJob(jobId)
                if (job == null) {
                    call.reject("Job not found or already finished.")
                    return@Runnable
                }
                call.resolve(jobStatusToJSObject(job))
            } catch (e: Exception) {
                call.reject(sanitizeErrorMessage(e), null, e)
            }
        })
    }

    @PluginMethod
    fun pauseJob(call: PluginCall) {
        val jobId = call.getString("jobId")
        if (jobId.isNullOrBlank()) {
            call.reject("jobId is required")
            return
        }
        val job = downloadService?.pauseJob(jobId)
        if (job == null) {
            call.reject("Job not found: $jobId")
            return
        }
        call.resolve(jobStatusToJSObject(job))
    }

    @PluginMethod
    fun resumeJob(call: PluginCall) {
        val jobId = call.getString("jobId")
        if (jobId.isNullOrBlank()) {
            call.reject("jobId is required")
            return
        }
        bridge.executeOnThread(Runnable {
            try {
                val job = downloadService?.resumeJob(jobId)
                if (job == null) {
                    call.reject("Job not found: $jobId")
                    return@Runnable
                }
                call.resolve(jobStatusToJSObject(job))
            } catch (e: Exception) {
                call.reject(sanitizeErrorMessage(e), null, e)
            }
        })
    }

    @PluginMethod
    fun retryJob(call: PluginCall) {
        val jobId = call.getString("jobId")
        if (jobId.isNullOrBlank()) {
            call.reject("jobId is required")
            return
        }
        bridge.executeOnThread(Runnable {
            try {
                val job = downloadService?.retryJob(jobId)
                if (job == null) {
                    call.reject("Job not found: $jobId")
                    return@Runnable
                }
                call.resolve(jobStatusToJSObject(job))
            } catch (e: Exception) {
                call.reject(sanitizeErrorMessage(e), null, e)
            }
        })
    }

    @PluginMethod
    fun fetchPlaylistMetadata(call: PluginCall) {
        val url = call.getString("url")
        if (url.isNullOrBlank()) {
            call.reject("url is required")
            return
        }
        val svc = downloadService
        if (svc == null) {
            call.reject("Engine not initialized.")
            return
        }
        bridge.executeOnThread(Runnable {
            try {
                val meta = svc.fetchPlaylistMetadata(url)
                call.resolve(meta)
            } catch (e: Exception) {
                call.reject(sanitizeErrorMessage(e), null, e)
            }
        })
    }

    @PluginMethod
    fun createPlaylistJobs(call: PluginCall) {
        val itemsArray = call.getArray("items")
        val preset = call.getString("preset") ?: "1080p"
        val playlistTitle = call.getString("playlist_title")
        if (itemsArray == null) {
            call.reject("items array is required")
            return
        }
        val svc = downloadService
        if (svc == null) {
            call.reject("Engine not initialized.")
            return
        }
        bridge.executeOnThread(Runnable {
            try {
                val result = svc.createPlaylistJobs(itemsArray, preset, playlistTitle)
                call.resolve(result)
            } catch (e: Exception) {
                call.reject(sanitizeErrorMessage(e), null, e)
            }
        })
    }

    @PluginMethod
    fun getEngineInfo(call: PluginCall) {
        bridge.executeOnThread(Runnable {
            try {
                val info = downloadService?.getEngineInfo()
                call.resolve(info ?: JSObject().apply {
                    put("library_version", "0.18.1")
                    put("ytdlp_version", "dynamic")
                    put("ffmpeg_version", "embedded")
                    put("status", "not-initialized")
                })
            } catch (e: Exception) {
                call.resolve(JSObject().apply {
                    put("library_version", "0.18.1")
                    put("ytdlp_version", "dynamic")
                    put("ffmpeg_version", "embedded")
                    put("status", "error")
                })
            }
        })
    }

    @PluginMethod
    fun checkReleaseUpdate(call: PluginCall) {
        bridge.executeOnThread(Runnable {
            try {
                val result = downloadService?.checkReleaseUpdate(context)
                    ?: JSObject().apply {
                        put("hasUpdate", false)
                        put("latestVersion", "unknown")
                        put("releaseUrl", "https://github.com/")
                        put("notes", "")
                    }
                call.resolve(result)
            } catch (e: Exception) {
                call.resolve(JSObject().apply {
                    put("hasUpdate", false)
                    put("latestVersion", "unknown")
                    put("releaseUrl", "https://github.com/")
                    put("notes", "")
                })
            }
        })
    }

    // ── Helpers ────────────────────────────────────────────────────────────

    private fun jobStatusToJSObject(job: ValaioliJob): JSObject {
        return JSObject().apply {
            put("job_id", job.jobId)
            put("state", job.state)
            put("progress_percent", job.progressPercent ?: JSONObject.NULL)
            put("message", job.message ?: JSONObject.NULL)
            put("created_at", job.createdAt)
            put("completed_at", job.completedAt ?: JSONObject.NULL)
            put("error", job.error ?: JSONObject.NULL)
            put("title", job.title ?: JSONObject.NULL)
            put("thumbnail", job.thumbnail ?: JSONObject.NULL)
            put("url", job.url ?: JSONObject.NULL)
            put("format_id", job.formatId ?: JSONObject.NULL)
            put("output_format", job.outputFormat ?: JSONObject.NULL)
            put("channel", job.channel ?: JSONObject.NULL)
            put("is_gif", job.isGif)
        }
    }

    /**
     * Strip internal paths and stack trace details from errors
     * before surfacing them to the WebView layer.
     */
    private fun sanitizeErrorMessage(e: Exception): String {
        return when {
            e.message?.contains("HTTP") == true -> "Network error: ${e.message}"
            e.message?.contains("timeout", ignoreCase = true) == true -> "Request timed out. Check your internet connection."
            e.message?.contains("Unsupported URL", ignoreCase = true) == true -> "Unsupported or unavailable URL."
            e.message?.contains("ffmpeg", ignoreCase = true) == true -> "Media processing error. The download may be in an unsupported format."
            e.message?.contains("storage", ignoreCase = true) == true -> "Storage error. Check available disk space and permissions."
            else -> e.message?.take(200) ?: "An unexpected error occurred."
        }
    }
}

abstract class ValaioliServiceConnection : ServiceConnection {
    override fun onServiceConnected(name: ComponentName?, service: IBinder?) {}
    override fun onServiceDisconnected(name: ComponentName?) {}
}
