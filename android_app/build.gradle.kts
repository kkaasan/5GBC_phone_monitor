// Top-level build file for the CBMonitorAndroid project.
// Repository configuration is handled in settings.gradle.kts (dependencyResolutionManagement).

tasks.register<Delete>("clean") {
    delete(rootProject.buildDir)
}

