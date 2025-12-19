package ee.levira.cbmonitor

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Looper
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.telephony.CellIdentityNr
import android.telephony.CellInfo
import android.telephony.CellInfoLte
import android.telephony.CellInfoNr
import android.telephony.CellSignalStrengthLte
import android.telephony.CellSignalStrengthNr
import android.telephony.TelephonyManager
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class MonitoringService : Service() {

    private val scope = CoroutineScope(Dispatchers.IO)
    private var job: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null

    private var sessionId: String? = null
    private var lastLocation: Location? = null
    private var locationManager: LocationManager? = null
    private var locationListener: LocationListener? = null
    private var locationCallbackRegistered = false

    override fun onCreate() {
        super.onCreate()
        startForeground(1, createNotification())
        acquireWakeLock()
        locationManager = getSystemService(Context.LOCATION_SERVICE) as? LocationManager
        ensureLocationUpdates()
        restoreExistingSessionId()
        startMonitoringLoop()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Ensure we stay alive when the app is backgrounded or the screen is off.
        startForeground(1, createNotification())
        acquireWakeLock()
        ensureLocationUpdates()
        startMonitoringLoop()
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        job?.cancel()
        releaseWakeLock()
        stopLocationUpdates()
        updateDataIndex()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotification(): Notification {
        val channelId = "cb_monitor_channel"
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "CB Monitor",
                NotificationManager.IMPORTANCE_LOW
            )
            manager.createNotificationChannel(channel)
        }

        return NotificationCompat.Builder(this, channelId)
            .setContentTitle("CB Monitor")
            .setContentText("Collecting cell & GPS data every 30s")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .build()
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "CBMonitor::CaptureWakeLock").apply {
            setReferenceCounted(false)
            try {
                acquire()
            } catch (_: Exception) {
                // If acquisition fails, continue without it
            }
        }
    }

    private fun releaseWakeLock() {
        try {
            if (wakeLock?.isHeld == true) {
                wakeLock?.release()
            }
        } catch (_: Exception) {
            // Ignore release errors
        } finally {
            wakeLock = null
        }
    }

    private fun startMonitoringLoop() {
        if (job?.isActive == true) return
        job = scope.launch {
            while (isActive) {
                val start = SystemClock.elapsedRealtime()
                captureAndLogSnapshot()
                val elapsed = SystemClock.elapsedRealtime() - start
                val wait = (30_000L - elapsed).coerceAtLeast(0L)
                delay(wait)
            }
        }
    }

    private fun restoreExistingSessionId() {
        val dir = getExternalFilesDir("cb_monitor") ?: filesDir
        val statusFile = File(dir, "status.json")
        if (!statusFile.exists()) return
        try {
            val json = JSONObject(statusFile.readText())
            val existing = json.optString("session_id").takeIf { it.isNotBlank() }
            if (existing != null) {
                sessionId = existing
            }
        } catch (_: Exception) {
            // Best-effort reuse of previous session id
        }
    }

    private fun captureAndLogSnapshot() {
        val now = Date()
        if (sessionId == null) {
            sessionId = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(now)
        }

        val timestamp = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US).format(now)

        val cellInfo = getCellInfo()
        val location = getLocation()

        val snapshot = JSONObject().apply {
            put("timestamp", timestamp)
            put("lte", JSONObject().apply {
                put("tac", cellInfo.optString("tac", "-"))
                put("earfcn", cellInfo.optString("earfcn", "-"))
                put("mcc", cellInfo.optString("mcc", "-"))
                put("mnc", cellInfo.optString("mnc", "-"))
                put("ci", cellInfo.optString("ci", "-"))
                put("pci", cellInfo.optString("pci", "-"))
                put("rat", cellInfo.optString("rat", "-"))
                cellInfo.optString("note", "").takeIf { it.isNotEmpty() }?.let { put("note", it) }
            })
            put("signal", JSONObject().apply {
                put("rssi", cellInfo.opt("rssi"))
                put("rsrp", cellInfo.opt("rsrp"))
                put("rsrq", cellInfo.opt("rsrq"))
                put("snr", cellInfo.opt("snr")) // may be null
            })
            put("location", JSONObject().apply {
                put("latitude", location?.latitude?.toString())
                put("longitude", location?.longitude?.toString())
            })
            cellInfo.optString("note", "").takeIf { it.isNotEmpty() }?.let {
                put("cell_note", it)
            }
        }

        val dir = getExternalFilesDir("cb_monitor") ?: filesDir
        val statusFile = File(dir, "status.json")
        val logFile = File(dir, "${sessionId}.jsonl")

        // Write status.json (overwrites each time)
        statusFile.writeText(
            snapshot.apply {
                put("session_id", sessionId)
            }.toString(2)
        )

        // Append to session log
        logFile.appendText(snapshot.toString() + "\n")
    }

    private fun getCellInfo(): JSONObject {
        val json = JSONObject()
        try {
            val requiredPermissions = listOf(
                android.Manifest.permission.ACCESS_FINE_LOCATION,
                android.Manifest.permission.ACCESS_COARSE_LOCATION,
                android.Manifest.permission.READ_PHONE_STATE
            )
            val missing = requiredPermissions.filter {
                ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
            }
            if (missing.isNotEmpty()) {
                json.put("note", "missing_permissions:${missing.joinToString(",")}")
                return json
            }

            val telephony = getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager
            val allCells: List<CellInfo>? = fetchCellInfo(telephony)

            // Prefer 5G NR if available, otherwise LTE. Fall back to any registered, then any cell.
            val registered = allCells?.filter { it.isRegistered } ?: emptyList()
            val nrCell = registered.filterIsInstance<CellInfoNr>().firstOrNull()
            val lteCell = registered.filterIsInstance<CellInfoLte>().firstOrNull()
            val anyRegistered = registered.firstOrNull()
            val anyCell = allCells?.firstOrNull()

            when (val cell = nrCell ?: lteCell ?: anyRegistered ?: anyCell) {
                is CellInfoNr -> {
                    val id = cell.cellIdentity as? CellIdentityNr
                    val strength = cell.cellSignalStrength

                json.put("rat", "NR")
                if (id != null) {
                    json.put("tac", id.tac.takeIf { it != Int.MAX_VALUE } ?: JSONObject.NULL)
                    json.put("earfcn", id.nrarfcn.takeIf { it != Int.MAX_VALUE } ?: JSONObject.NULL)
                    json.put("mcc", id.mccString ?: JSONObject.NULL)
                        json.put("mnc", id.mncString ?: JSONObject.NULL)
                        json.put("ci", id.nci)
                        json.put("pci", id.pci)
                    }

                if (strength is CellSignalStrengthNr) {
                    json.put("rssi", JSONObject.NULL) // Not available for NR
                    json.put("rsrp", strength.ssRsrp)
                    json.put("rsrq", strength.ssRsrq)
                    json.put("snr", strength.ssSinr.takeIf { it != CellInfo.UNAVAILABLE } ?: JSONObject.NULL)
                }
                if (!cell.isRegistered) {
                    json.put("note", "using_unregistered_nr_cell")
                }
            }
            is CellInfoLte -> {
                val id = cell.cellIdentity
                val strength: CellSignalStrengthLte = cell.cellSignalStrength

                json.put("rat", "LTE")
                json.put("tac", id.tac)
                json.put("earfcn", id.earfcn)
                json.put("mcc", id.mcc)
                json.put("mnc", id.mnc)
                json.put("ci", id.ci)
                json.put("pci", id.pci)

                val rssiVal = strength.rssi.takeIf { it != CellInfo.UNAVAILABLE }
                json.put("rssi", rssiVal ?: JSONObject.NULL)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    json.put("rsrp", strength.rsrp.takeIf { it != CellInfo.UNAVAILABLE } ?: JSONObject.NULL)
                    json.put("rsrq", strength.rsrq.takeIf { it != CellInfo.UNAVAILABLE } ?: JSONObject.NULL)
                    json.put("snr", strength.rssnr.takeIf { it != CellInfo.UNAVAILABLE } ?: JSONObject.NULL)
                } else {
                    json.put("rsrp", JSONObject.NULL)
                    json.put("rsrq", JSONObject.NULL)
                    json.put("snr", JSONObject.NULL)
                }
                if (!cell.isRegistered) {
                    json.put("note", "using_unregistered_lte_cell")
                }
            }
                else -> {
                    if (allCells.isNullOrEmpty()) {
                        json.put("note", "no_cell_info_available")
                    } else {
                        json.put("note", "no_registered_cell")
                    }
                }
            }
        } catch (_: SecurityException) {
            json.put("error", "missing_permission")
        } catch (e: Exception) {
            // Ignore, return partial/empty info
        }
        return json
    }

    private fun fetchCellInfo(telephony: TelephonyManager): List<CellInfo>? {
        var cells: List<CellInfo>? = try {
            telephony.allCellInfo
        } catch (e: SecurityException) {
            throw e
        } catch (_: Exception) {
            null
        }
        if (!cells.isNullOrEmpty()) return cells

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val latch = CountDownLatch(1)
            var refreshed: List<CellInfo>? = null
            try {
                telephony.requestCellInfoUpdate(
                    ContextCompat.getMainExecutor(this),
                    object : TelephonyManager.CellInfoCallback() {
                        override fun onCellInfo(cellInfo: MutableList<CellInfo>) {
                            refreshed = cellInfo
                            latch.countDown()
                        }
                    }
                )
                latch.await(1500L, TimeUnit.MILLISECONDS)
            } catch (e: SecurityException) {
                throw e
            } catch (_: Exception) {
                // ignore and fall back
            }
            if (!refreshed.isNullOrEmpty()) {
                cells = refreshed
            }
        }
        return cells
    }

    private fun getLocation(): Location? {
        val recent = lastLocation?.takeIf {
            val ageMs = (SystemClock.elapsedRealtimeNanos() - it.elapsedRealtimeNanos) / 1_000_000L
            ageMs in 0..30_000
        }
        if (recent != null) return recent

        ensureLocationUpdates()
        return try {
            val lm = locationManager ?: getSystemService(Context.LOCATION_SERVICE) as? LocationManager ?: return lastLocation

            val hasFine = ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
            val hasCoarse = ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
            if (!hasFine && !hasCoarse) return null

            // 1) Try to get a fresh fix from GPS or network within ~5s.
            var freshLocation: Location? = null
            val latch = CountDownLatch(1)
            val listener = object : LocationListener {
                override fun onLocationChanged(location: Location) {
                    // Prefer GPS, but take the first fix we get.
                    if (freshLocation == null || location.provider == LocationManager.GPS_PROVIDER) {
                        freshLocation = location
                        latch.countDown()
                    }
                }

                @Deprecated("Deprecated in Java")
                override fun onStatusChanged(provider: String?, status: Int, extras: android.os.Bundle?) {}
                override fun onProviderEnabled(provider: String) {}
                override fun onProviderDisabled(provider: String) {}
            }

            val providersToRequest = mutableListOf<String>()
            if (lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) providersToRequest.add(LocationManager.GPS_PROVIDER)
            if (lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) providersToRequest.add(LocationManager.NETWORK_PROVIDER)
            if (providersToRequest.isEmpty()) {
                providersToRequest.add(LocationManager.GPS_PROVIDER)
                providersToRequest.add(LocationManager.NETWORK_PROVIDER)
            }

            try {
                providersToRequest.forEach { provider ->
                    try {
                        lm.requestLocationUpdates(
                            provider,
                            0L,
                            0f,
                            listener,
                            Looper.getMainLooper()
                        )
                    } catch (_: SecurityException) {
                        // Ignore; will fall back below.
                    }
                }
                latch.await(5, TimeUnit.SECONDS)
            } catch (_: Exception) {
                // Ignore and fall back
            } finally {
                try {
                    lm.removeUpdates(listener)
                } catch (_: Exception) {
                }
            }

            if (freshLocation != null) {
                lastLocation = freshLocation
                return freshLocation
            }

            // 2) Fallback: pick the newest last known location from any provider.
            val providers = listOf(
                LocationManager.GPS_PROVIDER,
                LocationManager.NETWORK_PROVIDER,
                LocationManager.PASSIVE_PROVIDER
            )
            providers.asSequence()
                .mapNotNull { provider ->
                    try {
                        lm.getLastKnownLocation(provider)
                    } catch (e: SecurityException) {
                        null
                    }
                }
                .maxByOrNull { it.time }
        } catch (_: Exception) {
            lastLocation
        }
    }

    private fun ensureLocationUpdates() {
        if (locationCallbackRegistered) return
        val lm = locationManager ?: return
        val hasFine = ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val hasCoarse = ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (!hasFine && !hasCoarse) return

        val listener = object : LocationListener {
            override fun onLocationChanged(location: Location) {
                lastLocation = location
            }

            @Deprecated("Deprecated in Java")
            override fun onStatusChanged(provider: String?, status: Int, extras: android.os.Bundle?) {}
            override fun onProviderEnabled(provider: String) {}
            override fun onProviderDisabled(provider: String) {}
        }
        locationListener = listener
        try {
            lm.requestLocationUpdates(
                LocationManager.GPS_PROVIDER,
                5_000L,
                0f,
                listener,
                Looper.getMainLooper()
            )
        } catch (_: Exception) {
            // ignore
        }
        try {
            lm.requestLocationUpdates(
                LocationManager.NETWORK_PROVIDER,
                10_000L,
                0f,
                listener,
                Looper.getMainLooper()
            )
        } catch (_: Exception) {
            // ignore
        }
        locationCallbackRegistered = true
    }

    private fun stopLocationUpdates() {
        if (!locationCallbackRegistered) return
        val lm = locationManager ?: return
        try {
            locationListener?.let { lm.removeUpdates(it) }
        } catch (_: Exception) {
        } finally {
            locationCallbackRegistered = false
            locationListener = null
        }
    }

    private fun updateDataIndex() {
        val currentSession = sessionId ?: return
        val dir = getExternalFilesDir("cb_monitor") ?: filesDir
        val logFile = File(dir, "${currentSession}.jsonl")
        if (!logFile.exists()) return

        val points = mutableListOf<JSONObject>()
        logFile.forEachLine { line ->
            val trimmed = line.trim()
            if (trimmed.isNotEmpty()) {
                try {
                    points.add(JSONObject(trimmed))
                } catch (_: Exception) {
                    // skip malformed line
                }
            }
        }

        if (points.isEmpty()) return

        val first = points.first()
        val last = points.last()

        val lats = mutableListOf<Double>()
        val lons = mutableListOf<Double>()
        for (p in points) {
            val loc = p.optJSONObject("location") ?: continue
            val latStr = loc.optString("latitude", "")
            val lonStr = loc.optString("longitude", "")
            val lat = latStr.toDoubleOrNull()
            val lon = lonStr.toDoubleOrNull()
            if (lat != null && lon != null) {
                lats.add(lat)
                lons.add(lon)
            }
        }

        val metadata = JSONObject().apply {
            put("session_id", currentSession)
            put("start_time", first.optString("timestamp"))
            put("end_time", last.optString("timestamp"))
            put("count", points.size)
            put("bounds", JSONObject().apply {
                if (lats.isNotEmpty() && lons.isNotEmpty()) {
                    put("min_lat", lats.minOrNull())
                    put("max_lat", lats.maxOrNull())
                    put("min_lon", lons.minOrNull())
                    put("max_lon", lons.maxOrNull())
                } else {
                    put("min_lat", JSONObject.NULL)
                    put("max_lat", JSONObject.NULL)
                    put("min_lon", JSONObject.NULL)
                    put("max_lon", JSONObject.NULL)
                }
            })
        }

        val indexFile = File(dir, "data_index.json")
        val root = if (indexFile.exists()) {
            try {
                JSONObject(indexFile.readText())
            } catch (_: Exception) {
                JSONObject().put("sessions", JSONArray())
            }
        } else {
            JSONObject().put("sessions", JSONArray())
        }

        val sessions = root.optJSONArray("sessions") ?: JSONArray()
        // Remove any existing entry with same session_id
        val remaining = JSONArray()
        for (i in 0 until sessions.length()) {
            val s = sessions.optJSONObject(i)
            if (s == null || s.optString("session_id") != currentSession) {
                remaining.put(s)
            }
        }
        remaining.put(metadata)

        // Sort by start_time descending
        val sorted = (0 until remaining.length())
            .mapNotNull { remaining.optJSONObject(it) }
            .sortedByDescending { it.optString("start_time") }

        val newArray = JSONArray()
        sorted.forEach { newArray.put(it) }

        val newRoot = JSONObject().apply {
            put("sessions", newArray)
        }
        indexFile.writeText(newRoot.toString(2))
    }
}
