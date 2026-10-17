package id.surveymandiri.app.ui

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import coil.compose.AsyncImage
import id.surveymandiri.app.data.AppContainer
import id.surveymandiri.app.data.CreateRequestBody
import id.surveymandiri.app.data.PricingRateDto
import id.surveymandiri.app.data.RejectBody
import id.surveymandiri.app.data.ReportDto
import id.surveymandiri.app.data.SurveyRequestDto
import id.surveymandiri.app.data.questions
import id.surveymandiri.app.data.safeApi
import id.surveymandiri.app.data.stringField
import id.surveymandiri.app.util.Geo
import id.surveymandiri.app.util.GeoFix
import kotlinx.coroutines.launch
import java.time.LocalDate

// ---- Home: my requests -----------------------------------------------------------------------
class ClientHomeViewModel(private val c: AppContainer) : ViewModel() {
    var items by mutableStateOf<List<SurveyRequestDto>?>(null)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun load() {
        loading = true
        viewModelScope.launch {
            safeApi { c.api.requests() }
                .onSuccess { items = it.results; error = null }
                .onFailure { error = it.message }
            loading = false
        }
    }
}

@Composable
fun ClientHomeScreen(onCreate: () -> Unit, onOpen: (Long) -> Unit, onLogout: () -> Unit) {
    val vm = appViewModel { ClientHomeViewModel(it) }
    LaunchedEffect(Unit) { vm.load() }
    AppScaffold(
        title = "Permintaan Survei",
        actions = {
            IconButton(onClick = vm::load) { Icon(Icons.Filled.Refresh, contentDescription = "Muat ulang") }
            IconButton(onClick = onLogout) { Icon(Icons.AutoMirrored.Filled.ExitToApp, contentDescription = "Keluar") }
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(onClick = onCreate, icon = { Icon(Icons.Filled.Add, null) }, text = { Text("Buat Survei") })
        },
    ) { padding ->
        val list = vm.items
        when {
            list == null && vm.loading -> CenterLoading(padding)
            list.isNullOrEmpty() -> EmptyState(padding, "Belum ada permintaan. Tap \"Buat Survei\" untuk mulai.", vm.error, vm::load)
            else -> LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = 96.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.fillMaxSize(),
            ) {
                if (vm.loading) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
                items(list, key = { it.id }) { req -> RequestCard(req) { onOpen(req.id) } }
            }
        }
    }
}

@Composable
private fun RequestCard(req: SurveyRequestDto, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(categoryLabel(req.category), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                StatusChip(req.status)
            }
            Text(req.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text("${req.claimedUnits}/${req.quantity} unit diambil  •  ${rupiah(req.totalPrice)}", style = MaterialTheme.typography.bodySmall)
            Text("Deadline ${req.deadline}", style = MaterialTheme.typography.bodySmall)
        }
    }
}

// ---- Create request --------------------------------------------------------------------------------
class CreateRequestViewModel(private val c: AppContainer) : ViewModel() {
    var pricing by mutableStateOf<List<PricingRateDto>>(emptyList())
        private set
    var category by mutableStateOf("leasing")
    var title by mutableStateOf("")
    var description by mutableStateOf("")
    var quantity by mutableStateOf("1")
    var cities by mutableStateOf("")
    var deadline by mutableStateOf(LocalDate.now().plusDays(14).toString())
    var address by mutableStateOf("")
    var fix by mutableStateOf<GeoFix?>(null)
        private set

    // Leasing
    var leasingPurpose by mutableStateOf("credit_worthiness")
    var applicantRef by mutableStateOf("")

    // Caleg
    var district by mutableStateOf("")
    var demographic by mutableStateOf("")

    // Product
    var productName by mutableStateOf("")
    var productCondition by mutableStateOf("new")
    var researchType by mutableStateOf("market_research")

    // Caleg + product
    var questionsText by mutableStateOf("")

    var locating by mutableStateOf(false)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    init {
        viewModelScope.launch {
            safeApi { c.api.pricing() }.onSuccess { pricing = it }.onFailure { error = it.message }
        }
    }

    val rate: PricingRateDto? get() = pricing.firstOrNull { it.category == category }

    fun estimate(): Long? {
        val q = quantity.toIntOrNull() ?: return null
        return rate?.let { it.unitPrice * q }
    }

    fun selectCategory(value: String) {
        category = value
        rate?.let { r ->
            val q = quantity.toIntOrNull() ?: 0
            if (q < r.minUnits) quantity = r.minUnits.toString()
        }
    }

