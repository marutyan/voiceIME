#!/usr/bin/env bash
# VoiceIME のリリース実行ファイルをビルドし、メニューバー常駐用の .app バンドルへ包んで ad-hoc 署名する。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$APP_DIR/.." && pwd)"

APP_NAME="VoiceIME"
BUNDLE_ID="${VOICEIME_BUNDLE_ID:-com.voiceime.app}"
VERSION="${VOICEIME_VERSION:-0.1.0}"
BUILD_NUMBER="${VOICEIME_BUILD_NUMBER:-1}"
OUT_DIR="${VOICEIME_OUT_DIR:-$APP_DIR/build}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --out-dir)
            OUT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "使い方: $0 [--out-dir <出力先ディレクトリ>]"
            exit 0
            ;;
        *)
            echo "不明な引数です: $1" >&2
            exit 1
            ;;
    esac
done

SWIFT_FLAGS=()
if [[ -n "${VOICEIME_SWIFT_FLAGS:-}" ]]; then
    # 制限付き環境（CI等）から追加の swift build フラグを渡す場合に使う。
    read -r -a SWIFT_FLAGS <<< "$VOICEIME_SWIFT_FLAGS"
fi

echo "[1/4] Swiftリリースビルドを実行します..."
swift build -c release --package-path "$APP_DIR" ${SWIFT_FLAGS[@]+"${SWIFT_FLAGS[@]}"}

BIN_DIR="$(swift build -c release --package-path "$APP_DIR" ${SWIFT_FLAGS[@]+"${SWIFT_FLAGS[@]}"} --show-bin-path)"
EXECUTABLE="$BIN_DIR/$APP_NAME"
if [[ ! -x "$EXECUTABLE" ]]; then
    echo "ビルド済み実行ファイルが見つかりません: $EXECUTABLE" >&2
    exit 1
fi

APP_BUNDLE="$OUT_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_BUNDLE/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

echo "[2/4] .app バンドルを組み立てます: $APP_BUNDLE"
rm -rf "$APP_BUNDLE"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
cp "$EXECUTABLE" "$MACOS_DIR/$APP_NAME"
chmod +x "$MACOS_DIR/$APP_NAME"
printf 'APPL????' > "$CONTENTS_DIR/PkgInfo"

# XML特殊文字をエスケープしてプロジェクトルートを Info.plist へ埋め込む。
ESCAPED_REPO_ROOT="${REPO_ROOT//&/&amp;}"
ESCAPED_REPO_ROOT="${ESCAPED_REPO_ROOT//</&lt;}"
ESCAPED_REPO_ROOT="${ESCAPED_REPO_ROOT//>/&gt;}"

cat > "$CONTENTS_DIR/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>ja</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>${BUNDLE_ID}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleVersion</key>
    <string>${BUILD_NUMBER}</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>押している間の音声を録音し、手元の認識エンジンで文字起こしと整形を行うためにマイクを使用します。</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>VoiceIMEProjectRoot</key>
    <string>${ESCAPED_REPO_ROOT}</string>
</dict>
</plist>
EOF

echo "[3/4] ad-hoc 署名を適用します..."
codesign --force --deep --sign - "$APP_BUNDLE"

echo "[4/4] 署名を検証します..."
codesign --verify --verbose=2 "$APP_BUNDLE"

echo "完了: $APP_BUNDLE"
