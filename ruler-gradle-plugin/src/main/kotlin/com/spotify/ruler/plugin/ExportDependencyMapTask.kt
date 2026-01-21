/*
* Copyright 2021 Spotify AB
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*      http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/

package com.spotify.ruler.plugin

import com.spotify.ruler.common.dependency.DependencyEntry
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.MapProperty
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

/**
 * Gradle task that exports dependency information to a JSON file for use with ruler-cli.
 */
abstract class ExportDependencyMapTask : DefaultTask() {

    @get:Input
    abstract val dependencyEntries: MapProperty<String, List<DependencyEntry>>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun exportDependencyMap() {
        val allEntries = dependencyEntries.get().values.flatten()

        val jars = mutableListOf<JarInfo>()
        val assets = mutableListOf<AssetInfo>()
        val resources = mutableListOf<AssetInfo>()

        allEntries.forEach { entry ->
            when {
                entry.name.endsWith(".jar") -> {
                    jars.add(JarInfo(jar = entry.name, module = entry.component))
                }
                entry.name.startsWith("/assets/") || entry.name.contains("/assets/") -> {
                    assets.add(AssetInfo(filename = entry.name, module = entry.component))
                }
                entry.name.startsWith("/res/") || entry.name.contains("/res/") -> {
                    resources.add(AssetInfo(filename = entry.name, module = entry.component))
                }
                entry.name.endsWith(".class") -> {
                    // Classes are typically in JARs, handled above
                }
                else -> {
                    // Default to resources for other files
                    resources.add(AssetInfo(filename = entry.name, module = entry.component))
                }
            }
        }

        val moduleMap = ModuleMap(
            assets = assets.distinctBy { "${it.module}:${it.filename}" },
            jars = jars.distinctBy { it.jar },
            resources = resources.distinctBy { "${it.module}:${it.filename}" }
        )

        val json = Json { prettyPrint = true }
        val jsonString = json.encodeToString(moduleMap)

        outputFile.get().asFile.apply {
            parentFile.mkdirs()
            writeText(jsonString)
        }

        println("Dependency map exported to: ${outputFile.get().asFile.absolutePath}")
        println("Found ${jars.size} JARs, ${assets.size} assets, ${resources.size} resources")
    }
}

@Serializable
data class ModuleMap(
    val assets: List<AssetInfo>,
    val jars: List<JarInfo>,
    val resources: List<AssetInfo>
)

@Serializable
data class AssetInfo(
    val filename: String,
    val module: String
)

@Serializable
data class JarInfo(
    val jar: String,
    val module: String
)
