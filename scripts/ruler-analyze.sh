#!/bin/bash

# Ruler Wrapper Script
# This script automates the process of exporting dependency maps and running ruler analysis
#
# Copyright 2021 Spotify AB
# Licensed under the Apache License, Version 2.0

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
VARIANT="release"
PROJECT_DIR="."
GRADLE_CMD="./gradlew"
RULER_CLI_JAR=""
APK_FILE=""
BUNDLE_FILE=""
MAPPING_FILE=""
RESOURCE_MAPPING_FILE=""
OWNERSHIP_FILE=""
REPORT_DIR=""
DEFAULT_OWNER="unknown"
OMIT_FILE_BREAKDOWN=""

# Help function
show_help() {
    cat << EOF
Usage: $(basename "$0") [OPTIONS]

Wrapper script for Ruler that automates dependency map generation and analysis.

OPTIONS:
    -v, --variant VARIANT           Build variant to analyze (default: release)
    -p, --project-dir DIR           Project directory (default: current directory)
    -j, --ruler-cli JAR             Path to ruler-cli JAR file (required for CLI mode)
    -a, --apk-file FILE             Path to APK file for analysis
    -b, --bundle-file FILE          Path to Bundle file for analysis
    -m, --mapping-file FILE         Path to ProGuard/R8 mapping file
    -r, --resource-mapping-file FILE Path to resource mapping file
    -o, --ownership-file FILE       Path to ownership YAML file
    -d, --report-dir DIR            Output directory for reports
    --default-owner OWNER           Default owner for unattributed files (default: unknown)
    --omit-file-breakdown           Omit file-level breakdown in reports
    --gradle-only                   Only export dependency map, don't run analysis
    --cli-only                      Skip dependency map export, only run CLI analysis
    -h, --help                      Show this help message

EXAMPLES:
    # Full workflow: Export dependency map and run analysis
    $(basename "$0") --variant release --ruler-cli ./ruler-cli.jar --bundle-file app.aab

    # Only export dependency map
    $(basename "$0") --variant release --gradle-only

    # Only run CLI analysis (dependency map must exist)
    $(basename "$0") --variant release --ruler-cli ./ruler-cli.jar --cli-only --bundle-file app.aab

EOF
}

# Parse command line arguments
GRADLE_ONLY=false
CLI_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--variant)
            VARIANT="$2"
            shift 2
            ;;
        -p|--project-dir)
            PROJECT_DIR="$2"
            shift 2
            ;;
        -j|--ruler-cli)
            RULER_CLI_JAR="$2"
            shift 2
            ;;
        -a|--apk-file)
            APK_FILE="$2"
            shift 2
            ;;
        -b|--bundle-file)
            BUNDLE_FILE="$2"
            shift 2
            ;;
        -m|--mapping-file)
            MAPPING_FILE="$2"
            shift 2
            ;;
        -r|--resource-mapping-file)
            RESOURCE_MAPPING_FILE="$2"
            shift 2
            ;;
        -o|--ownership-file)
            OWNERSHIP_FILE="$2"
            shift 2
            ;;
        -d|--report-dir)
            REPORT_DIR="$2"
            shift 2
            ;;
        --default-owner)
            DEFAULT_OWNER="$2"
            shift 2
            ;;
        --omit-file-breakdown)
            OMIT_FILE_BREAKDOWN="--omit-file-breakdown"
            shift
            ;;
        --gradle-only)
            GRADLE_ONLY=true
            shift
            ;;
        --cli-only)
            CLI_ONLY=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# Validate inputs
if [[ "$GRADLE_ONLY" == false ]] && [[ -z "$RULER_CLI_JAR" ]]; then
    echo -e "${RED}Error: --ruler-cli is required unless using --gradle-only${NC}"
    exit 1
fi

if [[ "$CLI_ONLY" == false ]] && [[ "$GRADLE_ONLY" == false ]]; then
    if [[ -z "$APK_FILE" ]] && [[ -z "$BUNDLE_FILE" ]]; then
        echo -e "${YELLOW}Warning: Neither --apk-file nor --bundle-file specified. CLI analysis may fail.${NC}"
    fi
fi

# Change to project directory
cd "$PROJECT_DIR"

# Capitalize first letter of variant name for Gradle task
VARIANT_CAPITALIZED="$(tr '[:lower:]' '[:upper:]' <<< ${VARIANT:0:1})${VARIANT:1}"

