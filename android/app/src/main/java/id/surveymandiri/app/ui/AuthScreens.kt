package id.surveymandiri.app.ui

import android.content.Context
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import id.surveymandiri.app.BuildConfig
import id.surveymandiri.app.data.ApiException
import id.surveymandiri.app.data.AppContainer
import id.surveymandiri.app.data.ClientRegisterRequest
import id.surveymandiri.app.data.safeApi
import id.surveymandiri.app.util.Geo
import id.surveymandiri.app.util.GeoFix
import id.surveymandiri.app.util.Media
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.util.Locale

fun homeRoute(role: String?): String = when (role) {
    "client" -> Routes.CLIENT_HOME
    "surveyor" -> Routes.SURVEYOR_HOME
    else -> Routes.LOGIN
}

// ---- Splash: decide where to go ----------------------------------------------------------------
@Composable
fun SplashScreen(onRoute: (String) -> Unit) {
    val container = appContainer()
    LaunchedEffect(Unit) {
        val route = if (container.tokenStore.access == null) {
            Routes.LOGIN
        } else {
            safeApi { container.api.me() }.fold(
                onSuccess = { user ->
                    container.tokenStore.role = user.role
                    homeRoute(user.role)
                },
                // Offline: trust the stored role so surveyors can still work in the field.
                onFailure = { e -> if ((e as? ApiException)?.httpStatus == 401) Routes.LOGIN else homeRoute(container.tokenStore.role) },
            )
        }
        onRoute(route)
    }
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
}

// ---- Login -------------------------------------------------------------------------------------
class LoginViewModel(private val c: AppContainer) : ViewModel() {
    var email by mutableStateOf("")
    var password by mutableStateOf("")
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun login(onSuccess: (String) -> Unit) {
        if (email.isBlank() || password.isBlank()) {
            error = "Email dan password wajib diisi."
            return
        }
        loading = true
        error = null
        viewModelScope.launch {
            val result = c.session.login(email, password)
            loading = false
            result.onSuccess(onSuccess).onFailure { error = it.message }
        }
    }
}

@Composable
fun LoginScreen(onLoggedIn: (String) -> Unit, onRegisterClient: () -> Unit, onRegisterSurveyor: () -> Unit) {
    val vm = appViewModel { LoginViewModel(it) }
    AppScaffold(title = "Survey Mandiri") { padding ->
        ScrollBody(padding) {
            Text("Masuk", style = MaterialTheme.typography.headlineSmall)
            InfoText("Marketplace survei lapangan: client memesan survei, surveyor terverifikasi mengerjakan, dana aman di escrow.")
            TextInput(vm.email, { vm.email = it }, "Email", keyboardType = KeyboardType.Email)
            PasswordInput(vm.password, { vm.password = it })
            vm.error?.let { ErrorText(it) }
            BusyButton("Masuk", vm.loading) { vm.login(onLoggedIn) }
            HorizontalDivider()
            Text("Belum punya akun?", style = MaterialTheme.typography.bodyMedium)
            OutlinedButton(onClick = onRegisterClient, modifier = Modifier.fillMaxWidth()) { Text("Daftar sebagai Client") }
            OutlinedButton(onClick = onRegisterSurveyor, modifier = Modifier.fillMaxWidth()) { Text("Daftar sebagai Surveyor") }
            InfoText("Server: ${BuildConfig.API_BASE_URL}  •  v${BuildConfig.VERSION_NAME}")
        }
    }
}

// ---- Register client -----------------------------------------------------------------------------
class RegisterClientViewModel(private val c: AppContainer) : ViewModel() {
    var email by mutableStateOf("")
    var password by mutableStateOf("")
    var phone by mutableStateOf("")
    var clientType by mutableStateOf("leasing")
    var organization by mutableStateOf("")
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun submit(onDone: (String) -> Unit) {
        error = when {
            email.isBlank() || organization.isBlank() || phone.isBlank() -> "Semua kolom wajib diisi."
            password.length < 8 -> "Password minimal 8 karakter."
            else -> null
        }
        if (error != null) return
        loading = true
        viewModelScope.launch {
            val body = ClientRegisterRequest(email.trim().lowercase(), password, phone.trim(), clientType, organization.trim())
            val result = safeApi { c.api.registerClient(body) }.fold(
                onSuccess = { c.session.login(email, password) },
                onFailure = { Result.failure(it) },
            )
            loading = false
            result.onSuccess(onDone).onFailure { error = it.message }
        }
    }
}

@Composable
fun RegisterClientScreen(onBack: () -> Unit, onDone: (String) -> Unit) {
    val vm = appViewModel { RegisterClientViewModel(it) }
    AppScaffold(title = "Daftar Client", onBack = onBack) { padding ->
        ScrollBody(padding) {
            InfoText("Untuk leasing, tim caleg, atau brand yang butuh survei lapangan.")
            Text("Jenis client", style = MaterialTheme.typography.bodyMedium)
            ChoiceChips(
                listOf("leasing" to "Leasing", "caleg" to "Caleg", "product" to "Produk", "other" to "Lainnya"),
                vm.clientType,
            ) { vm.clientType = it }
            TextInput(vm.organization, { vm.organization = it }, "Nama organisasi / perusahaan")
            TextInput(vm.email, { vm.email = it }, "Email", keyboardType = KeyboardType.Email)
            TextInput(vm.phone, { vm.phone = it }, "No. HP (08xx / +62xx)", keyboardType = KeyboardType.Phone)
            PasswordInput(vm.password, { vm.password = it }, "Password (min. 8 karakter)")
            vm.error?.let { ErrorText(it) }
            BusyButton("Daftar & Masuk", vm.loading) { vm.submit(onDone) }
        }
    }
}

