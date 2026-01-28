# Ruler CLI

Command-line interface for [Ruler](../README.md) -- analyze Android APK/bundle size by module and dependency without requiring the Gradle plugin.

## Overview

The Ruler CLI provides the same analysis capabilities as the Ruler Gradle plugin, but can be run standalone against any APK or AAB file. It produces JSON and HTML reports showing how each module and dependency contributes to your app's size.

Key features:
- Analyze APK or AAB (app bundle) files
- Attribute file sizes to modules/dependencies
- Auto-generate dependency maps from JAR directories (no manual JSON needed)
- Ownership-based breakdowns by team
- Size verification with configurable thresholds
- JSON + interactive HTML reports

## Building

Build the CLI fat JAR:

```bash
./gradlew :ruler-cli:shadowJar
```

The output JAR is at `ruler-cli/build/libs/ruler-cli-<version>-all.jar`.

## Usage

### Basic usage with a dependency map

```bash
java -jar ruler-cli.jar \
  --apk-file app-release.apk \
  --dependency-map dependency-map.json \
  --app-info-file app-info.json \
  --project-path /path/to/project \
  --report-dir ./reports
```

### Auto-generate dependency map from JARs

Instead of providing a manually-created dependency map, point the CLI at directories containing your dependency JARs:

```bash
java -jar ruler-cli.jar \
  --apk-file app-release.apk \
  --dependency-jars-dir ~/.gradle/caches/modules-2/files-2.1 \
  --dependency-jars-dir ./build/intermediates/compile_library_classes_jar \
  --app-info-file app-info.json \
  --project-path /path/to/project \
  --report-dir ./reports
```

The CLI will recursively scan the directories for `.jar` files and infer module names from file paths using Maven/Gradle repository conventions. The auto-generated dependency map JSON is saved to `<report-dir>/generated-dependency-map.json` for reference.

You can specify `--dependency-jars-dir` multiple times to scan multiple directories.

### Using an AAB bundle with device spec

```bash
java -jar ruler-cli.jar \
  --bundle-file app-release.aab \
  --dependency-map dependency-map.json \
  --device-spec-file device-spec.json \
  --app-info-file app-info.json \
  --project-path /path/to/project \
  --report-dir ./reports
```

## CLI Options

| Option | Required | Description |
|---|---|---|
| `--apk-file` | One of apk/bundle | Path to the APK file (`.apk` or `.zip` of split APKs) |
| `--bundle-file` | One of apk/bundle | Path to the AAB bundle file |
| `--dependency-map` | One of map/jars-dir | Path to the dependency map JSON file |
| `--dependency-jars-dir` | One of map/jars-dir | Directory to scan for JARs (repeatable) |
| `--app-info-file` | Yes | Path to the app info JSON file |
| `--project-path` | Yes | Project path identifier (used for default component naming) |
| `--report-dir` | Yes | Directory for output reports |
| `--device-spec-file` | No | Device specification JSON (required for AAB bundles) |
| `--mapping-file` | No | ProGuard/R8 mapping file for deobfuscation |
| `--resource-mapping-file` | No | DexGuard resource mapping file |
| `--ownership-file` | No | YAML file defining component ownership |
| `--static-components-file` | No | Static component dependencies JSON |
| `--additional-entries-file` | No | Additional APK entries JSON |
| `--unstripped-native-files` | No | Unstripped native library files (repeatable) |
| `--aapt2-tool` | No | Path to custom aapt2 binary |
| `--bloaty-tool` | No | Path to bloaty binary for native lib analysis |
| `--default-owner` | No | Default owner for unassigned components (default: `unknown`) |
| `--omit-file-breakdown` | No | Flag to omit per-file breakdown in reports |
| `--ignore-file` | No | File paths to ignore (repeatable) |
| `--download-size-threshold` | No | Max download size in bytes (verification fails if exceeded) |
| `--install-size-threshold` | No | Max install size in bytes (verification fails if exceeded) |

## Input File Formats

### App Info JSON (`--app-info-file`)

```json
{
  "applicationId": "com.example.myapp",
  "versionName": "1.2.3",
  "variantName": "release"
}
```

### Device Spec JSON (`--device-spec-file`)

Required when using `--bundle-file`:

```json
{
  "abi": "arm64-v8a",
  "locale": "en",
  "screenDensity": 480,
  "sdkVersion": 27
}
```

### Dependency Map JSON (`--dependency-map`)

Maps JAR files, assets, and resources to their owning modules:

```json
{
  "jars": [
    {
      "jar": "/path/to/gson-2.10.1.jar",
      "module": "com.google.code.gson:gson:2.10.1"
    },
    {
      "jar": "/path/to/app/classes.jar",
      "module": ":app"
    }
  ],
  "assets": [
    {
      "filename": "some_asset.txt",
      "module": ":app"
    }
  ],
  "resources": [
    {
      "filename": "res/layout/activity_main.xml",
      "module": ":app"
    }
  ]
}
```

### Ownership YAML (`--ownership-file`)

```yaml
- identifier: ":app"
  owner: app-team
- identifier: "androidx.core:core"
  owner: platform-team
- identifier: ":feature:*"
  owner: feature-team
```

## Auto-Generated Dependency Map

When using `--dependency-jars-dir`, module names are inferred from file paths:

| Directory Convention | Example Path | Inferred Module |
|---|---|---|
| Gradle cache | `files-2.1/com.google.code.gson/gson/2.10.1/<hash>/gson-2.10.1.jar` | `com.google.code.gson:gson:2.10.1` |
| Maven repository | `com/google/code/gson/gson/2.10.1/gson-2.10.1.jar` | `com.google.code.gson:gson:2.10.1` |
| Gradle build output | `mymodule/build/libs/mymodule.jar` | `mymodule` |
| Fallback | `some-lib.jar` | `some-lib` |

