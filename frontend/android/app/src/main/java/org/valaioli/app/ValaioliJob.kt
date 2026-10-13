package org.valaioli.app

/**
 * ValaioliJob — in-memory job state record shared between
 * ValaioliNativePlugin and DownloadService.
 */
data class ValaioliJob(
    val jobId: String,
    var state: String,                    // queued|downloading|merging|completed|failed|cancelled|paused
    var progressPercent: Double? = null,
    var message: String? = null,
    val createdAt: String,
    var completedAt: String? = null,
    var error: String? = null,
    val title: String? = null,
    val thumbnail: String? = null,
    val url: String? = null,
    val formatId: String? = null,
    val outputFormat: String? = null,
    val channel: String? = null,
    val isGif: Boolean = false,
    val startTime: String? = null,
    val endTime: String? = null,
    var filePath: String? = null,
)