// ---- Register surveyor -----------------------------------------------------------------------------
class RegisterSurveyorViewModel(private val c: AppContainer) : ViewModel() {
    var fullName by mutableStateOf("")
    var email by mutableStateOf("")
    var password by mutableStateOf("")
    var phone by mutableStateOf("")
    var nik by mutableStateOf("")
    var city by mutableStateOf("")
    var radiusKm by mutableStateOf("25")
    var fix by mutableStateOf<GeoFix?>(null)
        private set
    var idDocument by mutableStateOf<File?>(null)
        private set
    var selfie by mutableStateOf<File?>(null)
        private set
    var locating by mutableStateOf(false)
        private set
    var processingPhoto by mutableStateOf(false)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun captureLocation(context: Context) {
        locating = true
        viewModelScope.launch {
            runCatching { Geo.currentFix(context.applicationContext) }
                .onSuccess {
                    fix = it
                    if (city.isBlank()) city = it.city
                }
                .onFailure { error = it.message }
            locating = false
        }
    }

    fun onPhoto(kind: String, raw: File) {
        processingPhoto = true
        viewModelScope.launch {
            runCatching { Media.compress(raw, File(raw.parentFile, "${kind}_${System.currentTimeMillis()}.jpg")) }
                .onSuccess { if (kind == "ktp") idDocument = it else selfie = it }
                .onFailure { error = it.message }
            processingPhoto = false
        }
    }

    fun submit(onDone: (String) -> Unit) {
        val location = fix
        val ktp = idDocument
        val face = selfie
        error = when {
            fullName.isBlank() || email.isBlank() || phone.isBlank() || city.isBlank() -> "Lengkapi semua data."
            !Regex("^\\d{16}$").matches(nik.trim()) -> "NIK harus 16 digit."
            password.length < 8 -> "Password minimal 8 karakter."
            location == null -> "Ambil lokasi domisili dulu."
            ktp == null || face == null -> "Foto KTP dan selfie wajib."
            radiusKm.toIntOrNull()?.let { it in 1..300 } != true -> "Radius layanan 1–300 km."
            else -> null
        }
        if (error != null || location == null || ktp == null || face == null) return

        loading = true
        viewModelScope.launch {
            val fields = listOf(
                "email" to email.trim().lowercase(),
                "password" to password,
                "phone" to phone.trim(),
                "full_name" to fullName.trim(),
                "nik" to nik.trim(),
                "city" to city.trim(),
                "latitude" to String.format(Locale.US, "%.7f", location.latitude),
                "longitude" to String.format(Locale.US, "%.7f", location.longitude),
                "service_radius_km" to radiusKm.trim(),
            ).map { (name, value) -> MultipartBody.Part.createFormData(name, value) }
            val jpeg = "image/jpeg".toMediaType()
            val parts = fields +
                MultipartBody.Part.createFormData("id_document", ktp.name, ktp.asRequestBody(jpeg)) +
                MultipartBody.Part.createFormData("selfie", face.name, face.asRequestBody(jpeg))

            val result = safeApi { c.api.registerSurveyor(parts) }.fold(
                onSuccess = { c.session.login(email, password) },
                onFailure = { Result.failure(it) },
            )
            loading = false
            result.onSuccess(onDone).onFailure { error = it.message }
        }
    }
}

@Composable
fun RegisterSurveyorScreen(onBack: () -> Unit, onDone: (String) -> Unit) {
    val vm = appViewModel { RegisterSurveyorViewModel(it) }
    val context = LocalContext.current
    val shootKtp = rememberCamera { vm.onPhoto("ktp", it) }
    val shootSelfie = rememberCamera { vm.onPhoto("selfie", it) }
    val requestLocation = rememberLocationRequest { vm.captureLocation(context) }

    AppScaffold(title = "Daftar Surveyor", onBack = onBack) { padding ->
        ScrollBody(padding) {
            InfoText("Data KTP hanya dilihat admin untuk verifikasi. Setelah diverifikasi, job di sekitar lokasi Anda akan muncul.")
            TextInput(vm.fullName, { vm.fullName = it }, "Nama lengkap (sesuai KTP)")
            TextInput(vm.nik, { vm.nik = it.filter(Char::isDigit).take(16) }, "NIK (16 digit)", keyboardType = KeyboardType.Number, supporting = "Hanya 4 digit terakhir yang disimpan.")
            TextInput(vm.email, { vm.email = it }, "Email", keyboardType = KeyboardType.Email)
            TextInput(vm.phone, { vm.phone = it }, "No. HP", keyboardType = KeyboardType.Phone)
            PasswordInput(vm.password, { vm.password = it }, "Password (min. 8 karakter)")
            LocationField("Lokasi domisili", vm.fix, vm.locating, requestLocation)
            TextInput(vm.city, { vm.city = it }, "Kota / Kabupaten domisili")
            TextInput(vm.radiusKm, { vm.radiusKm = it.filter(Char::isDigit).take(3) }, "Radius layanan (km)", keyboardType = KeyboardType.Number)
            PhotoField("Foto KTP", vm.idDocument, vm.processingPhoto, shootKtp)
            PhotoField("Selfie memegang KTP", vm.selfie, vm.processingPhoto, shootSelfie)
            vm.error?.let { ErrorText(it) }
            BusyButton("Kirim Pendaftaran", vm.loading) { vm.submit(onDone) }
        }
    }
}
