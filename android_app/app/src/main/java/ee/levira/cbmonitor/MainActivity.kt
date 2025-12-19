package ee.levira.cbmonitor

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var statusText: TextView
    private lateinit var logView: TextView
    private var pendingStartAction: (() -> Unit)? = null
    private val logUpdateHandler = Handler(Looper.getMainLooper())
    private var isUpdatingLogs = false

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
        logView = findViewById(R.id.logView)
        val startButton: Button = findViewById(R.id.startButton)
        val stopButton: Button = findViewById(R.id.stopButton)

        startButton.setOnClickListener {
            requestPermissionsIfNeeded {
                ContextCompat.startForegroundService(
                    this,
                    Intent(this, MonitoringService::class.java)
                )
                statusText.text = "Logging started (every 30 s)"
                startLogUpdates()
            }
        }

        stopButton.setOnClickListener {
            stopService(Intent(this, MonitoringService::class.java))
            statusText.text = "Logging stopped"
            stopLogUpdates()
        }

        // Initial log display
        updateLogDisplay()
    }

    override fun onResume() {
        super.onResume()
        // Check if service is running and update logs accordingly
        updateLogDisplay()
    }

    override fun onPause() {
        super.onPause()
        stopLogUpdates()
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

    private fun updateLogDisplay() {
        try {
            val dir = getExternalFilesDir("cb_monitor") ?: filesDir
            val statusFile = File(dir, "status.json")
            
            // Try to get current session ID from status.json
            var sessionId: String? = null
            if (statusFile.exists()) {
                try {
                    val statusJson = JSONObject(statusFile.readText())
                    sessionId = statusJson.optString("session_id", null)
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

            val entries = readLastLogEntries(logFile, 10)
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
}
