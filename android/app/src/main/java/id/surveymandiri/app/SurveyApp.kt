package id.surveymandiri.app

import android.app.Application
import id.surveymandiri.app.data.AppContainer
import id.surveymandiri.app.data.UploadWorker

class SurveyApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        // Resume any reports left in the outbox from a previous session.
        if (container.pendingReports.all().any { !it.failedPermanently }) {
            UploadWorker.enqueue(this)
        }
    }
}
