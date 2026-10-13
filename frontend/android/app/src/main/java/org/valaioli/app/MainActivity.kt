package org.valaioli.app

import com.getcapacitor.BridgeActivity

/**
 * MainActivity
 *
 * Entry point for the Valaioli Android application.
 * Extends BridgeActivity (Capacitor), which hosts the React/Vite
 * WebView UI and registers the native plugin bridge.
 */
class MainActivity : BridgeActivity() {

    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        // Register native plugin before super.onCreate
        registerPlugin(ValaioliNativePlugin::class.java)
        super.onCreate(savedInstanceState)

        // Start foreground download service so it remains alive
        // even when the WebView host activity is not in the foreground.
        val serviceIntent = android.content.Intent(this, DownloadService::class.java)
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent)
        } else {
            startService(serviceIntent)
        }
    }
}

