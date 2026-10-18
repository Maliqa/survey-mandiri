package id.surveymandiri.app.data

import com.google.gson.JsonObject
import com.google.gson.annotations.SerializedName

// ---- Auth ---------------------------------------------------------------------------------
data class LoginRequest(val email: String, val password: String)

data class RefreshRequest(val refresh: String)

data class TokenPair(val access: String, val refresh: String?)

data class LoginResponse(val access: String, val refresh: String, val user: UserDto)

data class ClientRegisterRequest(
    val email: String,
    val password: String,
    val phone: String,
    @SerializedName("client_type") val clientType: String,
    val organization: String,
)

data class SurveyorProfileDto(
    @SerializedName("full_name") val fullName: String,
    val city: String,
    val status: String,
    @SerializedName("rejection_reason") val rejectionReason: String?,
    @SerializedName("completed_units") val completedUnits: Int?,
)

data class UserDto(
    val id: Long,
    val email: String,
    val phone: String?,
    val role: String,
    @SerializedName("client_type") val clientType: String?,
    val organization: String?,
    @SerializedName("surveyor_profile") val surveyorProfile: SurveyorProfileDto?,
)

// ---- Pricing ------------------------------------------------------------------------------
data class PricingRateDto(
    val category: String,
    @SerializedName("unit_label") val unitLabel: String,
    @SerializedName("unit_price") val unitPrice: Long,
    @SerializedName("min_units") val minUnits: Int,
    @SerializedName("max_units") val maxUnits: Int,
)

// ---- Generic page -------------------------------------------------------------------------
data class Page<T>(val count: Int, val next: String?, val results: List<T>)

// ---- Client requests ------------------------------------------------------------------------
data class AssignmentSummaryDto(
    val id: Long,
    @SerializedName("surveyor_name") val surveyorName: String?,
    val units: Int,
    val status: String,
    @SerializedName("reports_submitted") val reportsSubmitted: Int,
)

data class SurveyRequestDto(
    val id: Long,
    val category: String,
    val title: String,
    val description: String?,
    val details: JsonObject?,
    val quantity: Int,
    @SerializedName("target_cities") val targetCities: List<String>?,
    val address: String?,
    val latitude: Double?,
    val longitude: Double?,
    val deadline: String,
    @SerializedName("unit_price") val unitPrice: Long,
    @SerializedName("total_price") val totalPrice: Long,
    val status: String,
    @SerializedName("claimed_units") val claimedUnits: Int,
    @SerializedName("remaining_units") val remainingUnits: Int,
    @SerializedName("escrow_status") val escrowStatus: String?,
    val assignments: List<AssignmentSummaryDto>?,
    @SerializedName("created_at") val createdAt: String?,
)

data class CreateRequestBody(
    val category: String,
    val title: String,
    val description: String,
    val details: Map<String, Any>,
    val quantity: Int,
    @SerializedName("target_cities") val targetCities: List<String>,
    val address: String,
    val latitude: Double?,
    val longitude: Double?,
    val deadline: String,
)

data class ReportLinkDto(
    val url: String,
    @SerializedName("pdf_url") val pdfUrl: String,
    @SerializedName("expires_at") val expiresAt: String?,
)

data class PayBody(val reference: String = "DEMO-APP")

data class RejectBody(val reason: String)

// ---- Surveyor jobs ----------------------------------------------------------------------------
data class JobDto(
    val id: Long,
    val category: String,
    val title: String,
    val description: String?,
    val details: JsonObject?,
    val quantity: Int,
    @SerializedName("remaining_units") val remainingUnits: Int,
    @SerializedName("target_cities") val targetCities: List<String>?,
    val address: String?,
    val latitude: Double?,
    val longitude: Double?,
    val deadline: String,
    @SerializedName("unit_earning") val unitEarning: Long,
    val status: String,
    @SerializedName("distance_km") val distanceKm: Double?,
)

data class AcceptBody(val units: Int)

data class AssignmentDto(
    val id: Long,
    val units: Int,
    val status: String,
    @SerializedName("reports_submitted") val reportsSubmitted: Int,
    val job: JobDto,
)

// ---- Reports ------------------------------------------------------------------------------------
data class ReportDto(
    val id: Long,
    @SerializedName("client_uuid") val clientUuid: String,
    @SerializedName("surveyor_name") val surveyorName: String?,
    @SerializedName("respondent_label") val respondentLabel: String?,
    val answers: JsonObject?,
    val notes: String?,
    @SerializedName("photo_url") val photoUrl: String,
    val latitude: Double,
    val longitude: Double,
    @SerializedName("gps_accuracy_m") val gpsAccuracyM: Double,
    val city: String?,
    @SerializedName("captured_at") val capturedAt: String,
    val status: String,
    val flags: List<String>?,
    @SerializedName("rejection_reason") val rejectionReason: String?,
)

// ---- Payouts --------------------------------------------------------------------------------------
data class PayoutDto(
    val id: Long,
    @SerializedName("request_title") val requestTitle: String?,
    val units: Int,
    @SerializedName("net_amount") val netAmount: Long,
    val status: String,
    @SerializedName("created_at") val createdAt: String?,
)

data class PayoutPage(val count: Int, val results: List<PayoutDto>, val totals: Map<String, Long>?)

/** Category-specific questions live in `details.questions` for caleg/product requests. */
fun JsonObject?.questions(): List<String> = runCatching {
    this?.getAsJsonArray("questions")?.mapNotNull { el -> runCatching { el.asString }.getOrNull() }
}.getOrNull().orEmpty()

fun JsonObject?.stringField(name: String): String? = runCatching {
    val el = this?.get(name)
    if (el == null || el.isJsonNull) null else el.asString
}.getOrNull()
