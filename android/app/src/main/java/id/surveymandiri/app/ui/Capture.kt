package id.surveymandiri.app.ui

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import id.surveymandiri.app.util.Geo
import id.surveymandiri.app.util.GeoFix
import id.surveymandiri.app.util.Media
import java.io.File
import java.util.Locale

/** Returns a function that opens the system camera and reports the raw photo file. */
@Composable
fun rememberCamera(onCaptured: (File) -> Unit): () -> Unit {
    val context = LocalContext.current
    var pendingPath by rememberSaveable { mutableStateOf<String?>(null) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val path = pendingPath
        if (ok && path != null) onCaptured(File(path))
    }
    return {
        try {
            val (file, uri) = Media.newCameraTarget(context)
            pendingPath = file.path
            launcher.launch(uri)
        } catch (e: Exception) {
            toast(context, "Kamera tidak tersedia: ${e.message}")
        }
    }
}

/** Returns a function that asks for location permission if needed, then calls [onGranted]. */
@Composable
fun rememberLocationRequest(onGranted: () -> Unit): () -> Unit {
    val context = LocalContext.current
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
        if (result.values.any { it }) onGranted() else toast(context, "Izin lokasi dibutuhkan untuk fitur ini.")
    }
    return {
        if (Geo.hasPermission(context)) onGranted() else launcher.launch(Geo.permissions)
    }
}

@Composable
fun PhotoField(label: String, file: File?, busy: Boolean = false, onShoot: () -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
        if (file != null) {
            AsyncImage(
                model = Uri.fromFile(file),
                contentDescription = label,
                contentScale = ContentScale.Crop,
                modifier = Modifier.size(84.dp).clip(RoundedCornerShape(8.dp)),
            )
        }
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(label, style = MaterialTheme.typography.bodyMedium)
            OutlinedButton(onClick = onShoot, enabled = !busy) {
                Text(if (busy) "Memproses..." else if (file == null) "Ambil Foto" else "Ulangi Foto")
            }
        }
    }
}

@Composable
fun LocationField(label: String, fix: GeoFix?, busy: Boolean, onCapture: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        if (fix != null) {
            Text(
                String.format(Locale.US, "%.6f, %.6f  (akurasi ±%.0f m)", fix.latitude, fix.longitude, fix.accuracyM),
                style = MaterialTheme.typography.bodySmall,
            )
            if (fix.isMock) {
                Text("Terdeteksi lokasi palsu (mock GPS). Laporan akan ditandai.", color = Color(0xFFC5221F), style = MaterialTheme.typography.bodySmall)
            } else if (fix.accuracyM > 100) {
                Text("Akurasi rendah. Coba di area terbuka lalu ambil ulang.", color = Color(0xFFB06000), style = MaterialTheme.typography.bodySmall)
            }
        }
        OutlinedButton(onClick = onCapture, enabled = !busy) {
            Text(if (busy) "Mencari lokasi..." else if (fix == null) "Ambil Lokasi GPS" else "Perbarui Lokasi")
        }
    }
}
