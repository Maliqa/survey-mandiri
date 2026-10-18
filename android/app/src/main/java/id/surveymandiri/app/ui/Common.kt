package id.surveymandiri.app.ui

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import id.surveymandiri.app.SurveyApp
import id.surveymandiri.app.data.AppContainer
import java.text.NumberFormat
import java.util.Locale

// ---- Theme ---------------------------------------------------------------------------------
private val Brand = Color(0xFF0B6E4F)

/** Always light (white background), regardless of the phone's dark-mode setting. */
private val LightColors = lightColorScheme(
    primary = Brand,
    onPrimary = Color.White,
    secondary = Color(0xFF2E7D60),
    background = Color.White,
    onBackground = Color(0xFF1B1F1D),
    surface = Color.White,
    onSurface = Color(0xFF1B1F1D),
    surfaceVariant = Color(0xFFF1F4F2),
    surfaceContainer = Color(0xFFF4F7F5),
    surfaceContainerLow = Color(0xFFF6F8F7),
    surfaceContainerHighest = Color(0xFFEDF1EE),
)

@Composable
fun SurveyTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = LightColors, content = content)
}

// ---- DI helpers ------------------------------------------------------------------------------
@Composable
fun appContainer(): AppContainer = (LocalContext.current.applicationContext as SurveyApp).container

/** ViewModel factory backed by the app container. */
@Composable
inline fun <reified VM : ViewModel> appViewModel(key: String? = null, crossinline builder: (AppContainer) -> VM): VM {
    val container = appContainer()
    return viewModel(
        key = key,
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = builder(container) as T
        },
    )
}

// ---- Formatting -------------------------------------------------------------------------------
private val idLocale: Locale = Locale.forLanguageTag("id-ID")

fun rupiah(amount: Long): String = "Rp" + NumberFormat.getInstance(idLocale).format(amount)

fun shortDateTime(iso: String?): String = iso?.take(16)?.replace('T', ' ').orEmpty()

fun categoryLabel(category: String): String = when (category) {
    "leasing" -> "Leasing"
    "caleg" -> "Caleg"
    "product" -> "Produk"
    else -> category
}

fun statusLabel(status: String): String = when (status) {
    "quoted" -> "Penawaran harga"
    "awaiting_payment" -> "Menunggu pembayaran"
    "open" -> "Mencari surveyor"
    "assigned" -> "Sedang dikerjakan"
    "in_review" -> "Menunggu review"
    "completed" -> "Selesai"
    "cancelled" -> "Dibatalkan"
    "active" -> "Aktif"
    "withdrawn" -> "Mundur"
    "done" -> "Selesai"
    "submitted" -> "Terkirim"
    "approved" -> "Disetujui"
    "rejected" -> "Ditolak"
    "pending" -> "Menunggu"
    "verified" -> "Terverifikasi"
    "suspended" -> "Ditangguhkan"
    "paid" -> "Sudah ditransfer"
    "funded" -> "Dana ditahan (escrow)"
    "released" -> "Dana dicairkan"
    "refunded" -> "Dana dikembalikan"
    else -> status
}

fun flagLabel(flag: String): String = when (flag) {
    "far_from_target" -> "Jauh dari titik target"
    "duplicate_photo" -> "Foto duplikat"
    "mock_location" -> "Terdeteksi GPS palsu"
    "low_gps_accuracy" -> "Akurasi GPS rendah"
    "outside_target_city" -> "Di luar kota target"
    else -> flag
}

private fun statusColor(status: String): Color = when (status) {
    "completed", "approved", "verified", "paid", "done", "released" -> Color(0xFF1E8E3E)
    "cancelled", "rejected", "suspended", "withdrawn", "refunded" -> Color(0xFFC5221F)
    "quoted", "awaiting_payment", "in_review", "pending" -> Color(0xFFB06000)
    else -> Color(0xFF1967D2)
}

// ---- Components --------------------------------------------------------------------------------
@Composable
fun AppScaffold(
    title: String,
    onBack: (() -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {},
    floatingActionButton: @Composable () -> Unit = {},
    bottomBar: @Composable () -> Unit = {},
    content: @Composable (PaddingValues) -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(onClick = onBack) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Kembali")
                        }
                    }
                },
                actions = actions,
            )
        },
        floatingActionButton = floatingActionButton,
        bottomBar = bottomBar,
        content = content,
    )
}

/** Standard scrollable form/detail body. */
@Composable
fun ScrollBody(padding: PaddingValues, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier = Modifier
            .padding(padding)
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        content = content,
    )
}

@Composable
fun StatusChip(status: String) {
    val color = statusColor(status)
    Surface(color = color.copy(alpha = 0.14f), shape = RoundedCornerShape(50)) {
        Text(
            statusLabel(status),
            color = color,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}

@Composable
fun FlagChip(flag: String) {
    Box(
        modifier = Modifier
            .background(Color(0xFFC5221F).copy(alpha = 0.12f), RoundedCornerShape(6.dp))
            .padding(horizontal = 8.dp, vertical = 3.dp),
    ) {
        Text("⚠ " + flagLabel(flag), color = Color(0xFFC5221F), style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
fun ErrorText(message: String) {
    Text(message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
}

@Composable
fun InfoText(message: String) {
    Text(message, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
}

@Composable
fun SectionTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
}

@Composable
fun LabeledValue(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
    }
}

@Composable
fun CenterLoading(padding: PaddingValues = PaddingValues()) {
    Box(Modifier.padding(padding).fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
fun EmptyState(padding: PaddingValues, message: String, error: String? = null, onRetry: (() -> Unit)? = null) {
    Column(
        Modifier.padding(padding).fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        if (error != null) ErrorText(error) else Text(message, style = MaterialTheme.typography.bodyLarge)
        if (onRetry != null) TextButton(onClick = onRetry) { Text("Muat ulang") }
    }
}

@Composable
fun BusyButton(text: String, busy: Boolean, modifier: Modifier = Modifier.fillMaxWidth(), enabled: Boolean = true, onClick: () -> Unit) {
    Button(onClick = onClick, enabled = enabled && !busy, modifier = modifier) {
        if (busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp) else Text(text)
    }
}

@Composable
fun TextInput(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier.fillMaxWidth(),
    keyboardType: KeyboardType = KeyboardType.Text,
    singleLine: Boolean = true,
    minLines: Int = 1,
    supporting: String? = null,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        modifier = modifier,
        singleLine = singleLine,
        minLines = minLines,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        supportingText = if (supporting != null) { { Text(supporting) } } else null,
    )
}

@Composable
fun PasswordInput(value: String, onValueChange: (String) -> Unit, label: String = "Password") {
    var visible by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
        visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
        trailingIcon = {
            TextButton(onClick = { visible = !visible }) { Text(if (visible) "Sembunyi" else "Lihat") }
        },
    )
}

/** Single-choice chips; scrolls horizontally on narrow screens. */
@Composable
fun ChoiceChips(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        options.forEach { (value, label) ->
            FilterChip(selected = value == selected, onClick = { onSelect(value) }, label = { Text(label) })
        }
    }
}

fun toast(context: android.content.Context, message: String) {
    Toast.makeText(context, message, Toast.LENGTH_LONG).show()
}
