package id.surveymandiri.app.data

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.google.gson.Gson
import id.surveymandiri.app.SurveyApp
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.io.IOException
import java.util.Locale
import java.util.concurrent.TimeUnit

/** A survey report saved on the device, waiting to be uploaded. */
data class PendingReport(
    val clientUuid: String,
    val assignmentId: Long,
    val respondentLabel: String,
    val answersJson: String,
    val notes: String,
    val latitude: Double,
    val longitude: Double,
    val gpsAccuracyM: Double,
    val city: String,
    val capturedAt: String,
    val isMock: Boolean,
    val photoPath: String,
    val lastError: String? = null,
    val failedPermanently: Boolean = false,
)

/**
 * File-based outbox: one JSON + one JPEG per report in app-private storage.
 * Survives app restarts; the server de-duplicates by client_uuid, so retries are safe.
 */
class PendingReportStore(context: Context, private val gson: Gson) {
    private val dir = File(context.filesDir, "pending_reports").apply { mkdirs() }
    private val _changes = MutableStateFlow(0)

    /** Bumps on every change so Compose screens can re-read the outbox. */
    val changes: StateFlow<Int> = _changes

    fun photoFileFor(clientUuid: String): File = File(dir, "$clientUuid.jpg")

    @Synchronized
    fun save(report: PendingReport) {
        File(dir, "${report.clientUuid}.json").writeText(gson.toJson(report))
        _changes.value = _changes.value + 1
    }

    @Synchronized
    fun all(): List<PendingReport> {
        val files = dir.listFiles { f -> f.extension == "json" } ?: return emptyList()
        return files.mapNotNull { f ->
            runCatching { gson.fromJson(f.readText(), PendingReport::class.java) }.getOrNull()
        }.sortedBy { it.capturedAt }
    }

    fun forAssignment(assignmentId: Long): List<PendingReport> = all().filter { it.assignmentId == assignmentId }

    @Synchronized
    fun remove(report: PendingReport) {
        File(dir, "${report.clientUuid}.json").delete()
        File(report.photoPath).delete()
        _changes.value = _changes.value + 1
    }
}

class UploadWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val container = (applicationContext as SurveyApp).container
        if (container.tokenStore.access == null) return Result.success() // logged out: keep outbox
        val store = container.pendingReports
        var shouldRetry = false

        for (report in store.all().filter { !it.failedPermanently }) {
            val photo = File(report.photoPath)
            if (!photo.exists()) {
                store.save(report.copy(lastError = "Foto tidak ditemukan di HP.", failedPermanently = true))
                continue
            }
            try {
                val response = container.api.submitReport(report.assignmentId, buildParts(report, photo))
                val code = response.code()
                when {
                    response.isSuccessful -> store.remove(report) // 201 new, 200 duplicate retry
                    code == 401 || code == 408 || code == 429 || code >= 500 -> {
                        shouldRetry = true
                        store.save(report.copy(lastError = "Server sibuk ($code), akan dicoba lagi."))
                    }
                    else -> {
                        val error = parseErrorBody(response.errorBody()?.string(), code)
                        store.save(report.copy(lastError = error.message, failedPermanently = true))
                    }
                }
            } catch (e: IOException) {
                shouldRetry = true
                break // offline: stop and let WorkManager retry when the network is back
            }
        }
        return if (shouldRetry) Result.retry() else Result.success()
    }

    companion object {
        private const val WORK_NAME = "report-upload"

        fun enqueue(context: Context) {
            val request = OneTimeWorkRequestBuilder<UploadWorker>()
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(WORK_NAME, ExistingWorkPolicy.APPEND_OR_REPLACE, request)
        }

        fun buildParts(r: PendingReport, photo: File): List<MultipartBody.Part> {
            fun field(name: String, value: String) = MultipartBody.Part.createFormData(name, value)
            fun coord(v: Double) = String.format(Locale.US, "%.7f", v)
            return listOf(
                field("client_uuid", r.clientUuid),
                field("respondent_label", r.respondentLabel),
                field("answers", r.answersJson),
                field("notes", r.notes),
                field("latitude", coord(r.latitude)),
                field("longitude", coord(r.longitude)),
                field("gps_accuracy_m", String.format(Locale.US, "%.1f", r.gpsAccuracyM)),
                field("city", r.city),
                field("captured_at", r.capturedAt),
                field("is_mock_location", if (r.isMock) "true" else "false"),
                MultipartBody.Part.createFormData("photo", photo.name, photo.asRequestBody("image/jpeg".toMediaType())),
            )
        }
    }
}
