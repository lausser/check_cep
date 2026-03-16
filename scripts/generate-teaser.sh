#!/usr/bin/env bash
# generate-teaser.sh — Record 4-scene Playwright teaser and convert to animated GIF.
#
# Scenes:
#   1. Passing login test with vision highlights + result highlight
#   2. Playwright HTML report for the passing test
#   3. Failing login test with soft assertion mismatch
#   4. Playwright HTML report drilled down to the error
#
# Title cards (dark background, white text) separate each scene.
#
# Prerequisites: ffmpeg, built container image (make test-image)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIXTURE="tc_vision_example_login"
FIXTURE_DIR="$REPO_ROOT/tests/fixtures/$FIXTURE"
TEASER_DIR="$REPO_ROOT/scripts/teaser"
GIF_OUTPUT="$REPO_ROOT/docs/teaser.gif"
CEP_IMAGE="${CEP_IMAGE:-check_cep:test}"

# ffmpeg GIF parameters
GIF_FPS=10
GIF_WIDTH=640
GIF_COLORS=128

# Check prerequisites
if ! command -v ffmpeg &>/dev/null; then
    echo "ERROR: ffmpeg is required but not installed." >&2
    exit 1
fi

if ! podman image exists "$CEP_IMAGE" 2>/dev/null; then
    echo "ERROR: Container image '$CEP_IMAGE' not found. Run 'make test-image' first." >&2
    exit 1
fi

# Detect available H.264 encoder
ENCODERS=$(ffmpeg -encoders 2>/dev/null || true)
H264_ENCODER=""
for enc in libx264 libopenh264; do
    if echo "$ENCODERS" | grep -q "$enc"; then
        H264_ENCODER="$enc"
        break
    fi
done
if [ -z "$H264_ENCODER" ]; then
    echo "ERROR: No H.264 encoder found (need libx264 or libopenh264)." >&2
    exit 1
fi

# Create temp dirs
WORK_DIR=$(mktemp -d)
PASS_TEST_DIR="$WORK_DIR/pass-tests"
PASS_RESULT_DIR="$WORK_DIR/pass-results"
FAIL_TEST_DIR="$WORK_DIR/fail-tests"
FAIL_RESULT_DIR="$WORK_DIR/fail-results"
ASSEMBLY_DIR="$WORK_DIR/assembly"

mkdir -p "$PASS_TEST_DIR" "$PASS_RESULT_DIR" "$FAIL_TEST_DIR" "$FAIL_RESULT_DIR" "$ASSEMBLY_DIR"
chmod 777 "$PASS_RESULT_DIR" "$FAIL_RESULT_DIR"
chmod 755 "$WORK_DIR" "$PASS_TEST_DIR" "$FAIL_TEST_DIR"

cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

# --- Helper: setup test directory ---
setup_test_dir() {
    local test_dir="$1"
    local test_file="$2"
    local grep_pattern="$3"
    cp -r "$FIXTURE_DIR"/functions "$FIXTURE_DIR"/assets "$FIXTURE_DIR"/pages "$test_dir/"
    cp "$test_file" "$test_dir/"
    cat > "$test_dir/playwright.config.ts" << CFGEOF
import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.',
  timeout: 60000,
  grep: /$grep_pattern/,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
    video: { mode: 'on', size: { width: 1280, height: 720 } },
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
CFGEOF
}

# --- Phase A: Record test runs ---

echo "Scene 1: Recording passing test..."
setup_test_dir "$PASS_TEST_DIR" "$TEASER_DIR/teaser-pass.test.ts" "teaser pass"
OMD_ROOT="$WORK_DIR" OMD_SITE=testsite \
    CEP_SLOW_MO=600 CEP_VISION_HIGHLIGHT_MS=800 \
    python3 "$REPO_ROOT/src/check_cep" \
    --host-name testhost --service-description teaser \
    --image "$CEP_IMAGE" --probe-location local \
    --test-source local --result-dest local \
    --test-dir "$PASS_TEST_DIR" --result-dir "$PASS_RESULT_DIR" \
    --timeout 120 >/dev/null 2>&1

echo "Scene 3: Recording failing test..."
setup_test_dir "$FAIL_TEST_DIR" "$TEASER_DIR/teaser-fail.test.ts" "teaser fail"
OMD_ROOT="$WORK_DIR" OMD_SITE=testsite \
    CEP_SLOW_MO=600 CEP_VISION_HIGHLIGHT_MS=800 \
    python3 "$REPO_ROOT/src/check_cep" \
    --host-name testhost --service-description teaser \
    --image "$CEP_IMAGE" --probe-location local \
    --test-source local --result-dest local \
    --test-dir "$FAIL_TEST_DIR" --result-dir "$FAIL_RESULT_DIR" \
    --timeout 120 >/dev/null 2>&1 || true  # Expected to fail (exit 2)

# Find recorded videos
PASS_VIDEO=$(find "$PASS_RESULT_DIR" -name "video.webm" | head -1)
FAIL_VIDEO=$(find "$FAIL_RESULT_DIR" -name "video.webm" | head -1)
if [ -z "$PASS_VIDEO" ]; then
    echo "ERROR: No video.webm found for passing test." >&2; exit 1
fi
if [ -z "$FAIL_VIDEO" ]; then
    echo "ERROR: No video.webm found for failing test." >&2; exit 1
fi