    fun captureLocation(context: Context) {
        locating = true
        viewModelScope.launch {
            runCatching { Geo.currentFix(context.applicationContext) }
                .onSuccess {
                    fix = it
                    if (cities.isBlank() && it.city.isNotBlank()) cities = it.city
                }
                .onFailure { error = it.message }
            locating = false
        }
    }

    private fun questions(): List<String> = questionsText.lines().map { it.trim() }.filter { it.isNotEmpty() }

    private fun details(): Map<String, Any> = when (category) {
        "leasing" -> mapOf("purpose" to leasingPurpose, "applicant_ref" to applicantRef.trim())
        "caleg" -> mapOf("electoral_district" to district.trim(), "target_demographic" to demographic.trim(), "questions" to questions())
        else -> mapOf(
            "product_name" to productName.trim(),
            "condition" to productCondition,
            "research_type" to researchType,
            "questions" to questions(),
        )
    }

    fun submit(onCreated: (Long) -> Unit) {
        val qty = quantity.toIntOrNull()
        val targetCities = cities.split(",").map { it.trim() }.filter { it.isNotEmpty() }
        val r = rate
        error = when {
            title.isBlank() || description.isBlank() -> "Judul dan deskripsi wajib diisi."
            qty == null || qty < 1 -> "Jumlah unit tidak valid."
            r != null && (qty < r.minUnits || qty > r.maxUnits) -> "Jumlah unit ${categoryLabel(category)} harus ${r.minUnits}–${r.maxUnits}."
            targetCities.isEmpty() -> "Isi minimal satu kota target."
            category == "leasing" && (fix == null || address.isBlank()) -> "Survei leasing butuh alamat dan titik lokasi."
            category == "leasing" && applicantRef.isBlank() -> "Isi nomor referensi aplikasi."
            category == "caleg" && (district.isBlank() || questions().isEmpty()) -> "Isi dapil dan minimal satu pertanyaan."
            category == "product" && productName.isBlank() -> "Isi nama produk."
            else -> null
        }
        if (error != null || qty == null) return

        loading = true
        viewModelScope.launch {
            val body = CreateRequestBody(
                category = category,
                title = title.trim(),
                description = description.trim(),
                details = details(),
                quantity = qty,
                targetCities = targetCities,
                address = address.trim(),
                latitude = fix?.latitude,
                longitude = fix?.longitude,
                deadline = deadline.trim(),
            )
            safeApi { c.api.createRequest(body) }
                .onSuccess { onCreated(it.id) }
                .onFailure { error = it.message }
            loading = false
        }
    }
}

