package id.surveymandiri.app.util

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.location.Geocoder
import android.net.Uri
import android.os.Build
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.exifinterface.media.ExifInterface
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.CancellationTokenSource
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.util.Locale
import kotlin.math.max
import kotlin.math.min

object Media {
    /** Temp file + content Uri for the system camera (ACTION_IMAGE_CAPTURE). */
    fun newCameraTarget(context: Context): Pair<File, Uri> {
        val dir = File(context.cacheDir, "camera").apply { mkdirs() }
        val file = File(dir, "cap_${System.currentTimeMillis()}.jpg")
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        return file to uri
    }

    /**
     * Downscales to [maxDim] px, applies EXIF rotation and re-encodes as JPEG so uploads stay
     * well under the server's 8 MB limit. Deletes [source] afterwards.
     */
    suspend fun compress(source: File, dest: File, maxDim: Int = 1600, quality: Int = 80) = withContext(Dispatchers.IO) {
        val bounds = BitmapFactory.Options()
        bounds.inJustDecodeBounds = true
        BitmapFactory.decodeFile(source.path, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) throw IOException("Foto tidak bisa dibaca.")

        var sample = 1
        while (max(bounds.outWidth, bounds.outHeight) / (sample * 2) >= maxDim) sample *= 2
        val decode = BitmapFactory.Options()
        decode.inSampleSize = sample
        val bitmap = BitmapFactory.decodeFile(source.path, decode) ?: throw IOException("Foto tidak bisa dibaca.")

        val rotation = when (ExifInterface(source.path).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)) {
            ExifInterface.ORIENTATION_ROTATE_90 -> 90f
            ExifInterface.ORIENTATION_ROTATE_180 -> 180f
            ExifInterface.ORIENTATION_ROTATE_270 -> 270f
            else -> 0f
        }
        val scale = min(1f, maxDim.toFloat() / max(bitmap.width, bitmap.height))
        val matrix = Matrix()
        matrix.postScale(scale, scale)
        matrix.postRotate(rotation)
        val output = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)

        dest.parentFile?.mkdirs()
        FileOutputStream(dest).use { stream -> output.compress(Bitmap.CompressFormat.JPEG, quality, stream) }
        if (output !== bitmap) output.recycle()
        bitmap.recycle()
        if (source.path != dest.path) source.delete()
        dest
    }
}

data class GeoFix(
    val latitude: Double,
    val longitude: Double,
    val accuracyM: Double,
    val isMock: Boolean,
    val city: String,
)

object Geo {
    fun hasPermission(context: Context): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    val permissions = arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)

    /** Fresh high-accuracy fix + mock-location flag + best-effort city name. */
    @SuppressLint("MissingPermission")
    @Suppress("DEPRECATION")
    suspend fun currentFix(context: Context): GeoFix {
        if (!hasPermission(context)) throw IOException("Izin lokasi belum diberikan.")
        val client = LocationServices.getFusedLocationProviderClient(context)
        val location = client.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, CancellationTokenSource().token).await()
            ?: throw IOException("Lokasi tidak didapat. Aktifkan GPS lalu coba lagi.")
        val mock = if (Build.VERSION.SDK_INT >= 31) location.isMock else location.isFromMockProvider
        val city = withContext(Dispatchers.IO) {
            runCatching {
                Geocoder(context, Locale.forLanguageTag("id-ID"))
                    .getFromLocation(location.latitude, location.longitude, 1)
                    ?.firstOrNull()
                    ?.let { it.subAdminArea ?: it.locality }
            }.getOrNull()
        }.orEmpty()
        return GeoFix(location.latitude, location.longitude, location.accuracy.toDouble(), mock, city)
    }
}
