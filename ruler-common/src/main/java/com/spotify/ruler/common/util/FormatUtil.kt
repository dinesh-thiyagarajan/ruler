/*
* Copyright 2026 Spotify AB
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

package com.spotify.ruler.common.util

import kotlin.math.log10
import kotlin.math.pow

private const val BYTE_FACTOR = 1024.0

/**
 * Formats a byte size into a human-readable string with appropriate units.
 *
 * @param bytes The size in bytes to format
 * @return A formatted string with the size and unit (e.g., "2.5 MB", "1.2 GB")
 */
fun formatBytes(bytes: Long): String {
    if (bytes < BYTE_FACTOR) {
        return "$bytes B"
    }

    val units = arrayOf("B", "KB", "MB", "GB", "TB", "PB")
    val exp = (log10(bytes.toDouble()) / log10(BYTE_FACTOR)).toInt()
    val unit = units.getOrElse(exp) { units.last() }
    val value = bytes / BYTE_FACTOR.pow(exp)

    return "%.1f %s".format(value, unit)
}