@Composable
fun CreateRequestScreen(onBack: () -> Unit, onCreated: (Long) -> Unit) {
    val vm = appViewModel { CreateRequestViewModel(it) }
    val context = LocalContext.current
    val requestLocation = rememberLocationRequest { vm.captureLocation(context) }

    AppScaffold(title = "Buat Permintaan Survei", onBack = onBack) { padding ->
        ScrollBody(padding) {
            Text("Kategori", style = MaterialTheme.typography.bodyMedium)
            ChoiceChips(listOf("leasing" to "Leasing", "caleg" to "Caleg", "product" to "Produk"), vm.category, vm::selectCategory)
            vm.rate?.let { InfoText("Tarif: ${rupiah(it.unitPrice)} per ${it.unitLabel} (min. ${it.minUnits})") }

            TextInput(vm.title, { vm.title = it }, "Judul")
            TextInput(vm.description, { vm.description = it }, "Deskripsi kebutuhan", singleLine = false, minLines = 3)

            when (vm.category) {
                "leasing" -> {
                    Text("Tujuan survei", style = MaterialTheme.typography.bodyMedium)
                    ChoiceChips(
                        listOf("credit_worthiness" to "Kelayakan kredit", "business_location" to "Lokasi usaha", "customer_verification" to "Verifikasi nasabah"),
                        vm.leasingPurpose,
                    ) { vm.leasingPurpose = it }
                    TextInput(vm.applicantRef, { vm.applicantRef = it }, "No. referensi aplikasi (bukan nama)")
                    TextInput(vm.address, { vm.address = it }, "Alamat yang disurvei", singleLine = false, minLines = 2)
                    LocationField("Titik lokasi (berdiri di lokasi / dekat alamat)", vm.fix, vm.locating, requestLocation)
                }
                "caleg" -> {
                    TextInput(vm.district, { vm.district = it }, "Daerah pemilihan (dapil)")
                    TextInput(vm.demographic, { vm.demographic = it }, "Target responden (opsional)")
                    TextInput(vm.questionsText, { vm.questionsText = it }, "Pertanyaan (satu per baris)", singleLine = false, minLines = 3)
                }
                else -> {
                    TextInput(vm.productName, { vm.productName = it }, "Nama produk")
                    ChoiceChips(listOf("new" to "Produk baru", "used" to "Produk bekas"), vm.productCondition) { vm.productCondition = it }
                    ChoiceChips(listOf("market_research" to "Riset pasar", "feedback" to "Feedback"), vm.researchType) { vm.researchType = it }
                    TextInput(vm.questionsText, { vm.questionsText = it }, "Pertanyaan (opsional, satu per baris)", singleLine = false, minLines = 3)
                }
            }

            TextInput(vm.quantity, { vm.quantity = it.filter(Char::isDigit).take(5) }, "Jumlah unit (${vm.rate?.unitLabel ?: "unit"})", keyboardType = KeyboardType.Number)
            TextInput(vm.cities, { vm.cities = it }, "Kota target (pisahkan dengan koma)", supporting = "Contoh: Sukabumi, Kabupaten Sukabumi")
            TextInput(vm.deadline, { vm.deadline = it }, "Deadline (YYYY-MM-DD)")
            ChoiceChips(
                listOf("7" to "+7 hari", "14" to "+14 hari", "30" to "+30 hari"),
                selected = "",
            ) { days -> vm.deadline = LocalDate.now().plusDays(days.toLong()).toString() }

            HorizontalDivider()
            vm.estimate()?.let { total ->
                LabeledValue("Estimasi total", rupiah(total))
                InfoText("Harga final dikunci saat permintaan dibuat. Anda menyetujui harga dulu sebelum membayar.")
            }
            vm.error?.let { ErrorText(it) }
            BusyButton("Buat Permintaan", vm.loading) { vm.submit(onCreated) }
        }
    }
}

// ---- Request detail ------------------------------------------------------------------------------------
class RequestDetailViewModel(private val c: AppContainer, private val id: Long) : ViewModel() {
    var request by mutableStateOf<SurveyRequestDto?>(null)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun load() {
        loading = true
        viewModelScope.launch {
            safeApi { c.api.request(id) }.onSuccess { request = it; error = null }.onFailure { error = it.message }
            loading = false
        }
    }

    fun act(action: String, onMessage: (String) -> Unit) {
        loading = true
        viewModelScope.launch {
            val result = safeApi {
                when (action) {
                    "approve" -> c.api.approveQuote(id)
                    "pay" -> c.api.pay(id)
                    "cancel" -> c.api.cancel(id)
                    else -> c.api.complete(id)
                }
            }
            result.onSuccess {
                request = it
                onMessage(
                    when (action) {
                        "approve" -> "Harga disetujui. Lanjutkan pembayaran."
                        "pay" -> "Pembayaran diterima. Job di-broadcast ke surveyor."
                        "cancel" -> "Permintaan dibatalkan."
                        else -> "Survei selesai. Dana dicairkan ke surveyor."
                    },
                )
            }.onFailure { onMessage(it.message ?: "Gagal.") }
            loading = false
        }
    }
}