# --- Phase B: Record report navigation ---

PASS_REPORT_VIDEO_DIR="$WORK_DIR/pass-report-video"
FAIL_REPORT_VIDEO_DIR="$WORK_DIR/fail-report-video"
mkdir -p "$PASS_REPORT_VIDEO_DIR" "$FAIL_REPORT_VIDEO_DIR"
chmod 777 "$PASS_REPORT_VIDEO_DIR" "$FAIL_REPORT_VIDEO_DIR"

echo "Scene 2: Recording pass report navigation..."
podman run --rm \
    -v "$PASS_RESULT_DIR/playwright-report:/home/pwuser/report:z" \
    -v "$PASS_REPORT_VIDEO_DIR:/home/pwuser/videos:z" \
    -v "$TEASER_DIR/record-report.js:/home/pwuser/record-report.js:z" \
    "$CEP_IMAGE" \
    node /home/pwuser/record-report.js \
        --report-dir /home/pwuser/report \
        --video-dir /home/pwuser/videos \
        --test-name "teaser pass" 2>/dev/null

echo "Scene 4: Recording fail report navigation..."
podman run --rm \
    -v "$FAIL_RESULT_DIR/playwright-report:/home/pwuser/report:z" \
    -v "$FAIL_REPORT_VIDEO_DIR:/home/pwuser/videos:z" \
    -v "$TEASER_DIR/record-report.js:/home/pwuser/record-report.js:z" \
    "$CEP_IMAGE" \
    node /home/pwuser/record-report.js \
        --report-dir /home/pwuser/report \
        --video-dir /home/pwuser/videos \
        --test-name "teaser fail" \
        --show-errors 2>/dev/null

PASS_REPORT_VIDEO=$(find "$PASS_REPORT_VIDEO_DIR" -name "*.webm" | head -1)
FAIL_REPORT_VIDEO=$(find "$FAIL_REPORT_VIDEO_DIR" -name "*.webm" | head -1)
if [ -z "$PASS_REPORT_VIDEO" ]; then
    echo "ERROR: No video found for pass report recording." >&2; exit 1
fi
if [ -z "$FAIL_REPORT_VIDEO" ]; then
    echo "ERROR: No video found for fail report recording." >&2; exit 1
fi

# --- Phase C: Assembly ---

echo "Generating title cards..."
for title in "Passing Test" "Test Report" "Failing Test" "Error Details"; do
    slug=$(echo "$title" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
    ffmpeg -y -f lavfi -i "color=c=0x1a1a2e:s=1280x720:d=1:r=25" \
        -vf "drawtext=text='$title':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2:font=DejaVu Sans" \
        -c:v "$H264_ENCODER" -pix_fmt yuv420p -t 1 \
        "$ASSEMBLY_DIR/title-$slug.mp4" 2>/dev/null
done

echo "Normalizing videos..."
ffmpeg -y -i "$PASS_VIDEO"         -c:v "$H264_ENCODER" -pix_fmt yuv420p -r 25 -s 1280x720 -an "$ASSEMBLY_DIR/scene-pass.mp4" 2>/dev/null
ffmpeg -y -i "$FAIL_VIDEO"         -c:v "$H264_ENCODER" -pix_fmt yuv420p -r 25 -s 1280x720 -an "$ASSEMBLY_DIR/scene-fail.mp4" 2>/dev/null
ffmpeg -y -i "$PASS_REPORT_VIDEO"  -c:v "$H264_ENCODER" -pix_fmt yuv420p -r 25 -s 1280x720 -an "$ASSEMBLY_DIR/report-pass.mp4" 2>/dev/null
ffmpeg -y -i "$FAIL_REPORT_VIDEO"  -c:v "$H264_ENCODER" -pix_fmt yuv420p -r 25 -s 1280x720 -an "$ASSEMBLY_DIR/report-fail.mp4" 2>/dev/null

echo "Concatenating segments..."
cat > "$ASSEMBLY_DIR/filelist.txt" << EOF
file 'title-passing-test.mp4'
file 'scene-pass.mp4'
file 'title-test-report.mp4'
file 'report-pass.mp4'
file 'title-failing-test.mp4'
file 'scene-fail.mp4'
file 'title-error-details.mp4'
file 'report-fail.mp4'
EOF
ffmpeg -y -f concat -safe 0 -i "$ASSEMBLY_DIR/filelist.txt" -c copy "$ASSEMBLY_DIR/combined.mp4" 2>/dev/null

echo "Converting to GIF..."
mkdir -p "$(dirname "$GIF_OUTPUT")"
ffmpeg -y -i "$ASSEMBLY_DIR/combined.mp4" \
    -vf "fps=$GIF_FPS,scale=$GIF_WIDTH:-1:flags=lanczos,palettegen=max_colors=$GIF_COLORS:stats_mode=diff" \
    "$ASSEMBLY_DIR/palette.png" 2>/dev/null
ffmpeg -y -i "$ASSEMBLY_DIR/combined.mp4" -i "$ASSEMBLY_DIR/palette.png" \
    -lavfi "fps=$GIF_FPS,scale=$GIF_WIDTH:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3" \
    -loop 0 "$GIF_OUTPUT" 2>/dev/null

SIZE=$(du -h "$GIF_OUTPUT" | cut -f1)
echo "Generated $GIF_OUTPUT ($SIZE)"
