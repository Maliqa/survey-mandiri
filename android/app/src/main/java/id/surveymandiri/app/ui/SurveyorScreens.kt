package id.surveymandiri.app.ui

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import id.surveymandiri.app.data.AcceptBody
import id.surveymandiri.app.data.AppContainer
import id.surveymandiri.app.data.AssignmentDto
import id.surveymandiri.app.data.JobDto
import id.surveymandiri.app.data.PayoutPage
import id.surveymandiri.app.data.PendingReport
import id.surveymandiri.app.data.ReportDto
import id.surveymandiri.app.data.UploadWorker
import id.surveymandiri.app.data.UserDto
import id.surveymandiri.app.data.questions
import id.surveymandiri.app.data.safeApi
import id.surveymandiri.app.data.stringField
import id.surveymandiri.app.util.Geo
import id.surveymandiri.app.util.GeoFix
import id.surveymandiri.app.util.Media
import kotlinx.coroutines.launch
import java.io.File
import java.time.OffsetDateTime
import java.util.Locale
import java.util.UUID

// ---- Home (tabs: jobs / tasks / wallet) -------------------------------------------------------------
class SurveyorHomeViewModel(private val c: AppContainer) : ViewModel() {
    var me by mutableStateOf<UserDto?>(null)
        private set
    var jobs by mutableStateOf<List<JobDto>?>(null)
        private set
    var assignments by mutableStateOf<List<AssignmentDto>?>(null)
        private set
    var payouts by mutableStateOf<PayoutPage?>(null)
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    val verificationStatus: String? get() = me?.surveyorProfile?.status

    fun refresh() {
        loading = true
        viewModelScope.launch {
            safeApi { c.api.me() }.onSuccess { me = it }.onFailure { error = it.message }
            if (me == null || verificationStatus == "verified") {
                safeApi { c.api.availableJobs() }.onSuccess { jobs = it.results; error = null }.onFailure { error = it.message }
                safeApi { c.api.assignments() }.onSuccess { page ->
                    assignments = page.results
                    page.results.forEach { c.assignmentCache[it.id] = it }
                }
                safeApi { c.api.payouts() }.onSuccess { payouts = it }
            }
            loading = false
        }
    }
}

@Composable
fun SurveyorHomeScreen(onJob: (Long) -> Unit, onAssignment: (Long) -> Unit, onLogout: () -> Unit) {
    val vm = appViewModel { SurveyorHomeViewModel(it) }
    var tab by rememberSaveable { mutableStateOf(0) }
    LaunchedEffect(Unit) { vm.refresh() }

    AppScaffold(
        title = when (tab) {
            0 -> "Job Tersedia"
            1 -> "Tugas Saya"
            else -> "Dompet"
        },
        actions = {
            IconButton(onClick = vm::refresh) { Icon(Icons.Filled.Refresh, contentDescription = "Muat ulang") }
            IconButton(onClick = onLogout) { Icon(Icons.AutoMirrored.Filled.ExitToApp, contentDescription = "Keluar") }
        },
        bottomBar = {
            NavigationBar {
                NavigationBarItem(selected = tab == 0, onClick = { tab = 0 }, icon = { Icon(Icons.Filled.Search, null) }, label = { Text("Job") })
                NavigationBarItem(selected = tab == 1, onClick = { tab = 1 }, icon = { Icon(Icons.Filled.CheckCircle, null) }, label = { Text("Tugas") })
                NavigationBarItem(selected = tab == 2, onClick = { tab = 2 }, icon = { Icon(Icons.Filled.AccountCircle, null) }, label = { Text("Dompet") })
            }
        },
    ) { padding ->
        val status = vm.verificationStatus
        if (status != null && status != "verified") {
            ScrollBody(padding) {
                SectionTitle("Akun belum aktif")
                StatusChip(status)
                Text(
                    when (status) {
                        "pending" -> "Data Anda sedang diverifikasi admin. Job akan muncul setelah akun terverifikasi."
                        "rejected" -> "Pendaftaran ditolak: ${vm.me?.surveyorProfile?.rejectionReason.orEmpty()}"
                        else -> "Akun ditangguhkan. Hubungi admin."
                    },
                )
                OutlinedButton(onClick = vm::refresh) { Text("Cek status lagi") }
            }
            return@AppScaffold
        }
        when (tab) {
            0 -> JobsTab(padding, vm, onJob)
            1 -> TasksTab(padding, vm, onAssignment)
            else -> WalletTab(padding, vm)
        }
    }
}