@Composable
fun RequestDetailScreen(id: Long, onBack: () -> Unit, onReports: () -> Unit) {
    val vm = appViewModel(key = "request-$id") { RequestDetailViewModel(it, id) }
    val context = LocalContext.current
    var confirm by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(id) { vm.load() }

    AppScaffold(
        title = "Detail Permintaan",
        onBack = onBack,
        actions = { IconButton(onClick = vm::load) { Icon(Icons.Filled.Refresh, contentDescription = "Muat ulang") } },
    ) { padding ->
        val req = vm.request
        if (req == null) {
            if (vm.loading) CenterLoading(padding) else EmptyState(padding, "", vm.error, vm::load)
            return@AppScaffold
        }
        ScrollBody(padding) {
            if (vm.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(categoryLabel(req.category), color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge)
                StatusChip(req.status)
            }
            Text(req.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
            req.description?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }

            HorizontalDivider()
            SectionTitle("Harga")
            LabeledValue("Harga per unit", rupiah(req.unitPrice))
            LabeledValue("Jumlah unit", req.quantity.toString())
            LabeledValue("Total", rupiah(req.totalPrice))
            req.escrowStatus?.let { LabeledValue("Escrow", statusLabel(it)) }

            HorizontalDivider()
            SectionTitle("Detail")
            LabeledValue("Kota target", req.targetCities.orEmpty().joinToString(", "))
            LabeledValue("Deadline", req.deadline)
            if (!req.address.isNullOrBlank()) LabeledValue("Alamat", req.address)
            req.details.stringField("electoral_district")?.let { LabeledValue("Dapil", it) }
            req.details.stringField("product_name")?.let { LabeledValue("Produk", it) }
            req.details.stringField("applicant_ref")?.let { LabeledValue("Ref. aplikasi", it) }
            req.details.questions().takeIf { it.isNotEmpty() }?.let { qs ->
                Text("Pertanyaan:", style = MaterialTheme.typography.bodyMedium)
                qs.forEachIndexed { i, q -> Text("${i + 1}. $q", style = MaterialTheme.typography.bodySmall) }
            }

            HorizontalDivider()
            SectionTitle("Progres")
            LinearProgressIndicator(
                progress = { if (req.quantity == 0) 0f else req.claimedUnits.toFloat() / req.quantity },
                modifier = Modifier.fillMaxWidth(),
            )
            Text("${req.claimedUnits} dari ${req.quantity} unit sudah diambil surveyor", style = MaterialTheme.typography.bodySmall)
            req.assignments.orEmpty().forEach { a ->
                LabeledValue("${a.surveyorName ?: "Surveyor"} (${statusLabel(a.status)})", "${a.reportsSubmitted}/${a.units} laporan")
            }

            HorizontalDivider()
            when (req.status) {
                "quoted" -> {
                    InfoText("Periksa harga di atas. Setelah disetujui, Anda diminta membayar ke escrow.")
                    BusyButton("Setujui Harga", vm.loading) { confirm = "approve" }
                }
                "awaiting_payment" -> {
                    InfoText("Dana ditahan platform (escrow) dan baru dicairkan ke surveyor setelah Anda menyetujui hasil survei.")
                    BusyButton("Bayar ${rupiah(req.totalPrice)} (Demo)", vm.loading) { confirm = "pay" }
                }
                "open" -> InfoText("Job sedang ditawarkan ke surveyor terverifikasi di area target.")
                "assigned" -> InfoText("Semua unit sudah diambil. Laporan akan masuk satu per satu.")
                "in_review" -> {
                    InfoText("Semua laporan sudah masuk. Cek laporan, tolak yang tidak sesuai, lalu selesaikan.")
                    BusyButton("Setujui Semua & Selesaikan", vm.loading) { confirm = "complete" }
                }
            }
            if (req.assignments.orEmpty().any { it.reportsSubmitted > 0 } || req.status in setOf("in_review", "completed")) {
                OutlinedButton(onClick = onReports, modifier = Modifier.fillMaxWidth()) { Text("Lihat Laporan") }
            }
            if (req.status in setOf("quoted", "awaiting_payment", "open") && req.claimedUnits == 0) {
                TextButton(onClick = { confirm = "cancel" }, modifier = Modifier.fillMaxWidth()) { Text("Batalkan Permintaan") }
            }
        }
    }

    confirm?.let { action ->
        val (title, text) = when (action) {
            "approve" -> "Setujui harga?" to "Total ${rupiah(vm.request?.totalPrice ?: 0)} akan dikunci untuk permintaan ini."
            "pay" -> "Bayar sekarang?" to "Mode demo: pembayaran langsung dianggap lunas dan dana masuk escrow."
            "complete" -> "Selesaikan survei?" to "Semua laporan yang tersisa disetujui dan dana escrow dicairkan ke surveyor."
            else -> "Batalkan permintaan?" to "Jika sudah dibayar, dana escrow dikembalikan."
        }
        AlertDialog(
            onDismissRequest = { confirm = null },
            title = { Text(title) },
            text = { Text(text) },
            confirmButton = {
                TextButton(onClick = {
                    confirm = null
                    vm.act(action) { toast(context, it) }
                }) { Text("Ya") }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("Batal") } },
        )
    }
}

// ---- Reports (client review) -------------------------------------------------------------------------------
class RequestReportsViewModel(private val c: AppContainer, private val requestId: Long) : ViewModel() {
    var reports by mutableStateOf<List<ReportDto>?>(null)
        private set
    var canReject by mutableStateOf(false)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun load() {
        loading = true
        viewModelScope.launch {
            val all = mutableListOf<ReportDto>()
            var page = 1
            var failure: Throwable? = null
            while (page <= 20) {
                val result = safeApi { c.api.requestReports(requestId, page) }
                val data = result.getOrNull()
                if (data == null) {
                    failure = result.exceptionOrNull()
                    break
                }
                all += data.results
                if (data.next == null) break
                page++
            }
            safeApi { c.api.request(requestId) }.onSuccess { canReject = it.status in setOf("open", "assigned", "in_review") }
            if (failure != null && all.isEmpty()) error = failure.message else reports = all
            loading = false
        }
    }

