/*
* Copyright 2024 Spotify AB
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

package com.spotify.ruler.cli

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.io.File
import java.util.logging.Level
import java.util.logging.Logger

/**
 * Generates a dependency map JSON by scanning directories for JAR files.
 *
 * This allows the CLI to auto-generate the dependency map instead of requiring
 * it to be provided manually. Module names are inferred from file paths using
 * Maven/Gradle repository conventions.
 */
class DependencyMapGenerator {

    private val logger = Logger.getLogger("Ruler")

    private val json = Json { prettyPrint = true }

    /**
     * Scans the given directories for JAR files and generates a [ModuleMap].
     *
     * @param jarsDirs Directories to scan recursively for .jar files
     * @return The generated ModuleMap
     */
    fun generate(jarsDirs: List<File>): ModuleMap {
        val jars = mutableListOf<Jar>()

        for (dir in jarsDirs) {
            require(dir.isDirectory) { "Not a directory: ${dir.absolutePath}" }
            logger.log(Level.INFO, "Scanning for JARs in: ${dir.absolutePath}")

            dir.walkTopDown()
                .filter { it.isFile && it.extension.equals("jar", ignoreCase = true) }
                .forEach { jarFile ->
                    val moduleName = inferModuleName(jarFile, dir)
                    jars.add(Jar(jar = jarFile.absolutePath, module = moduleName))
                    logger.log(Level.INFO, "Found JAR: ${jarFile.name} -> module: $moduleName")
                }
        }

        logger.log(Level.INFO, "Generated dependency map with ${jars.size} JARs")
        return ModuleMap(assets = emptyList(), jars = jars, resources = emptyList())
    }

    /**
     * Generates a [ModuleMap] and writes it to a JSON file.
     *
     * @param jarsDirs Directories to scan recursively for .jar files
     * @param outputFile File to write the JSON output to
     * @return The output file
     */
    fun generateToFile(jarsDirs: List<File>, outputFile: File): File {
        val moduleMap = generate(jarsDirs)
        outputFile.parentFile?.mkdirs()
        outputFile.writeText(json.encodeToString(moduleMap))
        logger.log(Level.INFO, "Wrote dependency map to: ${outputFile.absolutePath}")
        return outputFile
    }

    /**
     * Infers a module name from a JAR file's path.
     *
     * Supports common directory conventions:
     * - Maven: `repository/com/example/lib/1.0/lib-1.0.jar` -> `com.example:lib:1.0`
     * - Gradle cache: `files-2.1/com.example/lib/1.0/<hash>/lib-1.0.jar` -> `com.example:lib:1.0`
     * - Gradle build output: `project/build/.../classes.jar` -> inferred from path
     * - Fallback: uses the JAR filename without extension
     */
    internal fun inferModuleName(jarFile: File, baseDir: File): String {
        val relativePath = jarFile.relativeTo(baseDir).path.replace('\\', '/')
        val segments = relativePath.split('/')

        // Try Gradle module cache convention: files-2.1/group/artifact/version/hash/file.jar
        inferFromGradleCache(segments)?.let { return it }

        // Try Maven repository convention: group-as-path/artifact/version/file.jar
        inferFromMavenRepo(segments)?.let { return it }

        // Try Gradle build output: look for module name from build path
        inferFromGradleBuildOutput(segments)?.let { return it }

        // Fallback: use the JAR filename without extension and version
        return stripVersion(jarFile.nameWithoutExtension)
    }

    /**
     * Gradle cache: `files-2.1/group/artifact/version/hash/artifact-version.jar`
     * or: `transforms-N/hash/transformed/artifact-version.jar` with metadata
     */
    private fun inferFromGradleCache(segments: List<String>): String? {
        val filesIdx = segments.indexOfFirst { it.startsWith("files-2") }
        if (filesIdx >= 0 && segments.size >= filesIdx + 5) {
            val group = segments[filesIdx + 1]
            val artifact = segments[filesIdx + 2]
            val version = segments[filesIdx + 3]
            if (looksLikeVersion(version)) {
                return "$group:$artifact:$version"
            }
        }
        return null
    }

    /**
     * Maven repo: `com/example/artifact/1.0.0/artifact-1.0.0.jar`
     * The group is a path like `com/example` and we need to detect where it ends
     * and the artifact name begins.
     */
    private fun inferFromMavenRepo(segments: List<String>): String? {
        // Need at least: group-segment(s) / artifact / version / file.jar
        if (segments.size < 4) return null

        val fileName = segments.last()
        val version = segments[segments.size - 2]
        val artifact = segments[segments.size - 3]

        // Validate: version should look like a version, and the filename should contain artifact name
        if (!looksLikeVersion(version)) return null
        if (!fileName.startsWith(artifact, ignoreCase = true)) return null

        // Group is everything before artifact
        val groupSegments = segments.subList(0, segments.size - 3)
        if (groupSegments.isEmpty()) return null

        val group = groupSegments.joinToString(".")
        return "$group:$artifact:$version"
    }

    /**
     * Gradle build output: look for patterns like `moduleName/build/...`
     */
    private fun inferFromGradleBuildOutput(segments: List<String>): String? {
        val buildIdx = segments.indexOf("build")
        if (buildIdx > 0) {
            return segments.subList(0, buildIdx).joinToString(":")
        }
        return null
    }

    private val versionPattern = Regex("^\\d+\\.\\d+.*")

    private fun looksLikeVersion(text: String): Boolean {
        return versionPattern.matches(text)
    }

    /**
     * Strips version-like suffixes from a name.
     * e.g., "gson-2.10.1" -> "gson", "kotlin-stdlib" -> "kotlin-stdlib"
     */
    private fun stripVersion(name: String): String {
        val dashIdx = name.indexOfFirst { it == '-' && name.indexOf('-') != name.lastIndexOf('-') || it == '-' }
        if (dashIdx > 0) {
            val suffix = name.substring(dashIdx + 1)
            if (versionPattern.matches(suffix)) {
                return name.substring(0, dashIdx)
            }
        }
        return name
    }
}
