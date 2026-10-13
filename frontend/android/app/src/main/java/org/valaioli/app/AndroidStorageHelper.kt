package org.valaioli.app

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import java.io.File

/**
 * AndroidStorageHelper
 *
 * Encapsulates Android Scoped Storage interactions.
 *
 * On Android 10+ (API 29+) we write completed files into MediaStore
 * (Downloads, Music, or Movies) so the file is immediately discoverable
 * in the Files app, Gallery, and Music apps without requiring
 * MANAGE_EXTERNAL_STORAGE or READ_EXTERNAL_STORAGE permissions.
 *
 * On older API levels (minimum API 23 for this project) we fall back
 * to the standard public external storage directories, which require
 * WRITE_EXTERNAL_STORAGE permission.
 */
object AndroidStorageHelper {

    private const val TAG = "ValaioliStorage"
    private const val VALAIOLI_DIR = "Valaioli"

    /**
     * Returns a local staging directory for the download process.
     * youtubedl-android writes here first; we then copy/move to MediaStore.
     */
    fun getOutputDirectory(context: Context, outputFormat: String): File {
        val cacheBase = context.cacheDir
        val dir = File(cacheBase, "valaioli_staging").apply { mkdirs() }
        return dir
    }

    /**
     * Move a completed download from the staging cache to the appropriate
     * public MediaStore location, then delete the staging copy.
     *
     * Returns the final public URI, or null if the operation failed.
     */
    fun publishToMediaStore(context: Context, file: File, outputFormat: String): Uri? {
        if (!file.exists()) return null

        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                publishViaMediaStore(context, file, outputFormat)
            } else {
                publishLegacy(context, file, outputFormat)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to publish ${file.name} to MediaStore", e)
            null
        }
    }

    private fun publishViaMediaStore(context: Context, file: File, outputFormat: String): Uri? {
        val isAudio = outputFormat in listOf("mp3", "m4a", "wav", "ogg", "opus", "aac", "flac")
        val isVideo = outputFormat in listOf("mp4", "mkv", "webm", "avi", "mov")

        val (collection, relativePathBase) = when {
            isAudio -> MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY) to
                    "${Environment.DIRECTORY_MUSIC}/$VALAIOLI_DIR"
            isVideo -> MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY) to
                    "${Environment.DIRECTORY_MOVIES}/$VALAIOLI_DIR"
            else    -> MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY) to
                    "${Environment.DIRECTORY_DOWNLOADS}/$VALAIOLI_DIR"
        }

        val mimeType = when (outputFormat) {
            "mp3"  -> "audio/mpeg"
            "m4a"  -> "audio/mp4"
            "wav"  -> "audio/wav"
            "ogg"  -> "audio/ogg"
            "flac" -> "audio/flac"
            "mp4"  -> "video/mp4"
            "mkv"  -> "video/x-matroska"
            "webm" -> "video/webm"
            "gif"  -> "image/gif"
            else   -> "application/octet-stream"
        }

        val contentValues = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, file.name)
            put(MediaStore.MediaColumns.MIME_TYPE, mimeType)
            put(MediaStore.MediaColumns.RELATIVE_PATH, relativePathBase)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }

        val resolver = context.contentResolver
        val uri = resolver.insert(collection, contentValues) ?: return null

        resolver.openOutputStream(uri)?.use { out ->
            file.inputStream().use { inp -> inp.copyTo(out) }
        }

        contentValues.clear()
        contentValues.put(MediaStore.MediaColumns.IS_PENDING, 0)
        resolver.update(uri, contentValues, null, null)

        file.delete() // clean up staging copy

        Log.i(TAG, "Published ${file.name} → $uri")
        return uri
    }

    @Suppress("DEPRECATION")
    private fun publishLegacy(context: Context, file: File, outputFormat: String): Uri? {
        val isAudio = outputFormat in listOf("mp3", "m4a", "wav", "ogg")
        val isVideo = outputFormat in listOf("mp4", "mkv", "webm", "avi")

        val baseDir = when {
            isAudio -> Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC)
            isVideo -> Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES)
            else    -> Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        }

        val valaioliDir = File(baseDir, VALAIOLI_DIR).apply { mkdirs() }
        val dest = File(valaioliDir, file.name)
        file.copyTo(dest, overwrite = true)
        file.delete()

        return Uri.fromFile(dest)
    }
}