# Paths
DEPENDENCY_MAP_PATH="build/outputs/ruler/${VARIANT}/dependency-map.json"
DEFAULT_REPORT_DIR="build/reports/ruler-cli/${VARIANT}"

if [[ -z "$REPORT_DIR" ]]; then
    REPORT_DIR="$DEFAULT_REPORT_DIR"
fi

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}Ruler Analysis Wrapper${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "Variant: ${VARIANT}"
echo -e "Project Directory: ${PROJECT_DIR}"
echo -e "Dependency Map: ${DEPENDENCY_MAP_PATH}"
echo -e "Report Directory: ${REPORT_DIR}"
echo -e "${GREEN}============================================${NC}"

# Step 1: Export dependency map using Gradle task
if [[ "$CLI_ONLY" == false ]]; then
    echo -e "\n${GREEN}[1/2] Exporting dependency map...${NC}"

    if ! $GRADLE_CMD "export${VARIANT_CAPITALIZED}DependencyMap"; then
        echo -e "${RED}Failed to export dependency map${NC}"
        exit 1
    fi

    if [[ ! -f "$DEPENDENCY_MAP_PATH" ]]; then
        echo -e "${RED}Dependency map file not found at: $DEPENDENCY_MAP_PATH${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Dependency map exported successfully${NC}"

    if [[ "$GRADLE_ONLY" == true ]]; then
        echo -e "\n${GREEN}Dependency map exported to: $DEPENDENCY_MAP_PATH${NC}"
        exit 0
    fi
fi

# Step 2: Run ruler-cli with the generated dependency map
echo -e "\n${GREEN}[2/2] Running Ruler analysis...${NC}"

if [[ ! -f "$DEPENDENCY_MAP_PATH" ]]; then
    echo -e "${RED}Dependency map file not found at: $DEPENDENCY_MAP_PATH${NC}"
    echo -e "${RED}Run without --cli-only first to generate it.${NC}"
    exit 1
fi

if [[ ! -f "$RULER_CLI_JAR" ]]; then
    echo -e "${RED}Ruler CLI JAR not found at: $RULER_CLI_JAR${NC}"
    exit 1
fi

# Build CLI command
CLI_CMD="java -jar \"$RULER_CLI_JAR\" \
    --dependency-map=\"$DEPENDENCY_MAP_PATH\" \
    --project-path=\"$PROJECT_DIR\" \
    --report-dir=\"$REPORT_DIR\" \
    --default-owner=\"$DEFAULT_OWNER\""

# Add optional parameters
if [[ -n "$APK_FILE" ]]; then
    CLI_CMD="$CLI_CMD --apk-file=\"$APK_FILE\""
fi

if [[ -n "$BUNDLE_FILE" ]]; then
    CLI_CMD="$CLI_CMD --bundle-file=\"$BUNDLE_FILE\""
fi

if [[ -n "$MAPPING_FILE" ]]; then
    CLI_CMD="$CLI_CMD --mapping-file=\"$MAPPING_FILE\""
fi

if [[ -n "$RESOURCE_MAPPING_FILE" ]]; then
    CLI_CMD="$CLI_CMD --resource-mapping-file=\"$RESOURCE_MAPPING_FILE\""
fi

if [[ -n "$OWNERSHIP_FILE" ]]; then
    CLI_CMD="$CLI_CMD --ownership-file=\"$OWNERSHIP_FILE\""
fi

if [[ -n "$OMIT_FILE_BREAKDOWN" ]]; then
    CLI_CMD="$CLI_CMD $OMIT_FILE_BREAKDOWN"
fi

# Create app-info.json file (required by CLI)
APP_INFO_FILE="build/outputs/ruler/${VARIANT}/app-info.json"
mkdir -p "$(dirname "$APP_INFO_FILE")"

# Extract app info from build output or create default
cat > "$APP_INFO_FILE" << EOF
{
  "applicationId": "com.example.app",
  "versionName": "1.0",
  "variantName": "$VARIANT"
}
EOF

CLI_CMD="$CLI_CMD --app-info-file=\"$APP_INFO_FILE\""

# Execute CLI command
echo -e "Running: $CLI_CMD\n"
if eval "$CLI_CMD"; then
    echo -e "\n${GREEN}✓ Ruler analysis completed successfully${NC}"
    echo -e "${GREEN}Reports available at: $REPORT_DIR${NC}"
else
    echo -e "\n${RED}✗ Ruler analysis failed${NC}"
    exit 1
fi
