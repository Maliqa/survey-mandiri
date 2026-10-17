package id.surveymandiri.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import id.surveymandiri.app.ui.AppNav
import id.surveymandiri.app.ui.SurveyTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val container = (application as SurveyApp).container
        setContent {
            SurveyTheme {
                AppNav(container)
            }
        }
    }
}
