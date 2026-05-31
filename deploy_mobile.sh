#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/mobile/app"
ADB="$HOME/Android/Sdk/platform-tools/adb"
APK="$APP_DIR/android/app/build/outputs/apk/debug/app-debug.apk"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
fail() { echo -e "${RED}✗${NC}  $*"; exit 1; }
step() { echo -e "\n${BOLD}▶ $*${NC}"; }

# ── 1. Check Android SDK / ADB ────────────────────────────────────────────────
step "Checking tools"

if [[ ! -f "$ADB" ]]; then
  fail "ADB not found at $ADB
     Install Android Studio and let it set up the SDK, or install the
     command-line tools and place them at ~/Android/Sdk/platform-tools/"
fi
ok "ADB found"

# ── 2. Find Java (Android Studio's bundled JDK in nix store) ─────────────────
JAVAC=$(find /nix/store -maxdepth 4 -name "javac" 2>/dev/null | grep "android-studio.*unwrapped" | head -1)
if [[ -z "$JAVAC" ]]; then
  fail "Android Studio JDK not found in /nix/store.
     Is Android Studio installed via nixpkgs? (nix-env -iA nixpkgs.android-studio)"
fi
JAVA_HOME="$(dirname "$(dirname "$JAVAC")")"
ok "Java found: $JAVA_HOME"

# ── 3. Check phone is connected and authorised ────────────────────────────────
step "Checking device"

DEVICES=$("$ADB" devices 2>/dev/null | tail -n +2 | grep -v '^$')

if [[ -z "$DEVICES" ]]; then
  fail "No Android device detected.
     • Connect your phone via USB
     • Enable Developer Options (tap Build Number 7 times)
     • Enable USB Debugging in Developer Options"
fi

UNAUTHORIZED=$(echo "$DEVICES" | grep "unauthorized" || true)
OFFLINE=$(echo "$DEVICES" | grep "offline" || true)
READY=$(echo "$DEVICES" | grep "device$" || true)

if [[ -n "$UNAUTHORIZED" ]]; then
  fail "Device connected but not authorised.
     Check your phone for the 'Allow USB debugging?' dialog and tap Allow."
fi

if [[ -n "$OFFLINE" ]]; then
  fail "Device is offline. Try unplugging and reconnecting, then run:
     $ADB kill-server && $ADB start-server"
fi

if [[ -z "$READY" ]]; then
  fail "Device detected but not ready (state: $(echo "$DEVICES" | awk '{print $2}'))."
fi

DEVICE_MODEL=$("$ADB" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || echo "Unknown")
ok "Device ready: $DEVICE_MODEL"

# ── 4. Build web assets ───────────────────────────────────────────────────────
step "Building web assets (npm)"
cd "$APP_DIR"
npm run build

# ── 5. Regenerate Android icons from SVG source ───────────────────────────────
step "Generating Android icons (from resources/icon.svg)"
npx @capacitor/assets generate --android \
  --iconBackgroundColor '#12151f' \
  --iconBackgroundColorDark '#12151f'

# ── 6. Sync to Android project ────────────────────────────────────────────────
step "Syncing to Android project (cap sync)"
npx cap sync android

# ── 7. Build APK ─────────────────────────────────────────────────────────────
step "Building APK (Gradle)"
cd "$APP_DIR/android"
JAVA_HOME="$JAVA_HOME" \
ANDROID_HOME="$HOME/Android/Sdk" \
ANDROID_SDK_ROOT="$HOME/Android/Sdk" \
./gradlew assembleDebug

# ── 8. Install ────────────────────────────────────────────────────────────────
step "Installing APK on $DEVICE_MODEL"
"$ADB" install -r "$APK"

echo -e "\n${GREEN}${BOLD}Done.${NC} ProjectFlow Mobile installed on $DEVICE_MODEL."