@Composable
private fun JobsTab(padding: PaddingValues, vm: SurveyorHomeViewModel, onJob: (Long) -> Unit) {
    val jobs = vm.jobs
    when {
        jobs == null && vm.loading -> CenterLoading(padding)
        jobs.isNullOrEmpty() -> EmptyState(padding, "Belum ada job di area Anda. Tarik ulang nanti.", vm.error, vm::refresh)
        else -> LazyColumn(
            contentPadding = PaddingValues(16.dp, padding.calculateTopPadding() + 8.dp, 16.dp, padding.calculateBottomPadding() + 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            items(jobs, key = { it.id }) { job ->
                Card(onClick = { onJob(job.id) }, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Text(categoryLabel(job.category), color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge)
                            Text("${rupiah(job.unitEarning)}/unit", fontWeight = FontWeight.SemiBold)
                        }
                        Text(job.title, style = MaterialTheme.typography.titleMedium)
                        InfoText(
                            listOfNotNull(
                                "Sisa ${job.remainingUnits} unit",
                                job.distanceKm?.let { String.format(Locale.US, "%.1f km", it) },
                                "Deadline ${job.deadline}",
                            ).joinToString("  •  "),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun TasksTab(padding: PaddingValues, vm: SurveyorHomeViewModel, onAssignment: (Long) -> Unit) {
    val container = appContainer()
    val outboxVersion by container.pendingReports.changes.collectAsState()
    val pending = remember(outboxVersion) { container.pendingReports.all().groupingBy { it.assignmentId }.eachCount() }
    val list = vm.assignments
    when {
        list == null && vm.loading -> CenterLoading(padding)
        list.isNullOrEmpty() -> EmptyState(padding, "Belum ada tugas. Ambil job di tab Job.", vm.error, vm::refresh)
        else -> LazyColumn(
            contentPadding = PaddingValues(16.dp, padding.calculateTopPadding() + 8.dp, 16.dp, padding.calculateBottomPadding() + 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            items(list, key = { it.id }) { a ->
                Card(onClick = { onAssignment(a.id) }, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Text(a.job.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                            StatusChip(a.status)
                        }
                        val waiting = pending[a.id] ?: 0
                        InfoText("${a.reportsSubmitted}/${a.units} laporan terkirim" + if (waiting > 0) "  •  $waiting menunggu upload" else "")
                    }
                }
            }
        }
    }
}

@Composable
private fun WalletTab(padding: PaddingValues, vm: SurveyorHomeViewModel) {
    val page = vm.payouts
    ScrollBody(padding) {
        SectionTitle("Pendapatan")
        LabeledValue("Menunggu transfer", rupiah(page?.totals?.get("pending") ?: 0))
        LabeledValue("Sudah ditransfer", rupiah(page?.totals?.get("paid") ?: 0))
        InfoText("Dana cair setelah client menyetujui hasil survei, sudah dipotong komisi platform.")
        HorizontalDivider()
        if (page == null || page.results.isEmpty()) {
            InfoText(if (vm.loading) "Memuat..." else "Belum ada pembayaran.")
        } else {
            page.results.forEach { p ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(p.requestTitle ?: "Survei", style = MaterialTheme.typography.bodyMedium)
                        InfoText("${p.units} unit  •  ${shortDateTime(p.createdAt)}")
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(rupiah(p.netAmount), fontWeight = FontWeight.SemiBold)
                        StatusChip(p.status)
                    }
                }
            }
        }
    }
}

// ---- Job detail + accept -----------------------------------------------------------------------------------
class JobDetailViewModel(private val c: AppContainer, private val id: Long) : ViewModel() {
    var job by mutableStateOf<JobDto?>(null)
        private set
    var units by mutableStateOf("1")
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun load() {
        loading = true
        viewModelScope.launch {
            safeApi { c.api.job(id) }.onSuccess { job = it; error = null }.onFailure { error = it.message }
            loading = false
        }
    }

    fun accept(onAccepted: (Long) -> Unit) {
        val n = units.toIntOrNull()
        val remaining = job?.remainingUnits ?: 0
        if (n == null || n < 1 || n > remaining) {
            error = "Jumlah unit harus 1–$remaining."
            return
        }
        loading = true
        viewModelScope.launch {
            safeApi { c.api.acceptJob(id, AcceptBody(n)) }
                .onSuccess {
                    c.assignmentCache[it.id] = it
                    onAccepted(it.id)
                }
                .onFailure { error = it.message }
            loading = false
        }
    }
}

@Composable
fun JobDetailScreen(id: Long, onBack: () -> Unit, onAccepted: (Long) -> Unit) {
    val vm = appViewModel(key = "job-$id") { JobDetailViewModel(it, id) }
    val context = LocalContext.current
    LaunchedEffect(id) { vm.load() }
    AppScaffold(title = "Detail Job", onBack = onBack) { padding ->
        val job = vm.job
        if (job == null) {
            if (vm.loading) CenterLoading(padding) else EmptyState(padding, "", vm.error, vm::load)
            return@AppScaffold
        }
        ScrollBody(padding) {
            JobInfo(job, context)
            HorizontalDivider()
            if (job.status == "open" && job.remainingUnits > 0) {
                TextInput(vm.units, { vm.units = it.filter(Char::isDigit).take(4) }, "Ambil berapa unit? (sisa ${job.remainingUnits})", keyboardType = KeyboardType.Number)
                vm.units.toIntOrNull()?.let { LabeledValue("Perkiraan pendapatan", rupiah(job.unitEarning * it)) }
                vm.error?.let { ErrorText(it) }
                BusyButton("Ambil Job", vm.loading) { vm.accept(onAccepted) }
            } else {
                InfoText("Job ini sudah tidak menerima surveyor baru.")
            }
        }
    }
}

@Composable
private fun JobInfo(job: JobDto, context: Context) {
    Text(categoryLabel(job.category), color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelLarge)
    Text(job.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
    job.description?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
    LabeledValue("Pendapatan per unit", rupiah(job.unitEarning))
    LabeledValue("Sisa unit", "${job.remainingUnits} dari ${job.quantity}")
    LabeledValue("Deadline", job.deadline)
    LabeledValue("Kota", job.targetCities.orEmpty().joinToString(", "))
    job.distanceKm?.let { LabeledValue("Jarak dari Anda", String.format(Locale.US, "%.1f km", it)) }
    job.details.stringField("electoral_district")?.let { LabeledValue("Dapil", it) }
    job.details.stringField("product_name")?.let { LabeledValue("Produk", it) }
    if (!job.address.isNullOrBlank()) LabeledValue("Alamat", job.address)
    val lat = job.latitude
    val lon = job.longitude
    if (lat != null && lon != null) {
        OutlinedButton(onClick = { openMap(context, lat, lon) }) { Text("Buka di Maps") }
    }
    job.details.questions().takeIf { it.isNotEmpty() }?.let { qs ->
        Text("Pertanyaan untuk responden:", style = MaterialTheme.typography.bodyMedium)
        qs.forEachIndexed { i, q -> Text("${i + 1}. $q", style = MaterialTheme.typography.bodySmall) }
    }
}

private fun openMap(context: Context, lat: Double, lon: Double) {
    val uri = Uri.parse("geo:$lat,$lon?q=$lat,$lon")
    try {
        context.startActivity(Intent(Intent.ACTION_VIEW, uri))
    } catch (e: ActivityNotFoundException) {
        toast(context, "Tidak ada aplikasi peta di HP ini.")
    }
}

// ---- Assignment detail ---------------------------------------------------------------------------------------
class AssignmentViewModel(private val c: AppContainer, private val id: Long) : ViewModel() {
    var assignment by mutableStateOf(c.assignmentCache[id])
        private set
    var reports by mutableStateOf<List<ReportDto>>(emptyList())
        private set
    var loading by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun load() {
        loading = true
        viewModelScope.launch {
            safeApi { c.api.assignment(id) }
                .onSuccess {
                    assignment = it
                    c.assignmentCache[id] = it
                    error = null
                }
                .onFailure { error = it.message }
            safeApi { c.api.assignmentReports(id) }.onSuccess { reports = it }
            loading = false
        }
    }

    fun withdraw(onDone: () -> Unit, onMessage: (String) -> Unit) {
        viewModelScope.launch {
            safeApi { c.api.withdraw(id) }
                .onSuccess { onMessage("Anda mundur dari job ini."); onDone() }
                .onFailure { onMessage(it.message ?: "Gagal.") }
        }
    }

    fun retryUploads(context: Context) {
        c.pendingReports.forAssignment(id).filter { it.failedPermanently }.forEach {
            c.pendingReports.save(it.copy(failedPermanently = false, lastError = null))
        }
        UploadWorker.enqueue(context.applicationContext)
    }

    fun discard(report: PendingReport) = c.pendingReports.remove(report)
}

@Composable
fun AssignmentScreen(id: Long, onBack: () -> Unit, onNewReport: () -> Unit) {
    val vm = appViewModel(key = "assignment-$id") { AssignmentViewModel(it, id) }
    val container = appContainer()
    val context = LocalContext.current
    val outboxVersion by container.pendingReports.changes.collectAsState()
    val pending = remember(outboxVersion) { container.pendingReports.forAssignment(id) }
    var confirmWithdraw by remember { mutableStateOf(false) }

    // Reload when an upload finishes so the server count stays in sync.
    LaunchedEffect(id, outboxVersion) { vm.load() }

    AppScaffold(
        title = "Tugas Survei",
        onBack = onBack,
        actions = { IconButton(onClick = vm::load) { Icon(Icons.Filled.Refresh, contentDescription = "Muat ulang") } },
    ) { padding ->
        val a = vm.assignment
        if (a == null) {
            if (vm.loading) CenterLoading(padding) else EmptyState(padding, "", vm.error, vm::load)
            return@AppScaffold
        }
        val sent = vm.reports.count { it.status != "rejected" }
        val done = sent + pending.size
        ScrollBody(padding) {
            if (vm.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
            JobInfo(a.job, context)
            HorizontalDivider()
            SectionTitle("Progres")
            LinearProgressIndicator(progress = { if (a.units == 0) 0f else done.toFloat() / a.units }, modifier = Modifier.fillMaxWidth())
            Text("$sent terkirim  •  ${pending.size} menunggu upload  •  target ${a.units} unit", style = MaterialTheme.typography.bodySmall)
            vm.error?.let { InfoText("Offline? Data terakhir ditampilkan. ($it)") }

            if (a.status == "active" && done < a.units) {
                BusyButton("Isi Laporan Baru", busy = false, onClick = onNewReport)
            } else if (a.status == "active") {
                InfoText("Semua unit sudah dilaporkan. Menunggu review client.")
            }

            if (pending.isNotEmpty()) {
                HorizontalDivider()
                SectionTitle("Menunggu upload")
                pending.forEach { p ->
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(p.respondentLabel.ifBlank { "Laporan" } + "  •  " + shortDateTime(p.capturedAt), style = MaterialTheme.typography.bodyMedium)
                        p.lastError?.let { if (p.failedPermanently) ErrorText(it) else InfoText(it) }
                        if (p.failedPermanently) {
                            TextButton(onClick = { vm.discard(p) }) { Text("Hapus laporan ini") }
                        }
                    }
                }
                OutlinedButton(onClick = { vm.retryUploads(context) }) { Text("Kirim ulang sekarang") }
            }

            if (vm.reports.isNotEmpty()) {
                HorizontalDivider()
                SectionTitle("Laporan terkirim")
                vm.reports.forEach { r ->
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Text(r.respondentLabel?.ifBlank { null } ?: "Laporan #${r.id}", style = MaterialTheme.typography.bodyMedium)
                            StatusChip(r.status)
                        }
                        r.flags.orEmpty().forEach { FlagChip(it) }
                        if (!r.rejectionReason.isNullOrBlank()) ErrorText("Ditolak: ${r.rejectionReason}. Silakan ulangi unit ini.")
                    }
                }
            }

            if (a.status == "active" && sent == 0 && pending.isEmpty()) {
                HorizontalDivider()
                TextButton(onClick = { confirmWithdraw = true }) { Text("Mundur dari job ini") }
            }
        }
    }

    if (confirmWithdraw) {
        AlertDialog(
            onDismissRequest = { confirmWithdraw = false },
            title = { Text("Mundur dari job?") },
            text = { Text("Unit yang Anda ambil akan dibuka lagi untuk surveyor lain.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmWithdraw = false
                    vm.withdraw(onDone = onBack) { toast(context, it) }
                }) { Text("Ya, mundur") }
            },
            dismissButton = { TextButton(onClick = { confirmWithdraw = false }) { Text("Batal") } },
        )
    }
}

// ---- New report (offline-first) ---------------------------------------------------------------------------------
class ReportFormViewModel(private val c: AppContainer, private val assignmentId: Long) : ViewModel() {
    /** Generated once per form: makes upload retries idempotent on the server. */
    val clientUuid: String = UUID.randomUUID().toString()
    val assignment: AssignmentDto? = c.assignmentCache[assignmentId]
    val questions: List<String> = assignment?.job?.details.questions()

    var respondentLabel by mutableStateOf("")
    var notes by mutableStateOf("")
    val answers = mutableStateMapOf<String, String>()
    var city by mutableStateOf("")
    var photo by mutableStateOf<File?>(null)
        private set
    var capturedAt by mutableStateOf<String?>(null)
        private set
    var fix by mutableStateOf<GeoFix?>(null)
        private set
    var processingPhoto by mutableStateOf(false)
        private set
    var locating by mutableStateOf(false)
        private set
    var error by mutableStateOf<String?>(null)
        private set

    fun onPhoto(raw: File) {
        processingPhoto = true
        viewModelScope.launch {
            runCatching { Media.compress(raw, c.pendingReports.photoFileFor(clientUuid)) }
                .onSuccess {
                    photo = it
                    capturedAt = OffsetDateTime.now().toString()
                }
                .onFailure { error = it.message }
            processingPhoto = false
        }
    }

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

    fun save(context: Context, onSaved: () -> Unit) {
        val location = fix
        val image = photo
        val takenAt = capturedAt
        error = when {
            image == null || takenAt == null -> "Ambil foto bukti dulu."
            location == null -> "Ambil lokasi GPS dulu."
            questions.any { answers[it].isNullOrBlank() } -> "Jawab semua pertanyaan."
            else -> null
        }
        if (error != null || image == null || takenAt == null || location == null) return

        c.pendingReports.save(
            PendingReport(
                clientUuid = clientUuid,
                assignmentId = assignmentId,
                respondentLabel = respondentLabel.trim(),
                answersJson = c.gson.toJson(questions.associateWith { answers[it].orEmpty().trim() }),
                notes = notes.trim(),
                latitude = location.latitude,
                longitude = location.longitude,
                gpsAccuracyM = location.accuracyM,
                city = city.trim(),
                capturedAt = takenAt,
                isMock = location.isMock,
                photoPath = image.path,
            ),
        )
        UploadWorker.enqueue(context.applicationContext)
        onSaved()
    }
}

@Composable
fun ReportFormScreen(assignmentId: Long, onBack: () -> Unit) {
    val vm = appViewModel(key = "report-form-$assignmentId") { ReportFormViewModel(it, assignmentId) }
    val context = LocalContext.current
    val shoot = rememberCamera { vm.onPhoto(it) }
    val requestLocation = rememberLocationRequest { vm.captureLocation(context) }

    AppScaffold(title = "Laporan Baru", onBack = onBack) { padding ->
        ScrollBody(padding) {
            vm.assignment?.let { Text(it.job.title, style = MaterialTheme.typography.titleMedium) }
            InfoText("Laporan disimpan di HP dulu, lalu dikirim otomatis saat ada sinyal.")
            TextInput(vm.respondentLabel, { vm.respondentLabel = it }, "Label responden (mis. R-01, bukan nama lengkap)")
            vm.questions.forEachIndexed { i, q ->
                TextInput(vm.answers[q].orEmpty(), { vm.answers[q] = it }, "${i + 1}. $q", singleLine = false)
            }
            TextInput(vm.notes, { vm.notes = it }, "Catatan lapangan", singleLine = false, minLines = 3)
            PhotoField("Foto bukti (wajib, diambil langsung)", vm.photo, vm.processingPhoto, shoot)
            LocationField("Lokasi GPS (wajib)", vm.fix, vm.locating, requestLocation)
            TextInput(vm.city, { vm.city = it }, "Kota / Kabupaten")
            vm.error?.let { ErrorText(it) }
            BusyButton("Simpan & Kirim", busy = false) {
                vm.save(context) {
                    toast(context, "Laporan disimpan. Dikirim otomatis saat online.")
                    onBack()
                }
            }
        }
    }
}
