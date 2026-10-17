package id.surveymandiri.app.data

import android.content.Context
import com.google.gson.Gson
import com.google.gson.JsonElement
import com.google.gson.JsonParser
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.Route
import retrofit2.HttpException
import java.io.IOException

/** JWT pair kept in app-private SharedPreferences (sandboxed per app). */
class TokenStore(context: Context) {
    private val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)
    private val _sessionExpired = MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    /** Emits when the refresh token is rejected: UI must go back to login. */
    val sessionExpired: SharedFlow<Unit> = _sessionExpired

    val access: String? get() = prefs.getString(KEY_ACCESS, null)
    val refresh: String? get() = prefs.getString(KEY_REFRESH, null)

    var role: String?
        get() = prefs.getString(KEY_ROLE, null)
        set(value) {
            prefs.edit().putString(KEY_ROLE, value).commit()
        }

    @Synchronized
    fun save(access: String, refresh: String?) {
        val editor = prefs.edit()
        editor.putString(KEY_ACCESS, access)
        if (refresh != null) editor.putString(KEY_REFRESH, refresh)
        editor.commit()
    }

    @Synchronized
    fun clear() {
        prefs.edit().clear().commit()
    }

    fun expire() {
        clear()
        _sessionExpired.tryEmit(Unit)
    }

    private companion object {
        const val KEY_ACCESS = "access"
        const val KEY_REFRESH = "refresh"
        const val KEY_ROLE = "role"
    }
}

/** Adds the access token, only for our own backend and never on login/register/refresh. */
class AuthInterceptor(private val store: TokenStore, private val apiHost: String) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val path = request.url.encodedPath
        val isPublicAuth = path.startsWith("/api/v1/auth/") && !path.startsWith("/api/v1/auth/logout")
        val token = store.access
        if (token == null || isPublicAuth || request.url.host != apiHost || request.header("Authorization") != null) {
            return chain.proceed(request)
        }
        return chain.proceed(request.newBuilder().header("Authorization", "Bearer $token").build())
    }
}

/**
 * On 401, swaps the refresh token for a new pair and retries once.
 * The backend rotates refresh tokens, so concurrent 401s are serialized.
 */
class TokenAuthenticator(
    private val store: TokenStore,
    private val refresher: (String) -> TokenPair?,
) : Authenticator {
    override fun authenticate(route: Route?, response: Response): Request? {
        val sent = response.request.header("Authorization") ?: return null
        if (priorResponses(response) >= 2) return null
        synchronized(this) {
            val current = store.access
            if (current != null && "Bearer $current" != sent) {
                // Another request already refreshed while we waited.
                return response.request.newBuilder().header("Authorization", "Bearer $current").build()
            }
            val refresh = store.refresh
            if (refresh == null) {
                store.expire()
                return null
            }
            val pair = refresher(refresh) // IOException propagates: offline is not a logout.
            if (pair == null) {
                store.expire()
                return null
            }
            store.save(pair.access, pair.refresh)
            return response.request.newBuilder().header("Authorization", "Bearer ${pair.access}").build()
        }
    }

    private fun priorResponses(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}

/** Synchronous refresh used by the authenticator. Null = refresh token rejected. */
fun refreshTokens(client: OkHttpClient, baseUrl: String, gson: Gson, refresh: String): TokenPair? {
    val body = gson.toJson(RefreshRequest(refresh)).toRequestBody("application/json".toMediaType())
    val request = Request.Builder().url(baseUrl + "api/v1/auth/refresh").post(body).build()
    client.newCall(request).execute().use { response ->
        if (!response.isSuccessful) return null
        val text = response.body?.string() ?: return null
        return gson.fromJson(text, TokenPair::class.java)
    }
}

// ---- Errors ------------------------------------------------------------------------------------

class ApiException(message: String, val code: String?, val httpStatus: Int?) : Exception(message)

/** Parses the backend envelope {"error": {"code", "message", "details"}} into a readable message. */
fun parseErrorBody(body: String?, httpStatus: Int): ApiException {
    return try {
        val error = JsonParser.parseString(body ?: "").asJsonObject.getAsJsonObject("error")
        val code = error.get("code")?.takeIf { !it.isJsonNull }?.asString
        var message = error.get("message")?.takeIf { !it.isJsonNull }?.asString ?: "Terjadi kesalahan ($httpStatus)."
        if (code == "validation_error") {
            firstDetail(error.get("details"))?.let { message = it }
        }
        ApiException(message, code, httpStatus)
    } catch (e: Exception) {
        ApiException("Server error ($httpStatus).", null, httpStatus)
    }
}

private fun firstDetail(element: JsonElement?): String? {
    if (element == null || element.isJsonNull) return null
    if (element.isJsonPrimitive) return element.asString
    if (element.isJsonArray) {
        for (item in element.asJsonArray) {
            val found = firstDetail(item)
            if (found != null) return found
        }
        return null
    }
    for ((key, value) in element.asJsonObject.entrySet()) {
        val found = firstDetail(value) ?: continue
        return if (key == "non_field_errors" || key == "detail") found else "$key: $found"
    }
    return null
}

/** Runs an API call and maps every failure to an [ApiException] with a user-facing message. */
suspend fun <T> safeApi(block: suspend () -> T): Result<T> {
    return try {
        Result.success(block())
    } catch (e: CancellationException) {
        throw e
    } catch (e: HttpException) {
        Result.failure(parseErrorBody(e.response()?.errorBody()?.string(), e.code()))
    } catch (e: IOException) {
        Result.failure(ApiException("Tidak bisa terhubung ke server. Cek koneksi internet.", "network", null))
    } catch (e: ApiException) {
        Result.failure(e)
    } catch (e: Exception) {
        Result.failure(ApiException(e.message ?: "Terjadi kesalahan.", null, null))
    }
}
