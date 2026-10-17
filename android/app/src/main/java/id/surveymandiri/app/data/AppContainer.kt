package id.surveymandiri.app.data

import android.content.Context
import coil.ImageLoader
import com.google.gson.Gson
import id.surveymandiri.app.BuildConfig
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/**
 * Manual dependency container (one per process).
 * Kept deliberately simple instead of Hilt: fewer moving parts for a CI-only build.
 */
class AppContainer(context: Context) {
    val appContext: Context = context.applicationContext
    val baseUrl: String = BuildConfig.API_BASE_URL
    val gson = Gson()
    val tokenStore = TokenStore(appContext)

    private val plainClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    val okHttp: OkHttpClient = plainClient.newBuilder()
        .addInterceptor(AuthInterceptor(tokenStore, baseUrl.toHttpUrl().host))
        .authenticator(TokenAuthenticator(tokenStore) { refresh -> refreshTokens(plainClient, baseUrl, gson, refresh) })
        .apply {
            if (BuildConfig.DEBUG) {
                // BASIC = method + URL + status only; never log bodies (tokens, photos).
                addInterceptor(HttpLoggingInterceptor().setLevel(HttpLoggingInterceptor.Level.BASIC))
            }
        }
        .build()

    val api: ApiService = Retrofit.Builder()
        .baseUrl(baseUrl)
        .client(okHttp)
        .addConverterFactory(GsonConverterFactory.create(gson))
        .build()
        .create(ApiService::class.java)

    /** Report photos are private endpoints, so images load through the authenticated client. */
    val imageLoader: ImageLoader = ImageLoader.Builder(appContext)
        .okHttpClient(okHttp)
        .crossfade(true)
        .build()

    val session = Session(api, tokenStore)
    val pendingReports = PendingReportStore(appContext, gson)

    /** Last-seen assignments, so the report form still works offline. */
    val assignmentCache = ConcurrentHashMap<Long, AssignmentDto>()
}

class Session(private val api: ApiService, private val store: TokenStore) {
    /** Returns the user's role on success. Admin accounts are web-only. */
    suspend fun login(email: String, password: String): Result<String> =
        safeApi { api.login(LoginRequest(email.trim().lowercase(), password)) }.mapCatching { res ->
            if (res.user.role == "admin") {
                throw ApiException("Akun admin hanya bisa dipakai di panel web.", "admin_web_only", null)
            }
            store.save(res.access, res.refresh)
            store.role = res.user.role
            res.user.role
        }

    suspend fun logout() {
        store.refresh?.let { refresh -> safeApi { api.logout(RefreshRequest(refresh)) } }
        store.clear()
    }
}
