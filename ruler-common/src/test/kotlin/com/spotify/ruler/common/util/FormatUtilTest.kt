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

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class FormatUtilTest {

    @Test
    fun `formatBytes returns bytes for values under 1024`() {
        assertEquals("0 B", formatBytes(0))
        assertEquals("1 B", formatBytes(1))
        assertEquals("512 B", formatBytes(512))
        assertEquals("1023 B", formatBytes(1023))
    }

    @Test
    fun `formatBytes returns KB for values in kilobyte range`() {
        assertEquals("1.0 KB", formatBytes(1024))
        assertEquals("1.5 KB", formatBytes(1536))
        assertEquals("10.0 KB", formatBytes(10240))
        assertEquals("100.0 KB", formatBytes(102400))
    }

    @Test
    fun `formatBytes returns MB for values in megabyte range`() {
        assertEquals("1.0 MB", formatBytes(1048576))
        assertEquals("2.5 MB", formatBytes(2621440))
        assertEquals("10.0 MB", formatBytes(10485760))
        assertEquals("100.0 MB", formatBytes(104857600))
    }

    @Test
    fun `formatBytes returns GB for values in gigabyte range`() {
        assertEquals("1.0 GB", formatBytes(1073741824))
        assertEquals("2.5 GB", formatBytes(2684354560))
        assertEquals("10.0 GB", formatBytes(10737418240))
    }

    @Test
    fun `formatBytes returns TB for values in terabyte range`() {
        assertEquals("1.0 TB", formatBytes(1099511627776))
        assertEquals("2.5 TB", formatBytes(2748779069440))
    }

    @Test
    fun `formatBytes returns PB for values in petabyte range`() {
        assertEquals("1.0 PB", formatBytes(1125899906842624))
    }

    @Test
    fun `formatBytes rounds to one decimal place`() {
        assertEquals("1.3 KB", formatBytes(1331))
        assertEquals("1.7 MB", formatBytes(1782579))
        assertEquals("3.4 GB", formatBytes(3651010560))
    }
}