The generated map is written to `<report-dir>/generated-dependency-map.json` so you can inspect and refine it for future runs.

## Output

Reports are written to `--report-dir`:

- `report.json` -- Machine-readable JSON report with component-level size breakdown
- `report.html` -- Interactive HTML report for visual analysis
- `generated-dependency-map.json` -- (only when using `--dependency-jars-dir`) The auto-generated dependency map

## Size Verification

Use `--download-size-threshold` and `--install-size-threshold` to enforce size limits. The CLI will exit with a non-zero status if the total app size exceeds either threshold:

```bash
java -jar ruler-cli.jar \
  --apk-file app.apk \
  --dependency-map deps.json \
  --app-info-file app-info.json \
  --project-path /project \
  --report-dir ./reports \
  --download-size-threshold 20000000 \
  --install-size-threshold 40000000
```

## Examples

### CI pipeline: analyze and enforce size budget

```bash
java -jar ruler-cli.jar \
  --apk-file app/build/outputs/apk/release/app-release.apk \
  --dependency-jars-dir ~/.gradle/caches/modules-2/files-2.1 \
  --app-info-file config/app-info.json \
  --project-path ":app" \
  --report-dir build/reports/ruler \
  --ownership-file config/ownership.yaml \
  --download-size-threshold 15000000
```

### Analyze with ProGuard mapping for accurate class names

```bash
java -jar ruler-cli.jar \
  --apk-file app-release.apk \
  --dependency-map deps.json \
  --mapping-file app/build/outputs/mapping/release/mapping.txt \
  --app-info-file app-info.json \
  --project-path ":app" \
  --report-dir ./reports
```

## One-Command Analysis Script

The `scripts/ruler_generate_and_analyze.py` script combines dependency map generation and Ruler analysis into a single command. It inspects your Gradle project's dependency graph, locates JAR files in the Gradle cache and build outputs, generates the dependency map JSON, and runs the Ruler CLI.

Requirements: Python 3.10+, a built Gradle project (run `./gradlew assembleRelease` first).

### Generate dependency map only

```bash
python ruler-cli/scripts/ruler_generate_and_analyze.py generate \
  --project-dir /path/to/android-project \
  --app-module :app \
  --build-variant release \
  --output dependency-map.json
```

This runs `./gradlew :app:dependencies` to resolve the full dependency tree, then locates the actual JAR files in `~/.gradle/caches/` and the project's build output directories.

### Generate + analyze in one step

```bash
python ruler-cli/scripts/ruler_generate_and_analyze.py analyze \
  --project-dir /path/to/android-project \
  --app-module :app \
  --build-variant release \
  --apk-file app/build/outputs/apk/release/app-release.apk \
  --ruler-cli-jar ruler-cli/build/libs/ruler-cli-all.jar \
  --report-dir ./ruler-reports
```

This will:
1. Run Gradle to resolve all dependencies
2. Find JAR files in the Gradle cache and build directories
3. Collect resources and assets from project modules
4. Generate `dependency-map.json` and `app-info.json`
5. Run the Ruler CLI and produce HTML + JSON reports

### Script options

**`generate` subcommand:**

| Option | Default | Description |
|---|---|---|
| `--project-dir` | (required) | Root directory of the Gradle project |
| `--app-module` | `:app` | App module path |
| `--build-variant` | `release` | Build variant |
| `--gradle-home` | `~/.gradle` | Gradle home directory for cache lookups |
| `--output` | `dependency-map.json` | Output file path |
| `--app-info-output` | | Also generate app-info.json at this path |

**`analyze` subcommand:**

| Option | Default | Description |
|---|---|---|
| `--project-dir` | (required) | Root directory of the Gradle project |
| `--app-module` | `:app` | App module path |
| `--build-variant` | `release` | Build variant |
| `--apk-file` | (required) | Path to the APK file |
| `--ruler-cli-jar` | (required) | Path to the ruler-cli fat JAR |
| `--report-dir` | `./ruler-reports` | Output directory for reports |
| `--gradle-home` | `~/.gradle` | Gradle home directory |
| `--app-info-file` | | Existing app-info.json (auto-generated if omitted) |
| `--mapping-file` | | ProGuard/R8 mapping file |
| `--ownership-file` | | Ownership YAML file |
| `--device-spec-file` | | Device specification JSON |
| `--download-size-threshold` | | Max download size in bytes |
| `--install-size-threshold` | | Max install size in bytes |

### How dependency resolution works

The script resolves dependencies through these steps:

1. **Gradle dependency tree**: Runs `./gradlew :app:dependencies --configuration=releaseRuntimeClasspath` and parses the output to extract all dependency coordinates (`group:artifact:version`) and project module references.

2. **JAR location**: For each dependency, searches in order:
   - Gradle cache: `~/.gradle/caches/modules-2/files-2.1/<group>/<artifact>/<version>/`
   - Maven local: `~/.m2/repository/<group-path>/<artifact>/<version>/`

3. **Project modules**: For project dependencies (e.g., `:sample:lib`), looks for compiled JARs in:
   - `<module>/build/intermediates/compile_library_classes_jar/<variant>/classes.jar`
   - `<module>/build/intermediates/runtime_library_classes_jar/<variant>/classes.jar`
   - `<module>/build/libs/<module>.jar`

4. **Resources & assets**: Scans each project module's `src/main/res/` and `src/main/assets/` directories.

Dependencies that can't be found (e.g., Android platform libraries, AARs without extracted JARs) are reported as warnings but don't block the analysis.
