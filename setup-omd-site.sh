#!/usr/bin/env bash
# setup-omd-site.sh — Install check_cep into the active OMD site.
#
# Site-user mode (no argument):
#   cd /path/to/check_cep
#   bash setup-omd-site.sh
#
# Root mode (pass the site name):
#   bash setup-omd-site.sh testsite
#
# Requirements:
#   - Site-user mode: $OMD_ROOT must be set (it is when logged in as site user)
#   - Root mode: run as root; the site must already exist (omd create <site>)
#   - The script must be run from the root of the check_cep repository

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_NAME="${1:-}"

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

if [[ -n "$SITE_NAME" ]]; then
    # Root mode
    if [[ "$EUID" -ne 0 ]]; then
        echo "ERROR: pass a site name only when running as root." >&2; exit 1
    fi
    OMD_ROOT="/omd/sites/$SITE_NAME"
    if [[ ! -d "$OMD_ROOT" ]]; then
        echo "ERROR: $OMD_ROOT does not exist. Run 'omd create $SITE_NAME' first." >&2; exit 1
    fi
else
    # Site-user mode
    if [[ -z "${OMD_ROOT:-}" ]]; then
        echo "ERROR: \$OMD_ROOT is not set. Run as site user or pass the site name." >&2; exit 1
    fi
    SITE_NAME=""   # not needed
fi

if [[ ! -f "$REPO_DIR/src/check_cep" ]]; then
    echo "ERROR: src/check_cep not found. Run this from the repository root." >&2
    exit 1
fi

echo "Installing check_cep into OMD site: $OMD_ROOT"

# ---------------------------------------------------------------------------
# 1. Plugin binary
# ---------------------------------------------------------------------------

PLUGIN_DIR="$OMD_ROOT/local/lib/nagios/plugins"
mkdir -p "$PLUGIN_DIR"
cp "$REPO_DIR/src/check_cep" "$PLUGIN_DIR/check_cep"
chmod 755 "$PLUGIN_DIR/check_cep"
echo "  [ok] plugin -> $PLUGIN_DIR/check_cep"

# ---------------------------------------------------------------------------
# 2. Runtime directories
# ---------------------------------------------------------------------------

mkdir -p "$OMD_ROOT/etc/check_cep/tests"
echo "  [ok] test source dir -> $OMD_ROOT/etc/check_cep/tests"

mkdir -p "$OMD_ROOT/var/tmp/check_cep"
echo "  [ok] result dir      -> $OMD_ROOT/var/tmp/check_cep"

# ---------------------------------------------------------------------------
# 3. Demo starter test  (DEMOHOST / DEMOSERVICE)
# ---------------------------------------------------------------------------

DEMO_DIR="$OMD_ROOT/etc/check_cep/tests/DEMOHOST/DEMOSERVICE"
mkdir -p "$DEMO_DIR/functions"
mkdir -p "$DEMO_DIR/variables"
mkdir -p "$DEMO_DIR/bla/blub"

cat > "$DEMO_DIR/bla/blub/playwright.config.ts" << 'PWCONFIG'
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './',
  timeout: 30000,
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
  ],
});
PWCONFIG

cat > "$DEMO_DIR/bla/blub/consol.test.ts" << 'PWTEST'
import { test, expect } from '@playwright/test';

test('consol.de has Consulting & Solutions', async ({ page }) => {
  await page.goto('https://www.consol.de');
  await expect(page.locator('body')).toContainText('Consulting & Solutions');
});
PWTEST

echo "  [ok] demo test       -> $DEMO_DIR"

# ---------------------------------------------------------------------------
# 4. Container build context  ($OMD_ROOT/etc/check_cep/container/)
#    Contains everything needed to build the check_cep container image.
# ---------------------------------------------------------------------------

CONTAINER_DIR="$OMD_ROOT/etc/check_cep/container"
mkdir -p "$CONTAINER_DIR/image/plugins"

cp -r "$REPO_DIR/src/container/." "$CONTAINER_DIR/"

echo "  [ok] container build context -> $CONTAINER_DIR"

# ---------------------------------------------------------------------------
# 4. Root mode: transfer ownership to the site user
# ---------------------------------------------------------------------------

if [[ -n "$SITE_NAME" ]]; then
    chown -R "$SITE_NAME:$SITE_NAME" \
        "$OMD_ROOT/etc/check_cep" \
        "$OMD_ROOT/var/tmp/check_cep" \
        "$PLUGIN_DIR/check_cep"
    echo "  [ok] ownership -> $SITE_NAME:$SITE_NAME"
fi

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------

cat <<EOF

Done. Next steps:

  Build the container image (adjust the Playwright version as needed):
    cd $CONTAINER_DIR
    podman build --build-arg PLAYWRIGHT_VERSION=v1.58.2 -t localhost/check_cep:latest .

  Place your Playwright tests under:
    $OMD_ROOT/etc/check_cep/tests/<hostname>/<service>/

  The plugin is ready at:
    $PLUGIN_DIR/check_cep

EOF
