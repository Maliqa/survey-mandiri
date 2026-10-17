package id.surveymandiri.app.data

import okhttp3.MultipartBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

/** Mirrors the backend contract in README §3 (base: /api/v1/). */
interface ApiService {
    // Auth
    @POST("api/v1/auth/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @POST("api/v1/auth/logout")
    suspend fun logout(@Body body: RefreshRequest): Response<Unit>

    @POST("api/v1/auth/register/client")
    suspend fun registerClient(@Body body: ClientRegisterRequest): UserDto

    @Multipart
    @POST("api/v1/auth/register/surveyor")
    suspend fun registerSurveyor(@Part parts: List<MultipartBody.Part>): UserDto

    @GET("api/v1/me")
    suspend fun me(): UserDto

    // Client
    @GET("api/v1/pricing")
    suspend fun pricing(): List<PricingRateDto>

    @GET("api/v1/requests")
    suspend fun requests(@Query("page") page: Int = 1): Page<SurveyRequestDto>

    @POST("api/v1/requests")
    suspend fun createRequest(@Body body: CreateRequestBody): SurveyRequestDto

    @GET("api/v1/requests/{id}")
    suspend fun request(@Path("id") id: Long): SurveyRequestDto

    @POST("api/v1/requests/{id}/approve-quote")
    suspend fun approveQuote(@Path("id") id: Long): SurveyRequestDto

    @POST("api/v1/requests/{id}/pay")
    suspend fun pay(@Path("id") id: Long, @Body body: PayBody = PayBody()): SurveyRequestDto

    @POST("api/v1/requests/{id}/cancel")
    suspend fun cancel(@Path("id") id: Long): SurveyRequestDto

    @POST("api/v1/requests/{id}/complete")
    suspend fun complete(@Path("id") id: Long): SurveyRequestDto

    @GET("api/v1/requests/{id}/reports")
    suspend fun requestReports(@Path("id") id: Long, @Query("page") page: Int = 1): Page<ReportDto>

    @POST("api/v1/reports/{id}/reject")
    suspend fun rejectReport(@Path("id") id: Long, @Body body: RejectBody): ReportDto

    // Surveyor
    @GET("api/v1/jobs/available")
    suspend fun availableJobs(): Page<JobDto>

    @GET("api/v1/jobs/{id}")
    suspend fun job(@Path("id") id: Long): JobDto

    @POST("api/v1/jobs/{id}/accept")
    suspend fun acceptJob(@Path("id") id: Long, @Body body: AcceptBody): AssignmentDto

    @GET("api/v1/assignments")
    suspend fun assignments(): Page<AssignmentDto>

    @GET("api/v1/assignments/{id}")
    suspend fun assignment(@Path("id") id: Long): AssignmentDto

    @POST("api/v1/assignments/{id}/withdraw")
    suspend fun withdraw(@Path("id") id: Long): AssignmentDto

    @GET("api/v1/assignments/{id}/reports")
    suspend fun assignmentReports(@Path("id") id: Long): List<ReportDto>

    /** Returns Response so the upload worker can tell retryable from permanent errors. */
    @Multipart
    @POST("api/v1/assignments/{id}/reports")
    suspend fun submitReport(@Path("id") id: Long, @Part parts: List<MultipartBody.Part>): Response<ReportDto>

    @GET("api/v1/payouts")
    suspend fun payouts(): PayoutPage
}
