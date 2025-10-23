#!/bin/bash
# Code signing script for CLI AI Coder releases
# This script handles signing of binaries and packages for distribution

set -e

# Configuration
CERTIFICATE_FILE="${CERTIFICATE_FILE:-codesign.p12}"
CERTIFICATE_PASSWORD="${CERTIFICATE_PASSWORD:-}"
APPLE_ID="${APPLE_ID:-}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on macOS for code signing
if [[ "$OSTYPE" != "darwin"* ]]; then
    log_warn "Code signing is only supported on macOS"
    exit 0
fi

# Check for required tools
command -v codesign >/dev/null 2>&1 || {
    log_error "codesign command not found. Install Xcode command line tools."
    exit 1
}

# Sign macOS binary
sign_macos_binary() {
    local binary_path="$1"
    local entitlements_file="$2"

    log_info "Signing macOS binary: $binary_path"

    if [[ -n "$entitlements_file" && -f "$entitlements_file" ]]; then
        codesign --force --verify --verbose --sign "$CERTIFICATE_FILE" \
                 --entitlements "$entitlements_file" "$binary_path"
    else
        codesign --force --verify --verbose --sign "$CERTIFICATE_FILE" "$binary_path"
    fi

    log_info "Binary signed successfully"
}

# Sign Windows binary (using signtool)
sign_windows_binary() {
    local binary_path="$1"

    log_info "Signing Windows binary: $binary_path"

    if ! command -v signtool >/dev/null 2>&1; then
        log_error "signtool not found. Install Windows SDK."
        exit 1
    fi

    signtool sign //f "$CERTIFICATE_FILE" //p "$CERTIFICATE_PASSWORD" "$binary_path"
    log_info "Windows binary signed successfully"
}

# Notarize macOS app with Apple
notarize_macos_app() {
    local app_path="$1"

    log_info "Notarizing macOS app: $app_path"

    if [[ -z "$APPLE_ID" ]]; then
        log_error "APPLE_ID environment variable not set"
        exit 1
    fi

    # Create zip for notarization
    ditto -c -k --keepParent "$app_path" "notarization.zip"

    # Submit for notarization
    xcrun notarytool submit "notarization.zip" \
        --apple-id "$APPLE_ID" \
        --team-id "$APPLE_TEAM_ID" \
        --wait

    # Staple notarization ticket
    xcrun stapler staple "$app_path"

    # Clean up
    rm "notarization.zip"

    log_info "App notarized successfully"
}

# Sign package/disk image
sign_package() {
    local package_path="$1"

    log_info "Signing package: $package_path"

    if [[ "${package_path##*.}" == "dmg" ]]; then
        # Sign DMG
        codesign --force --verify --verbose --sign "$CERTIFICATE_FILE" "$package_path"
    elif [[ "${package_path##*.}" == "pkg" ]]; then
        # Sign PKG
        productsign --sign "$CERTIFICATE_FILE" "$package_path" "${package_path}.signed"
        mv "${package_path}.signed" "$package_path"
    fi

    log_info "Package signed successfully"
}

# Main signing function
main() {
    local target="$1"
    local platform="$2"

    if [[ -z "$target" ]]; then
        log_error "Usage: $0 <target_path> [platform]"
        log_error "Platforms: macos, windows, linux"
        exit 1
    fi

    case "$platform" in
        macos)
            sign_macos_binary "$target"
            notarize_macos_app "$target"
            ;;
        windows)
            sign_windows_binary "$target"
            ;;
        linux)
            log_info "Linux binaries typically don't need code signing"
            ;;
        *)
            log_error "Unsupported platform: $platform"
            exit 1
            ;;
    esac
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi