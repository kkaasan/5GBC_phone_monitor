package ee.levira.cbmonitor

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class CellBroadcastReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "CBReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        Log.i(TAG, "Cell Broadcast received: ${intent.action}")

        try {
            // Log the broadcast receipt - detailed parsing is done by LogcatCBLogger
            // This receiver serves as a fallback and notification mechanism

            val extras = intent.extras
            if (extras != null) {
                Log.d(TAG, "CB broadcast extras: ${extras.keySet().joinToString()}")

                // Try to extract basic info if available
                val message = extras.get("message")
                if (message != null) {
                    Log.d(TAG, "CB message object received: ${message.javaClass.name}")
                    // LogcatCBLogger will parse this from logcat
                    saveCBNotification(context)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error processing CB broadcast", e)
        }
    }

    private fun saveCBNotification(context: Context) {
        try {
            // Just log that we received a CB broadcast
            // The actual parsing and saving is done by LogcatCBLogger
            // which reads from logcat and has more reliable access to CB message details

            val timestamp = Date()
            val timestampStr = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US).format(timestamp)

            Log.i(TAG, "CB broadcast notification saved at $timestampStr")

            // The LogcatCBLogger running in MonitoringService will handle the actual
            // message capture and storage

        } catch (e: Exception) {
            Log.e(TAG, "Error logging CB notification", e)
        }
    }

}
