package id.surveymandiri.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import id.surveymandiri.app.data.AppContainer

object Routes {
    const val SPLASH = "splash"
    const val LOGIN = "login"
    const val REGISTER_CLIENT = "register/client"
    const val REGISTER_SURVEYOR = "register/surveyor"
    const val CLIENT_HOME = "client/home"
    const val CLIENT_NEW = "client/new"
    const val CLIENT_REQUEST = "client/request/{id}"
    const val CLIENT_REPORTS = "client/request/{id}/reports"
    const val SURVEYOR_HOME = "surveyor/home"
    const val SURVEYOR_JOB = "surveyor/job/{id}"
    const val SURVEYOR_ASSIGNMENT = "surveyor/assignment/{id}"
    const val SURVEYOR_REPORT = "surveyor/assignment/{id}/report"

    fun withId(route: String, id: Long) = route.replace("{id}", id.toString())
}

private val idArg = listOf(navArgument("id") { type = NavType.LongType })

/** Replace the whole back stack (login/logout/home). */
private fun NavHostController.resetTo(route: String) {
    navigate(route) {
        popUpTo(graph.id) { inclusive = true }
        launchSingleTop = true
    }
}

@Composable
fun AppNav(container: AppContainer) {
    val nav = rememberNavController()

    LaunchedEffect(Unit) {
        container.tokenStore.sessionExpired.collect {
            toast(container.appContext, "Sesi berakhir. Silakan masuk lagi.")
            nav.resetTo(Routes.LOGIN)
        }
    }

    NavHost(navController = nav, startDestination = Routes.SPLASH) {
        composable(Routes.SPLASH) { SplashScreen(onRoute = { nav.resetTo(it) }) }

        composable(Routes.LOGIN) {
            LoginScreen(
                onLoggedIn = { role -> nav.resetTo(homeRoute(role)) },
                onRegisterClient = { nav.navigate(Routes.REGISTER_CLIENT) },
                onRegisterSurveyor = { nav.navigate(Routes.REGISTER_SURVEYOR) },
            )
        }
        composable(Routes.REGISTER_CLIENT) {
            RegisterClientScreen(onBack = { nav.popBackStack() }, onDone = { role -> nav.resetTo(homeRoute(role)) })
        }
        composable(Routes.REGISTER_SURVEYOR) {
            RegisterSurveyorScreen(onBack = { nav.popBackStack() }, onDone = { role -> nav.resetTo(homeRoute(role)) })
        }

        // Client
        composable(Routes.CLIENT_HOME) {
            val logout = rememberLogout { nav.resetTo(Routes.LOGIN) }
            ClientHomeScreen(
                onCreate = { nav.navigate(Routes.CLIENT_NEW) },
                onOpen = { id -> nav.navigate(Routes.withId(Routes.CLIENT_REQUEST, id)) },
                onLogout = logout,
            )
        }
        composable(Routes.CLIENT_NEW) {
            CreateRequestScreen(
                onBack = { nav.popBackStack() },
                onCreated = { id ->
                    nav.navigate(Routes.withId(Routes.CLIENT_REQUEST, id)) {
                        popUpTo(Routes.CLIENT_NEW) { inclusive = true }
                    }
                },
            )
        }
        composable(Routes.CLIENT_REQUEST, arguments = idArg) { entry ->
            val id = entry.arguments?.getLong("id") ?: 0L
            RequestDetailScreen(
                id = id,
                onBack = { nav.popBackStack() },
                onReports = { nav.navigate(Routes.withId(Routes.CLIENT_REPORTS, id)) },
            )
        }
        composable(Routes.CLIENT_REPORTS, arguments = idArg) { entry ->
            RequestReportsScreen(requestId = entry.arguments?.getLong("id") ?: 0L, onBack = { nav.popBackStack() })
        }

        // Surveyor
        composable(Routes.SURVEYOR_HOME) {
            val logout = rememberLogout { nav.resetTo(Routes.LOGIN) }
            SurveyorHomeScreen(
                onJob = { id -> nav.navigate(Routes.withId(Routes.SURVEYOR_JOB, id)) },
                onAssignment = { id -> nav.navigate(Routes.withId(Routes.SURVEYOR_ASSIGNMENT, id)) },
                onLogout = logout,
            )
        }
        composable(Routes.SURVEYOR_JOB, arguments = idArg) { entry ->
            JobDetailScreen(
                id = entry.arguments?.getLong("id") ?: 0L,
                onBack = { nav.popBackStack() },
                onAccepted = { assignmentId ->
                    nav.navigate(Routes.withId(Routes.SURVEYOR_ASSIGNMENT, assignmentId)) {
                        popUpTo(Routes.SURVEYOR_HOME)
                    }
                },
            )
        }
        composable(Routes.SURVEYOR_ASSIGNMENT, arguments = idArg) { entry ->
            val id = entry.arguments?.getLong("id") ?: 0L
            AssignmentScreen(
                id = id,
                onBack = { nav.popBackStack() },
                onNewReport = { nav.navigate(Routes.withId(Routes.SURVEYOR_REPORT, id)) },
            )
        }
        composable(Routes.SURVEYOR_REPORT, arguments = idArg) { entry ->
            ReportFormScreen(assignmentId = entry.arguments?.getLong("id") ?: 0L, onBack = { nav.popBackStack() })
        }
    }
}
