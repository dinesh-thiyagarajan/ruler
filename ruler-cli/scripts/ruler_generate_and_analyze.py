#!/usr/bin/env python3
"""
Ruler CLI - Dependency Map Generator & Analyzer

Generates the dependency-map.json required by the Ruler CLI by inspecting
a Gradle project's dependency graph and locating the actual JAR files.
Can also run the full Ruler analysis in a single command.

Usage:
    # Generate dependency map only
    python ruler_generate_and_analyze.py generate \
        --project-dir /path/to/android-project \
        --app-module :app \
        --build-variant release \
        --output dependency-map.json

    # Generate dependency map + run Ruler analysis
    python ruler_generate_and_analyze.py analyze \
        --project-dir /path/to/android-project \
        --app-module :app \
        --build-variant release \
        --apk-file app/build/outputs/apk/release/app-release.apk \
        --report-dir ./ruler-reports \
        --ruler-cli-jar ruler-cli-all.jar
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional


def run_gradle_dependencies(project_dir: str, app_module: str, configuration: str) -> str:
    """Run Gradle dependencies task and return the output."""
    gradlew = os.path.join(project_dir, "gradlew")
    if not os.path.isfile(gradlew):
        gradlew = os.path.join(project_dir, "gradlew.bat")
    if not os.path.isfile(gradlew):
        raise FileNotFoundError(f"Cannot find gradlew in {project_dir}")

    cmd = [
        gradlew,
        f"{app_module}:dependencies",
        f"--configuration={configuration}",
        "--console=plain",
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    if result.returncode != 0:
        print(f"Gradle dependencies failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def parse_dependency_tree(output: str) -> list[dict]:
    """
    Parse Gradle dependency tree output to extract dependency identifiers.

    Returns a list of dicts: [{"group": ..., "artifact": ..., "version": ...}, ...]
    Also includes project dependencies: [{"project": ":module:path"}, ...]
    """
    deps = []
    seen = set()

    # Match lines like: +--- com.google.code.gson:gson:2.10.1
    # or:               \--- org.jetbrains.kotlin:kotlin-stdlib:1.9.10 (*)
    # or:               +--- project :sample:lib
    dep_pattern = re.compile(
        r"[+\\|]\-\-\-\s+"
        r"(?:project\s+(\S+)"  # project dependency
        r"|(\S+):(\S+):(\S+))"  # external dependency group:artifact:version
    )

    # Also capture version resolution: com.example:lib:1.0 -> 1.1
    version_arrow = re.compile(r"(\S+):(\S+):(\S+)\s+->\s+(\S+)")

    for line in output.splitlines():
        # Check for version arrow resolution first
        m = version_arrow.search(line)
        if m:
            group, artifact, _, resolved_version = m.groups()
            key = f"{group}:{artifact}:{resolved_version}"
            if key not in seen:
                seen.add(key)
                deps.append({
                    "group": group,
                    "artifact": artifact,
                    "version": resolved_version,
                })
            continue

        m = dep_pattern.search(line)
        if m:
            project_path = m.group(1)
            if project_path:
                key = f"project:{project_path}"
                if key not in seen:
                    seen.add(key)
                    deps.append({"project": project_path})
            else:
                group, artifact, version = m.group(2), m.group(3), m.group(4)
                # Strip trailing markers like (*), (c), (n)
                version = re.sub(r"\s*\(.*\)$", "", version)
                key = f"{group}:{artifact}:{version}"
                if key not in seen:
                    seen.add(key)
                    deps.append({
                        "group": group,
                        "artifact": artifact,
                        "version": version,
                    })

    return deps


def find_jar_in_gradle_cache(group: str, artifact: str, version: str,
                              gradle_home: Optional[str] = None) -> Optional[str]:
    """Find a JAR file in the Gradle cache for a given dependency."""
    if gradle_home is None:
        gradle_home = os.path.join(os.path.expanduser("~"), ".gradle")

    cache_dir = os.path.join(gradle_home, "caches", "modules-2", "files-2.1",
                             group, artifact, version)

    if not os.path.isdir(cache_dir):
        return None

    # Walk the hash directories looking for a JAR
    for root, _, files in os.walk(cache_dir):
        for f in files:
            if f.endswith(".jar") and not f.endswith("-sources.jar") and not f.endswith("-javadoc.jar"):
                return os.path.join(root, f)
    return None


def find_jar_in_maven_local(group: str, artifact: str, version: str) -> Optional[str]:
    """Find a JAR file in Maven local repository."""
    m2_repo = os.path.join(os.path.expanduser("~"), ".m2", "repository")
    group_path = group.replace(".", os.sep)
    jar_dir = os.path.join(m2_repo, group_path, artifact, version)

    if not os.path.isdir(jar_dir):
        return None

    jar_name = f"{artifact}-{version}.jar"
    jar_path = os.path.join(jar_dir, jar_name)
    if os.path.isfile(jar_path):
        return jar_path

    # Also check for AAR (Android libraries)
    aar_name = f"{artifact}-{version}.aar"
    aar_path = os.path.join(jar_dir, aar_name)
    if os.path.isfile(aar_path):
        return aar_path

    return None


def find_project_jar(project_dir: str, module_path: str, build_variant: str) -> Optional[str]:
    """Find the compiled JAR/classes for a project module."""
    # Convert :sample:lib to sample/lib
    module_dir = module_path.lstrip(":").replace(":", os.sep)
    module_abs = os.path.join(project_dir, module_dir)

    if not os.path.isdir(module_abs):
        return None

    # Common locations for compiled classes
    candidates = [
        os.path.join(module_abs, "build", "intermediates",
                     "compile_library_classes_jar", build_variant, "classes.jar"),
        os.path.join(module_abs, "build", "intermediates",
                     "compile_library_classes_jar", build_variant, "bundleLibCompileToJar", "classes.jar"),
        os.path.join(module_abs, "build", "intermediates",
                     "runtime_library_classes_jar", build_variant, "classes.jar"),
        os.path.join(module_abs, "build", "libs", f"{os.path.basename(module_dir)}.jar"),
    ]

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    # Fallback: search build/intermediates for any classes.jar
    intermediates = os.path.join(module_abs, "build", "intermediates")
    if os.path.isdir(intermediates):
        for root, _, files in os.walk(intermediates):
            if build_variant in root:
                for f in files:
                    if f == "classes.jar":
                        return os.path.join(root, f)

    return None


def find_resources_and_assets(project_dir: str, module_path: str) -> tuple[list, list]:
    """Find resources and assets for a project module."""
    module_dir = module_path.lstrip(":").replace(":", os.sep)
    module_abs = os.path.join(project_dir, module_dir)

    resources = []
    assets = []

    # Scan res directory
    res_dir = os.path.join(module_abs, "src", "main", "res")
    if os.path.isdir(res_dir):
        for root, _, files in os.walk(res_dir):
            for f in files:
                rel_path = os.path.relpath(os.path.join(root, f), os.path.join(module_abs, "src", "main"))
                resources.append({"filename": rel_path, "module": module_path})

    # Scan assets directory
    assets_dir = os.path.join(module_abs, "src", "main", "assets")
    if os.path.isdir(assets_dir):
        for root, _, files in os.walk(assets_dir):
            for f in files:
                rel_path = os.path.relpath(os.path.join(root, f), os.path.join(module_abs, "src", "main", "assets"))
                assets.append({"filename": rel_path, "module": module_path})

    return resources, assets


def generate_dependency_map(
    project_dir: str,
    app_module: str,
    build_variant: str,
    gradle_home: Optional[str] = None,
) -> dict:
    """
    Generate the full dependency map by:
    1. Running Gradle to get the dependency tree
    2. Locating JAR files for each dependency
    3. Scanning for resources and assets
    """
    configuration = f"{build_variant}RuntimeClasspath"
    print(f"\n=== Resolving dependencies for {app_module} ({configuration}) ===\n")

    output = run_gradle_dependencies(project_dir, app_module, configuration)
    deps = parse_dependency_tree(output)

    print(f"\nFound {len(deps)} unique dependencies")

    jars = []
    all_resources = []
    all_assets = []
    missing = []

    for dep in deps:
        if "project" in dep:
            # Project module dependency
            module_path = dep["project"]
            jar_path = find_project_jar(project_dir, module_path, build_variant)
            if jar_path:
                jars.append({"jar": jar_path, "module": module_path})
                print(f"  [OK] {module_path} -> {jar_path}")
            else:
                missing.append(f"project {module_path}")
                print(f"  [MISS] {module_path} (no compiled JAR found)")

            # Also collect resources and assets
            resources, assets = find_resources_and_assets(project_dir, module_path)
            all_resources.extend(resources)
            all_assets.extend(assets)
        else:
            # External dependency
            group = dep["group"]
            artifact = dep["artifact"]
            version = dep["version"]
            module_id = f"{group}:{artifact}:{version}"

            jar_path = find_jar_in_gradle_cache(group, artifact, version, gradle_home)
            if not jar_path:
                jar_path = find_jar_in_maven_local(group, artifact, version)

            if jar_path:
                jars.append({"jar": jar_path, "module": module_id})
                print(f"  [OK] {module_id} -> {os.path.basename(jar_path)}")
            else:
                missing.append(module_id)
                print(f"  [MISS] {module_id} (JAR not found in cache)")

    # Also handle the app module itself
    app_jar = find_project_jar(project_dir, app_module, build_variant)
    if app_jar:
        jars.append({"jar": app_jar, "module": app_module})
        print(f"  [OK] {app_module} (app) -> {app_jar}")

    app_resources, app_assets = find_resources_and_assets(project_dir, app_module)
    all_resources.extend(app_resources)
    all_assets.extend(app_assets)

    if missing:
        print(f"\nWarning: {len(missing)} dependencies not found (may be AARs or platform libs):")
        for m in missing:
            print(f"  - {m}")

    print(f"\nDependency map: {len(jars)} JARs, {len(all_resources)} resources, {len(all_assets)} assets")

    return {
        "jars": jars,
        "resources": all_resources,
        "assets": all_assets,
    }


def generate_app_info(project_dir: str, app_module: str, build_variant: str) -> dict:
    """Generate a basic app-info.json from project configuration."""
    module_dir = app_module.lstrip(":").replace(":", os.sep)
    module_abs = os.path.join(project_dir, module_dir)

    # Try to read applicationId from build.gradle or build.gradle.kts
    app_id = "com.example.app"
    version_name = "1.0.0"

    for build_file_name in ["build.gradle.kts", "build.gradle"]:
        build_file = os.path.join(module_abs, build_file_name)
        if os.path.isfile(build_file):
            with open(build_file) as f:
                content = f.read()

            app_id_match = re.search(r'applicationId\s*[=( ]\s*["\']([^"\']+)["\']', content)
            if app_id_match:
                app_id = app_id_match.group(1)

            version_match = re.search(r'versionName\s*[=( ]\s*["\']([^"\']+)["\']', content)
            if version_match:
                version_name = version_match.group(1)
            break

    return {
        "applicationId": app_id,
        "versionName": version_name,
        "variantName": build_variant,
    }


def run_ruler_cli(
    ruler_jar: str,
    dependency_map: str,
    apk_file: str,
    app_info_file: str,
    project_path: str,
    report_dir: str,
    extra_args: Optional[list[str]] = None,
):
    """Run the Ruler CLI with the generated dependency map."""
    cmd = [
        "java", "-jar", ruler_jar,
        "--dependency-map", dependency_map,
        "--apk-file", apk_file,
        "--app-info-file", app_info_file,
        "--project-path", project_path,
        "--report-dir", report_dir,
    ]
    if extra_args:
        cmd.extend(extra_args)

    print(f"\n=== Running Ruler CLI ===\n")
    print(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=os.path.dirname(ruler_jar) or ".")
    return result.returncode


def cmd_generate(args):
    """Handle the 'generate' subcommand."""
    dep_map = generate_dependency_map(
        project_dir=args.project_dir,
        app_module=args.app_module,
        build_variant=args.build_variant,
        gradle_home=args.gradle_home,
    )

    output_path = args.output
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(dep_map, f, indent=2)

    print(f"\nDependency map written to: {output_path}")

    if args.app_info_output:
        app_info = generate_app_info(args.project_dir, args.app_module, args.build_variant)
        with open(args.app_info_output, "w") as f:
            json.dump(app_info, f, indent=2)
        print(f"App info written to: {args.app_info_output}")


def cmd_analyze(args):
    """Handle the 'analyze' subcommand - generate dep map + run Ruler."""
    # Step 1: Generate dependency map
    dep_map = generate_dependency_map(
        project_dir=args.project_dir,
        app_module=args.app_module,
        build_variant=args.build_variant,
        gradle_home=args.gradle_home,
    )

    report_dir = args.report_dir
    os.makedirs(report_dir, exist_ok=True)

    dep_map_path = os.path.join(report_dir, "generated-dependency-map.json")
    with open(dep_map_path, "w") as f:
        json.dump(dep_map, f, indent=2)
    print(f"\nDependency map written to: {dep_map_path}")

    # Step 2: Generate app-info.json
    app_info = generate_app_info(args.project_dir, args.app_module, args.build_variant)
    app_info_path = args.app_info_file
    if not app_info_path:
        app_info_path = os.path.join(report_dir, "app-info.json")
        with open(app_info_path, "w") as f:
            json.dump(app_info, f, indent=2)
        print(f"App info written to: {app_info_path}")

    # Step 3: Run Ruler CLI
    extra_args = []
    if args.mapping_file:
        extra_args.extend(["--mapping-file", args.mapping_file])
    if args.ownership_file:
        extra_args.extend(["--ownership-file", args.ownership_file])
    if args.device_spec_file:
        extra_args.extend(["--device-spec-file", args.device_spec_file])
    if args.download_size_threshold:
        extra_args.extend(["--download-size-threshold", str(args.download_size_threshold)])
    if args.install_size_threshold:
        extra_args.extend(["--install-size-threshold", str(args.install_size_threshold)])

    rc = run_ruler_cli(
        ruler_jar=args.ruler_cli_jar,
        dependency_map=dep_map_path,
        apk_file=args.apk_file,
        app_info_file=app_info_path,
        project_path=args.app_module,
        report_dir=report_dir,
        extra_args=extra_args,
    )

    if rc == 0:
        print(f"\nAnalysis complete. Reports written to: {report_dir}")
        print(f"  - {os.path.join(report_dir, 'report.json')}")
        print(f"  - {os.path.join(report_dir, 'report.html')}")
    else:
        print(f"\nRuler CLI exited with code {rc}", file=sys.stderr)
        sys.exit(rc)


def main():
    parser = argparse.ArgumentParser(
        description="Ruler - Generate dependency maps and analyze Android app size",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate dependency map only
  %(prog)s generate \\
      --project-dir ./my-android-project \\
      --app-module :app \\
      --output dependency-map.json

  # Generate dependency map + run full analysis
  %(prog)s analyze \\
      --project-dir ./my-android-project \\
      --app-module :app \\
      --apk-file app/build/outputs/apk/release/app-release.apk \\
      --ruler-cli-jar ruler-cli-all.jar \\
      --report-dir ./ruler-reports
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- generate subcommand ---
    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate a dependency-map.json from a Gradle project",
    )
    gen_parser.add_argument("--project-dir", required=True,
                            help="Root directory of the Gradle project")
    gen_parser.add_argument("--app-module", default=":app",
                            help="App module path (default: :app)")
    gen_parser.add_argument("--build-variant", default="release",
                            help="Build variant (default: release)")
    gen_parser.add_argument("--gradle-home",
                            help="Gradle home directory (default: ~/.gradle)")
    gen_parser.add_argument("--output", default="dependency-map.json",
                            help="Output file path (default: dependency-map.json)")
    gen_parser.add_argument("--app-info-output",
                            help="Also generate app-info.json at this path")
    gen_parser.set_defaults(func=cmd_generate)

    # --- analyze subcommand ---
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Generate dependency map and run Ruler analysis in one step",
    )
    analyze_parser.add_argument("--project-dir", required=True,
                                help="Root directory of the Gradle project")
    analyze_parser.add_argument("--app-module", default=":app",
                                help="App module path (default: :app)")
    analyze_parser.add_argument("--build-variant", default="release",
                                help="Build variant (default: release)")
    analyze_parser.add_argument("--gradle-home",
                                help="Gradle home directory (default: ~/.gradle)")
    analyze_parser.add_argument("--apk-file", required=True,
                                help="Path to the APK file to analyze")
    analyze_parser.add_argument("--ruler-cli-jar", required=True,
                                help="Path to the ruler-cli fat JAR")
    analyze_parser.add_argument("--report-dir", default="./ruler-reports",
                                help="Directory for reports (default: ./ruler-reports)")
    analyze_parser.add_argument("--app-info-file",
                                help="Path to existing app-info.json (auto-generated if omitted)")
    analyze_parser.add_argument("--mapping-file",
                                help="ProGuard/R8 mapping file")
    analyze_parser.add_argument("--ownership-file",
                                help="Ownership YAML file")
    analyze_parser.add_argument("--device-spec-file",
                                help="Device specification JSON file")
    analyze_parser.add_argument("--download-size-threshold", type=int,
                                help="Max download size in bytes")
    analyze_parser.add_argument("--install-size-threshold", type=int,
                                help="Max install size in bytes")
    analyze_parser.set_defaults(func=cmd_analyze)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
