package ee.levira.cbmonitor

import android.content.Context
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Captures Cell Broadcast messages from logcat
 * Requires READ_LOGS permission to be granted via ADB:
 * adb shell pm grant ee.levira.cbmonitor android.permission.READ_LOGS
 */
class LogcatCBLogger(private val context: Context) {

    companion object {
        private const val TAG = "LogcatCBLogger"
    }

    private var logcatProcess: Process? = null
    private var logcatJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO)
    private var isRunning = false
    private var deviceName: String = "phone"

    fun startLogging(deviceName: String = "phone") {
        if (isRunning) {
            Log.d(TAG, "CB logcat logging already running")
            return
        }

        this.deviceName = deviceName
        Log.i(TAG, "Starting CB logcat monitoring for device: $deviceName...")

        logcatJob = scope.launch {
            try {
                isRunning = true

                // Clear logcat first to avoid processing old messages
                try {
                    Runtime.getRuntime().exec("logcat -c").waitFor()
                } catch (e: Exception) {
                    Log.w(TAG, "Could not clear logcat", e)
                }

                // Start logcat monitoring for CB messages
                logcatProcess = Runtime.getRuntime().exec(
                    arrayOf("logcat", "-v", "time", "GsmCellBroadcastHandler:D", "*:S")
                )

                val reader = BufferedReader(InputStreamReader(logcatProcess!!.inputStream))
                val currentMessageLines = mutableListOf<String>()
                var inMessage = false

                while (isActive && isRunning) {
                    val line = reader.readLine() ?: break

                    // Detect start of new CB message
                    if (line.contains("Not a duplicate message") ||
                        line.contains("Duplicate message detected")) {

                        // Save previous message if exists
                        if (currentMessageLines.isNotEmpty() && inMessage) {
                            parseCBMessage(currentMessageLines)?.let { saveCBMessage(it) }
                        }

                        // Start new message
                        currentMessageLines.clear()
                        currentMessageLines.add(line)
                        inMessage = true

                    } else if (inMessage) {
                        currentMessageLines.add(line)

                        // Check if message is complete
                        if (line.contains("release wakelock") ||
                            line.contains("call cancel") ||
                            line.contains("broadcast complete")) {

                            parseCBMessage(currentMessageLines)?.let { saveCBMessage(it) }
                            currentMessageLines.clear()
                            inMessage = false
                        }
                    }
                }

            } catch (e: Exception) {
                Log.e(TAG, "Error in CB logcat monitoring", e)
            } finally {
                isRunning = false
            }
        }
    }

    fun stopLogging() {
        Log.i(TAG, "Stopping CB logcat monitoring...")
        isRunning = false
        logcatJob?.cancel()
        logcatProcess?.destroy()
        logcatProcess = null
    }

    private fun parseCBMessage(logLines: List<String>): JSONObject? {
        try {
            val cbData = JSONObject()
            val bodyLines = mutableListOf<String>()
            var logTimestamp: String? = null
            var inMessage = false

            // Log lines that are system state, not body content
            val systemKeywords = listOf(
                "SmsCbMessage{", "Dispatching", "Found ", "compareMessage",
                "Duplicate message", "Not a duplicate", "Idle:", "Waiting:",
                "call cancel", "Airplane mode", "onLocationUnavailable",
                "release wakelock", "broadcast complete"
            )

            for (line in logLines) {
                // Extract timestamp from first log line
                if (logTimestamp == null) {
                    val tsRegex = Regex("""^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})""")
                    tsRegex.find(line)?.let { logTimestamp = it.groupValues[1] }
                }

                if (line.contains("SmsCbMessage{")) {
                    inMessage = true

                    // Parse header fields from the SmsCbMessage{ line
                    Regex("""geographicalScope=(\d+)""").find(line)?.let {
                        cbData.put("geographicalScope", it.groupValues[1].toInt())
                    }
                    Regex("""serialNumber=(\d+)""").find(line)?.let {
                        cbData.put("serialNumber", it.groupValues[1].toInt())
                    }
                    Regex("""serviceCategory=(\d+)""").find(line)?.let {
                        cbData.put("serviceCategory", it.groupValues[1].toInt())
                    }
                    Regex("""language=(\w+)""").find(line)?.let {
                        cbData.put("language", it.groupValues[1])
                    }
                    // location=[mcc,mnc,lac/tac] - broadcast area cell identifier
                    Regex("""location=\[([^\]]*)\]""").find(line)?.let {
                        cbData.put("location", it.groupValues[1])
                    }

                    // Try to parse metadata fields from this line (single-line message format)
                    parseMetadataFields(line, cbData)

                    // Extract first body line (everything after "body=")
                    Regex("""body=(.*)$""").find(line)?.let {
                        var bodyText = it.groupValues[1]
                        // Single-line format: strip trailing metadata
                        if (bodyText.contains(", priority=")) {
                            bodyText = bodyText.substringBefore(", priority=")
                        }
                        if (bodyText.isNotEmpty()) bodyLines.add(bodyText)
                    }

                } else if (inMessage) {
                    // Extract content after logcat prefix "): "
                    val content = line.substringAfter("): ").trimEnd()

                    // The closing metadata line starts with ", priority=" or ", received time="
                    if (content.startsWith(", priority=") || content.startsWith(", received time=") ||
                        content.startsWith(", SmsCbCmasInfo")) {
                        parseMetadataFields(content, cbData)
                    } else if (systemKeywords.none { line.contains(it) }) {
                        // Body continuation line
                        bodyLines.add(content)
                    }
                }
            }

            // Assemble body, removing trailing blank lines
            if (bodyLines.isNotEmpty()) {
                val trimmed = bodyLines.dropLastWhile { it.isBlank() }
                val fullBody = trimmed.joinToString("\n").trim()

                // Fallback: if metadata was mixed into body (edge case), split it out
                if (fullBody.contains(", priority=")) {
                    cbData.put("body", fullBody.substringBefore(", priority=").trim())
                    val metaPart = ", priority=" + fullBody.substringAfter(", priority=")
                    parseMetadataFields(metaPart, cbData)
                } else {
                    cbData.put("body", fullBody)
                }
            }

            if (cbData.length() == 0 || !cbData.has("body")) return null

            cbData.put("logTimestamp", logTimestamp)
            cbData.put("source", "android_logcat")
            return cbData

        } catch (e: Exception) {
            Log.e(TAG, "Error parsing CB message from logcat", e)
            return null
        }
    }

    private fun parseMetadataFields(text: String, cbData: JSONObject) {
        if (!cbData.has("priority")) {
            Regex("""priority=(\d+)""").find(text)?.let {
                cbData.put("priority", it.groupValues[1].toInt())
            }
        }
        if (!cbData.has("receivedTime")) {
            Regex("""received time=(\d+)""").find(text)?.let {
                cbData.put("receivedTime", it.groupValues[1].toLong())
            }
        }
        if (!cbData.has("slotIndex")) {
            Regex("""slotIndex\s*=\s*(\d+)""").find(text)?.let {
                cbData.put("slotIndex", it.groupValues[1].toInt())
            }
        }
        if (!cbData.has("maximumWaitingTime")) {
            Regex("""maximumWaitingTime=(\d+)""").find(text)?.let {
                cbData.put("maximumWaitingTime", it.groupValues[1].toInt())
            }
        }
        if (!cbData.has("geo")) {
            Regex("""geo=([^}]*)""").find(text)?.let {
                val geo = it.groupValues[1].trimEnd('}').trim()
                if (geo.isNotEmpty()) cbData.put("geo", geo)
            }
        }
        if (!cbData.has("cmasInfo")) {
            val cmasRegex = Regex(
                """SmsCbCmasInfo\{messageClass=(-?\d+), category=(-?\d+), responseType=(-?\d+), severity=(-?\d+), urgency=(-?\d+), certainty=(-?\d+)\}"""
            )
            cmasRegex.find(text)?.let {
                cbData.put("cmasInfo", JSONObject().apply {
                    put("messageClass", it.groupValues[1].toInt())
                    put("category", it.groupValues[2].toInt())
                    put("responseType", it.groupValues[3].toInt())
                    put("severity", it.groupValues[4].toInt())
                    put("urgency", it.groupValues[5].toInt())
                    put("certainty", it.groupValues[6].toInt())
                })
            }
        }
    }

    private fun saveCBMessage(cbData: JSONObject) {
        try {
            // Parse timestamp
            val timestamp = try {
                val logTs = cbData.optString("logTimestamp")
                if (logTs.isNotEmpty()) {
                    // Parse "12-29 14:30:22.123" format
                    val year = SimpleDateFormat("yyyy", Locale.US).format(Date())
                    val parts = logTs.split(" ")
                    val datePart = parts[0]
                    val timePart = parts[1]
                    val dateStr = "$year-$datePart $timePart"
                    SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US).parse(dateStr)
                        ?: Date()
                } else {
                    Date()
                }
            } catch (e: Exception) {
                Date()
            }

            val timestampStr = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US).format(timestamp)

            // Get current location from status.json
            val location = getLastKnownLocation()

            // Create CB record
            val cbRecord = JSONObject().apply {
                put("timestamp", timestampStr)
                put("receivedTime", cbData.opt("receivedTime"))
                put("serialNumber", cbData.opt("serialNumber"))
                put("serviceCategory", cbData.opt("serviceCategory"))
                put("body", cbData.optString("body", ""))
                put("language", cbData.optString("language"))
                put("priority", cbData.opt("priority"))
                put("geographicalScope", cbData.opt("geographicalScope"))
                cbData.optString("location").let { if (it.isNotEmpty()) put("location", it) }
                cbData.optString("geo").let { if (it.isNotEmpty()) put("geo", it) }
                cbData.optJSONObject("cmasInfo")?.let { put("cmasInfo", it) }
                put("maximumWaitingTime", cbData.opt("maximumWaitingTime"))
                put("slotIndex", cbData.opt("slotIndex"))
                put("coordinates", location)
                put("source", cbData.optString("source"))
            }

            // Generate message ID with device name prefix
            val msgId = "${deviceName}_" +
                    SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(timestamp) +
                    "_${cbData.opt("serialNumber")}"

            // Save to file
            val dir = context.getExternalFilesDir("cb_monitor") ?: context.filesDir
            val cbLogsDir = File(dir, "cb_logs")
            if (!cbLogsDir.exists()) {
                cbLogsDir.mkdirs()
            }

            val cbFile = File(cbLogsDir, "$msgId.json")

            // Don't overwrite if file exists
            if (cbFile.exists()) {
                Log.d(TAG, "CB message already saved: $msgId")
                return
            }

            cbFile.writeText(cbRecord.toString(2))

            // Update CB index
            updateCBIndex(dir, msgId, cbRecord)

            Log.i(TAG, "CB message saved: $msgId - ${cbData.optString("body").take(50)}")

        } catch (e: Exception) {
            Log.e(TAG, "Error saving CB message from logcat", e)
        }
    }

    private fun getLastKnownLocation(): JSONObject {
        val locationJson = JSONObject()
        try {
            val dir = context.getExternalFilesDir("cb_monitor") ?: context.filesDir
            val statusFile = File(dir, "status.json")

            if (statusFile.exists()) {
                val statusData = JSONObject(statusFile.readText())
                val location = statusData.optJSONObject("location")
                if (location != null) {
                    locationJson.put("latitude", location.optString("latitude"))
                    locationJson.put("longitude", location.optString("longitude"))
                    return locationJson
                }
            }
        } catch (e: Exception) {
            // Ignore
        }

        locationJson.put("latitude", null)
        locationJson.put("longitude", null)
        return locationJson
    }

    private fun updateCBIndex(dir: File, msgId: String, cbRecord: JSONObject) {
        try {
            val cbIndexFile = File(dir, "cb_index.json")
            val index = if (cbIndexFile.exists()) {
                try {
                    JSONObject(cbIndexFile.readText())
                } catch (e: Exception) {
                    JSONObject().put("messages", JSONArray())
                }
            } else {
                JSONObject().put("messages", JSONArray())
            }

            val messages = index.optJSONArray("messages") ?: JSONArray()

            // Extract heading from body
            val body = cbRecord.optString("body", "")
            val heading = if (body.isNotEmpty()) {
                body.split("\n").firstOrNull()?.take(100) ?: "CB Message"
            } else {
                "CB Message"
            }

            // Create index entry
            val indexEntry = JSONObject().apply {
                put("id", msgId)
                put("timestamp", cbRecord.optString("timestamp"))
                put("heading", heading)
                put("priority", cbRecord.opt("priority"))
                put("language", cbRecord.optString("language"))
                put("serviceCategory", cbRecord.opt("serviceCategory"))
            }

            // Check if already exists
            var exists = false
            for (i in 0 until messages.length()) {
                val msg = messages.optJSONObject(i)
                if (msg?.optString("id") == msgId) {
                    exists = true
                    break
                }
            }

            if (!exists) {
                // Add to beginning
                val newMessages = JSONArray()
                newMessages.put(indexEntry)
                for (i in 0 until messages.length()) {
                    newMessages.put(messages.get(i))
                }
                index.put("messages", newMessages)

                cbIndexFile.writeText(index.toString(2))
            }

        } catch (e: Exception) {
            Log.e(TAG, "Error updating CB index", e)
        }
    }
}
