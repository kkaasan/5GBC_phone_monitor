package ee.levira.cbmonitor

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.app.ActivityManager
import android.os.SystemClock
import android.graphics.Color
import android.widget.Button
import android.widget.TextView
import android.widget.LinearLayout
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import android.location.GnssStatus
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.telephony.CellIdentityNr
import android.telephony.CellInfo
import android.telephony.CellInfoLte
import android.telephony.CellInfoNr
import android.telephony.CellSignalStrengthLte
import android.telephony.CellSignalStrengthNr
import android.telephony.TelephonyManager
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var networkIdValue: TextView
    private lateinit var tacValue: TextView
    private lateinit var pciValue: TextView
    private lateinit var earfcnValue: TextView
    private lateinit var rssiValue: TextView
    private lateinit var rsrqValue: TextView
    private lateinit var gpsStatusValue: TextView
    private lateinit var coordsValue: TextView
    private lateinit var logView: TextView
    private lateinit var gpsRow: LinearLayout
    private lateinit var coordsRow: LinearLayout
    private var pendingStartAction: (() -> Unit)? = null
    private val logUpdateHandler = Handler(Looper.getMainLooper())
    private var isUpdatingLogs = false
    private val liveUpdateHandler = Handler(Looper.getMainLooper())
    private var isUpdatingLive = false
    private var isLogging = false
    private var lastSatVisible: Int? = null
    private var lastSatUsed: Int? = null
    private var gnssCallbackRegistered = false
    private var lastLocation: Location? = null
    private var locationCallbackRegistered = false
    private var liveLocationListener: LocationListener? = null

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grantResults ->
        val allGranted = grantResults.values.all { it }
        if (!allGranted) {
            statusText.text = "Permissions denied – logging may not work correctly"
            pendingStartAction = null
        } else {
            statusText.text = "Permissions granted – starting logging..."
            pendingStartAction?.invoke()
            pendingStartAction = null
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.statusText)
        networkIdValue = findViewById(R.id.networkIdValue)
        tacValue = findViewById(R.id.tacValue)
        pciValue = findViewById(R.id.pciValue)
        earfcnValue = findViewById(R.id.earfcnValue)
        rssiValue = findViewById(R.id.rssiValue)
        rsrqValue = findViewById(R.id.rsrqValue)
        gpsStatusValue = findViewById(R.id.gpsStatusValue)
        coordsValue = findViewById(R.id.coordsValue)
        logView = findViewById(R.id.logView)
        gpsRow = findViewById(R.id.gpsRow)
        coordsRow = findViewById(R.id.coordsRow)
        val startButton: Button = findViewById(R.id.startButton)

        startButton.setOnClickListener {
            if (isLogging) {
                stopLogging()
            } else {
                startLogging()
            }
        }

        // Initial log display
        updateLogDisplay()
        startLiveUpdates()
        isLogging = isServiceRunning()
        updateButtonLabel()
        if (isLogging) {
            startLogUpdates()
            statusText.text = "Logging active (every 30 s)"
        }
    }

    override fun onResume() {
        super.onResume()
        // Check if service is running and update logs accordingly
        updateLogDisplay()
        startLiveUpdates()
        isLogging = isServiceRunning()
        updateButtonLabel()
        if (isLogging) startLogUpdates()
    }

    override fun onPause() {
        super.onPause()
        stopLogUpdates()
        stopLiveUpdates()
    }

    private fun requestPermissionsIfNeeded(onGranted: () -> Unit) {
        // Core permissions needed for basic functionality
        val corePermissions = listOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.READ_PHONE_STATE
        )

        val missingCore = corePermissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missingCore.isEmpty()) {
            // Core permissions granted, check background location separately (Android 10+)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val hasBackground = ContextCompat.checkSelfPermission(
                    this,
                    Manifest.permission.ACCESS_BACKGROUND_LOCATION
                ) == PackageManager.PERMISSION_GRANTED

                if (!hasBackground) {
                    // Request background location separately (required by Android)
                    statusText.text = "Grant background location for continuous logging"
                    pendingStartAction = onGranted
                    permissionLauncher.launch(arrayOf(Manifest.permission.ACCESS_BACKGROUND_LOCATION))
                    return
                }
            }
            // All permissions granted, start immediately
            onGranted()
        } else {
            // Request core permissions first
            pendingStartAction = onGranted
            permissionLauncher.launch(missingCore.toTypedArray())
        }
    }

    private fun startLogging() {
        requestPermissionsIfNeeded {
            ContextCompat.startForegroundService(
                this,
                Intent(this, MonitoringService::class.java)
            )
            isLogging = true
            statusText.text = "Logging started (every 30 s)"
            updateButtonLabel()
            startLogUpdates()
        }
    }

    private fun stopLogging() {
        stopService(Intent(this, MonitoringService::class.java))
        isLogging = false
        statusText.text = "Logging stopped"
        updateButtonLabel()
        stopLogUpdates()
    }

    private fun updateButtonLabel() {
        val startButton: Button = findViewById(R.id.startButton)
        startButton.text = if (isLogging) "Stop logging" else "Start logging"
    }

    private fun isServiceRunning(): Boolean {
        val manager = getSystemService(ACTIVITY_SERVICE) as ActivityManager
        @Suppress("DEPRECATION")
        return manager.getRunningServices(Int.MAX_VALUE)
            .any { it.service.className == MonitoringService::class.java.name }
    }

    private fun startLogUpdates() {
        if (isUpdatingLogs) return
        isUpdatingLogs = true
        updateLogDisplay()
        scheduleNextUpdate()
    }

    private fun stopLogUpdates() {
        isUpdatingLogs = false
        logUpdateHandler.removeCallbacksAndMessages(null)
    }

    private fun scheduleNextUpdate() {
        if (!isUpdatingLogs) return
        logUpdateHandler.postDelayed({
            updateLogDisplay()
            scheduleNextUpdate()
        }, 5000) // Update every 5 seconds
    }

    private fun startLiveUpdates() {
        if (isUpdatingLive) return
        isUpdatingLive = true
        ensureGnssCallback()
        ensureLocationUpdates()
        updateLiveData()
    }

    private fun stopLiveUpdates() {
        isUpdatingLive = false
        liveUpdateHandler.removeCallbacksAndMessages(null)
        unregisterGnssCallback()
        stopLocationUpdates()
    }

    private fun scheduleNextLiveUpdate() {
        if (!isUpdatingLive) return
        liveUpdateHandler.postDelayed({
            updateLiveData()
        }, 1000) // every second
    }

    private fun updateLiveData() {
        val snapshot = fetchLiveCellInfo()
        networkIdValue.text = snapshot.networkId
        tacValue.text = snapshot.tac
        pciValue.text = snapshot.pciCellId
        earfcnValue.text = snapshot.channel
        rssiValue.text = snapshot.rssiRsrp
        rsrqValue.text = snapshot.rsrq
        gpsStatusValue.text = snapshot.gpsStatus
        coordsValue.text = snapshot.coords

        val warnGps = snapshot.satUsed == 0 && (snapshot.lastFixAgeSec ?: Int.MAX_VALUE) > 120
        val highlightColor = Color.parseColor("#FFE7C2") // light orange
        val defaultColor = Color.TRANSPARENT
        gpsStatusValue.setBackgroundColor(if (warnGps) highlightColor else defaultColor)
        coordsValue.setBackgroundColor(if (warnGps) highlightColor else defaultColor)
        gpsRow.setBackgroundColor(if (warnGps) highlightColor else defaultColor)
        coordsRow.setBackgroundColor(if (warnGps) highlightColor else defaultColor)
        scheduleNextLiveUpdate()
    }

    private fun updateLogDisplay() {
        try {
            val dir = getExternalFilesDir("cb_monitor") ?: filesDir
            val statusFile = File(dir, "status.json")
            
            // Try to get current session ID from status.json
            var sessionId: String? = null
            if (statusFile.exists()) {
                try {
                    val statusJson = JSONObject(statusFile.readText())
                    sessionId = statusJson.optString("session_id").takeIf { it.isNotBlank() }
                } catch (e: Exception) {
                    // Ignore
                }
            }

            // If no active session, try to find the most recent log file
            if (sessionId == null) {
                val logFiles = dir.listFiles { _, name -> name.endsWith(".jsonl") }
                if (logFiles != null && logFiles.isNotEmpty()) {
                    sessionId = logFiles.maxByOrNull { it.lastModified() }?.name?.removeSuffix(".jsonl")
                }
            }

            if (sessionId == null) {
                logView.text = "No log entries yet...\nStart logging to see data."
                return
            }

            val logFile = File(dir, "$sessionId.jsonl")
            if (!logFile.exists()) {
                logView.text = "Log file not found: $sessionId.jsonl"
                return
            }

            val entries = readLastLogEntries(logFile, 5)
            if (entries.isEmpty()) {
                logView.text = "Log file is empty..."
            } else {
                logView.text = entries.joinToString("\n\n")
            }
        } catch (e: Exception) {
            logView.text = "Error reading logs: ${e.message}"
        }
    }

    private fun readLastLogEntries(logFile: File, count: Int): List<String> {
        val entries = mutableListOf<String>()
        try {
            val lines = logFile.readLines()
            val lastLines = lines.takeLast(count)
            
            lastLines.forEach { line ->
                val trimmed = line.trim()
                if (trimmed.isNotEmpty()) {
                    try {
                        val json = JSONObject(trimmed)
                        entries.add(formatLogEntry(json))
                    } catch (e: Exception) {
                        // Skip malformed lines
                    }
                }
            }
        } catch (e: Exception) {
            // File read error
        }
        return entries.reversed() // Show newest first
    }

    private fun formatLogEntry(json: JSONObject): String {
        val timestamp = json.optString("timestamp", "?")
        val timeStr = try {
            // Try different timestamp formats
            val formats = listOf(
                SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US),
                SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS", Locale.US),
                SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US)
            )
            var date: Date? = null
            for (format in formats) {
                try {
                    date = format.parse(timestamp)
                    break
                } catch (e: Exception) {
                    // Try next format
                }
            }
            if (date != null) {
                val outputFormat = SimpleDateFormat("HH:mm:ss", Locale.US)
                outputFormat.format(date)
            } else {
                timestamp.takeLast(8) // Fallback
            }
        } catch (e: Exception) {
            timestamp.takeLast(8) // Fallback to last 8 chars
        }

        val location = json.optJSONObject("location")
        val lat = location?.optString("latitude") ?: "-"
        val lon = location?.optString("longitude") ?: "-"
        val locStr = if (lat != "-" && lon != "-") {
            "${lat.take(8)}, ${lon.take(8)}"
        } else {
            "No GPS"
        }

        val signal = json.optJSONObject("signal")
        val rssi = signal?.opt("rssi")?.toString() ?: "-"
        val rsrp = signal?.opt("rsrp")?.toString() ?: "-"
        val rsrq = signal?.opt("rsrq")?.toString() ?: "-"

        val lte = json.optJSONObject("lte")
        val pci = lte?.optString("pci") ?: "-"

        return "$timeStr | RSSI: $rssi | RSRP: $rsrp | RSRQ: $rsrq\n" +
               "📍 $locStr | PCI: $pci"
    }

    private fun fetchLiveCellInfo(): LiveSnapshot {
        val placeholder = LiveSnapshot(
            networkId = "-",
            tac = "-",
            pciCellId = "-",
            channel = "-",
            rssiRsrp = "-",
            rsrq = "-",
            gpsStatus = "-",
            coords = "-",
            satUsed = null,
            lastFixAgeSec = null
        )
        val requiredPermissions = listOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.READ_PHONE_STATE
        )
        val missing = requiredPermissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            return placeholder.copy(networkId = "Permissions needed")
        }

        val telephony = getSystemService(TELEPHONY_SERVICE) as TelephonyManager
        val location = getLatestLocationQuick()
        val coordsText = location?.let { "${formatCoord(it.latitude)}, ${formatCoord(it.longitude)}" } ?: "-"
        val ageSeconds = location?.let { ((System.currentTimeMillis() - it.time) / 1000).toInt().coerceAtLeast(0) }
        val satUsedCount = lastSatUsed
        val satSummary = formatSatelliteStatus()
        val gpsStatus = when {
            location == null -> "No fix $satSummary"
            ageSeconds == null -> "Fix $satSummary"
            else -> "Fix ~${ageSeconds}s ago (${location.provider}) $satSummary"
        }

        val allCells: List<CellInfo>? = try {
            telephony.allCellInfo
        } catch (_: SecurityException) {
            return placeholder.copy(networkId = "Permissions needed", gpsStatus = gpsStatus, coords = coordsText)
        } catch (_: Exception) {
            null
        }

        val registered = allCells?.filter { it.isRegistered } ?: emptyList()
        val nrCell = registered.filterIsInstance<CellInfoNr>().firstOrNull()
        val lteCell = registered.filterIsInstance<CellInfoLte>().firstOrNull()
        val anyRegistered = registered.firstOrNull()
        val anyCell = allCells?.firstOrNull()

        val cell = nrCell ?: lteCell ?: anyRegistered ?: anyCell ?: return placeholder.copy(
            networkId = "No cell info",
            gpsStatus = gpsStatus,
            coords = coordsText
        )

        return when (cell) {
            is CellInfoNr -> {
                val id = cell.cellIdentity as? CellIdentityNr
                val strength = cell.cellSignalStrength as? CellSignalStrengthNr
                val mcc = id?.mccString
                val mnc = id?.mncString
                val networkId = listOfNotNull(mcc, mnc).takeIf { it.isNotEmpty() }?.joinToString("-") ?: "-"
                val tac = id?.tac?.takeIf { it != Int.MAX_VALUE }?.toString() ?: "-"
                val pci = id?.pci?.toString() ?: "-"
                val ci = id?.nci?.toString() ?: "-"
                val rssi = "-" // not exposed for NR
                val rsrp = strength?.ssRsrp?.takeIf { it != CellInfo.UNAVAILABLE }?.toString() ?: "-"
                val rsrq = strength?.ssRsrq?.takeIf { it != CellInfo.UNAVAILABLE }?.toString() ?: "-"
                val channelNumber = id?.nrarfcn?.takeIf { it != Int.MAX_VALUE }
                LiveSnapshot(
                    networkId = networkId,
                    tac = tac,
                    pciCellId = "$pci / $ci",
                    channel = channelNumber?.let { "NR-ARFCN $it" } ?: "-",
                    rssiRsrp = "$rssi / $rsrp",
                    rsrq = rsrq,
                    gpsStatus = gpsStatus,
                    coords = coordsText,
                    satUsed = satUsedCount,
                    lastFixAgeSec = ageSeconds
                )
            }

            is CellInfoLte -> {
                val id = cell.cellIdentity
                val strength: CellSignalStrengthLte = cell.cellSignalStrength
                val networkId = listOfNotNull(
                    id.mccString?.takeIf { it.isNotBlank() },
                    id.mncString?.takeIf { it.isNotBlank() }
                ).takeIf { it.isNotEmpty() }?.joinToString("-")
                    ?: listOfNotNull(
                        id.mcc.takeIf { it != Int.MAX_VALUE }?.toString(),
                        id.mnc.takeIf { it != Int.MAX_VALUE }?.toString()
                    ).takeIf { it.isNotEmpty() }?.joinToString("-")
                    ?: "-"

                val earfcn = id.earfcn.takeIf { it != Int.MAX_VALUE }?.toString() ?: "-"
                val tac = id.tac.takeIf { it != Int.MAX_VALUE }?.toString() ?: "-"
                val pci = id.pci.takeIf { it != Int.MAX_VALUE }?.toString() ?: "-"
                val ci = id.ci.takeIf { it != Int.MAX_VALUE }?.toString() ?: "-"
                val rssiVal = strength.rssi.takeIf { it != CellInfo.UNAVAILABLE }
                val rsrpVal = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    strength.rsrp.takeIf { it != CellInfo.UNAVAILABLE }
                } else null
                val rsrqVal = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    strength.rsrq.takeIf { it != CellInfo.UNAVAILABLE }
                } else null

                LiveSnapshot(
                    networkId = networkId,
                    tac = tac,
                    pciCellId = "$pci / $ci",
                    channel = "EARFCN $earfcn",
                    rssiRsrp = "${rssiVal ?: "-"} / ${rsrpVal ?: "-"}",
                    rsrq = (rsrqVal ?: "-").toString(),
                    gpsStatus = gpsStatus,
                    coords = coordsText,
                    satUsed = satUsedCount,
                    lastFixAgeSec = ageSeconds
                )
            }

            else -> placeholder.copy(
                networkId = "Unsupported cell type",
                gpsStatus = gpsStatus,
                coords = coordsText,
                satUsed = satUsedCount,
                lastFixAgeSec = ageSeconds
            )
        }
    }

    private fun getLatestLocationQuick(): Location? {
        val hasFine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val hasCoarse = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (!hasFine && !hasCoarse) return null

        val recentLive = lastLocation?.takeIf {
            val ageMs = (SystemClock.elapsedRealtimeNanos() - it.elapsedRealtimeNanos) / 1_000_000L
            ageMs in 0..20_000
        }
        if (recentLive != null) return recentLive

        val lm = getSystemService(LOCATION_SERVICE) as? LocationManager ?: return null
        val providers = listOf(
            LocationManager.GPS_PROVIDER,
            LocationManager.NETWORK_PROVIDER,
            LocationManager.PASSIVE_PROVIDER
        )
        val newestKnown = providers.mapNotNull { provider ->
            try {
                lm.getLastKnownLocation(provider)
            } catch (_: SecurityException) {
                null
            } catch (_: Exception) {
                null
            }
        }.maxByOrNull { it.time }
        if (newestKnown != null) {
            lastLocation = newestKnown
        }
        return newestKnown ?: lastLocation
    }

    private fun formatCoord(value: Double): String {
        return String.format(Locale.US, "%.6f", value)
    }

    private fun ensureGnssCallback() {
        if (gnssCallbackRegistered) return
        val hasFine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (!hasFine) return
        val lm = getSystemService(LOCATION_SERVICE) as? LocationManager ?: return
        try {
            lm.registerGnssStatusCallback(ContextCompat.getMainExecutor(this), gnssStatusCallback)
            gnssCallbackRegistered = true
        } catch (_: SecurityException) {
            // ignore
        } catch (_: Exception) {
            // ignore
        }
    }

    private fun ensureLocationUpdates() {
        if (locationCallbackRegistered) return
        val hasFine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val hasCoarse = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (!hasFine && !hasCoarse) return
        val lm = getSystemService(LOCATION_SERVICE) as? LocationManager ?: return

        val listener = object : LocationListener {
            override fun onLocationChanged(location: Location) {
                lastLocation = location
            }

            @Deprecated("Deprecated in Java")
            override fun onStatusChanged(provider: String?, status: Int, extras: android.os.Bundle?) {}
            override fun onProviderEnabled(provider: String) {}
            override fun onProviderDisabled(provider: String) {}
        }
        liveLocationListener = listener
        try {
            lm.requestLocationUpdates(
                LocationManager.GPS_PROVIDER,
                1000L,
                0f,
                listener,
                Looper.getMainLooper()
            )
        } catch (_: SecurityException) {
            // ignore
        }
        try {
            lm.requestLocationUpdates(
                LocationManager.NETWORK_PROVIDER,
                2000L,
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
        val lm = getSystemService(LOCATION_SERVICE) as? LocationManager ?: return
        liveLocationListener?.let {
            try {
                lm.removeUpdates(it)
            } catch (_: Exception) {
            }
        }
        locationCallbackRegistered = false
        liveLocationListener = null
    }

    private fun unregisterGnssCallback() {
        if (!gnssCallbackRegistered) return
        val lm = getSystemService(LOCATION_SERVICE) as? LocationManager ?: return
        try {
            lm.unregisterGnssStatusCallback(gnssStatusCallback)
        } catch (_: Exception) {
            // ignore
        } finally {
            gnssCallbackRegistered = false
        }
    }

    private val gnssStatusCallback = object : GnssStatus.Callback() {
        override fun onSatelliteStatusChanged(status: GnssStatus) {
            val count = status.satelliteCount
            lastSatVisible = count
            var used = 0
            for (i in 0 until count) {
                if (status.usedInFix(i)) used++
            }
            lastSatUsed = used
        }
    }

    private fun formatSatelliteStatus(): String {
        val visible = lastSatVisible
        val used = lastSatUsed
        return if (visible != null && used != null) {
            "(sats $used/$visible)"
        } else {
            "(sats -/-)"
        }
    }

    data class LiveSnapshot(
        val networkId: String,
        val tac: String,
        val pciCellId: String,
        val channel: String,
        val rssiRsrp: String,
        val rsrq: String,
        val gpsStatus: String,
        val coords: String,
        val satUsed: Int?,
        val lastFixAgeSec: Int?
    )
}