    fun reject(reportId: Long, reason: String, onMessage: (String) -> Unit) {
        viewModelScope.launch {
            safeApi { c.api.rejectReport(reportId, RejectBody(reason)) }
                .onSuccess { onMessage("Laporan ditolak. Surveyor akan mengulang unit ini."); load() }
                .onFailure { onMessage(it.message ?: "Gagal.") }
        }
    }
}

@Composable
fun RequestReportsScreen(requestId: Long, onBack: () -> Unit) {
    val vm = appViewModel(key = "reports-$requestId") { RequestReportsViewModel(it, requestId) }
    val context = LocalContext.current
    val container = appContainer()
    var rejecting by remember { mutableStateOf<ReportDto?>(null) }
    var reason by remember { mutableStateOf("") }
    LaunchedEffect(requestId) { vm.load() }

    AppScaffold(
        title = "Laporan Survei",
        onBack = onBack,
        actions = { IconButton(onClick = vm::load) { Icon(Icons.Filled.Refresh, contentDescription = "Muat ulang") } },
    ) { padding ->
        val reports = vm.reports
        when {
            reports == null && vm.loading -> CenterLoading(padding)
            reports.isNullOrEmpty() -> EmptyState(padding, "Belum ada laporan.", vm.error, vm::load)
            else -> LazyColumn(
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = padding.calculateTopPadding() + 8.dp, bottom = 32.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item {
                    val flagged = reports.count { !it.flags.isNullOrEmpty() }
                    InfoText("${reports.size} laporan  •  $flagged ditandai mencurigakan")
                }
                items(reports, key = { it.id }) { report ->
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            AsyncImage(
                                model = report.photoUrl,
                                imageLoader = container.imageLoader,
                                contentDescription = "Foto laporan",
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.fillMaxWidth().height(200.dp).clip(RoundedCornerShape(8.dp)),
                            )
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                Text(report.respondentLabel?.ifBlank { null } ?: "Laporan #${report.id}", fontWeight = FontWeight.SemiBold)
                                StatusChip(report.status)
                            }
                            report.flags.orEmpty().forEach { FlagChip(it) }
                            InfoText("${report.surveyorName ?: "Surveyor"}  •  ${shortDateTime(report.capturedAt)}  •  ${report.city.orEmpty()}")
                            InfoText("GPS ${"%.5f".format(report.latitude)}, ${"%.5f".format(report.longitude)} (±${report.gpsAccuracyM.toInt()} m)")
                            report.answers?.entrySet()?.forEach { (q, a) ->
                                Text("$q: ${runCatching { a.asString }.getOrDefault(a.toString())}", style = MaterialTheme.typography.bodySmall)
                            }
                            if (!report.notes.isNullOrBlank()) Text("Catatan: ${report.notes}", style = MaterialTheme.typography.bodySmall)
                            if (!report.rejectionReason.isNullOrBlank()) ErrorText("Alasan ditolak: ${report.rejectionReason}")
                            if (vm.canReject && report.status == "submitted") {
                                TextButton(onClick = { rejecting = report; reason = "" }) { Text("Tolak laporan ini") }
                            }
                        }
                    }
                }
            }
        }
    }

    rejecting?.let { report ->
        AlertDialog(
            onDismissRequest = { rejecting = null },
            title = { Text("Tolak laporan?") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Surveyor harus mengulang unit ini.")
                    TextInput(reason, { reason = it }, "Alasan (wajib)")
                }
            },
            confirmButton = {
                TextButton(enabled = reason.isNotBlank(), onClick = {
                    rejecting = null
                    vm.reject(report.id, reason.trim()) { toast(context, it) }
                }) { Text("Tolak") }
            },
            dismissButton = { TextButton(onClick = { rejecting = null }) { Text("Batal") } },
        )
    }
}

/** Shared logout action for both roles. */
@Composable
fun rememberLogout(onLoggedOut: () -> Unit): () -> Unit {
    val container = appContainer()
    val scope = rememberCoroutineScope()
    return {
        scope.launch {
            container.session.logout()
            onLoggedOut()
        }
    }
}
