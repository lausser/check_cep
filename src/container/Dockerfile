# Build-args without defaults (spec 024): the values come from
# src/container/versions.env and VERSION — build with `make image` (or pass
# all five --build-arg values, see README "Build the Container Image").
# PLAYWRIGHT_VERSION has no "v" prefix; the base image is pinned by digest.
# A missing PLAYWRIGHT_VERSION/PLAYWRIGHT_BASE_DIGEST already fails while
# resolving FROM (before any RUN can check it); the other args are checked
# with a clear message below.
ARG PLAYWRIGHT_VERSION
ARG PLAYWRIGHT_BASE_DIGEST
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble@${PLAYWRIGHT_BASE_DIGEST} AS base

# Re-declare ARGs after FROM
ARG PLAYWRIGHT_VERSION
ARG CEP_VERSION
ARG VCS_REF
ARG BUILD_DATE
RUN for arg in PLAYWRIGHT_VERSION=${PLAYWRIGHT_VERSION} CEP_VERSION=${CEP_VERSION} \
               VCS_REF=${VCS_REF} BUILD_DATE=${BUILD_DATE}; do \
        [ -n "${arg#*=}" ] || { echo "missing --build-arg ${arg%%=*} (use make image)"; exit 1; }; \
    done
ENV PLAYWRIGHT_VERSION=${PLAYWRIGHT_VERSION} \
    CEP_IMAGE_VERSION=${CEP_VERSION} \
    DEBIAN_FRONTEND="noninteractive" \
    TZ="UTC"
LABEL org.opencontainers.image.version="${CEP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/lausser/check_cep" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.title="check_cep" \
      io.consol.check_cep.playwright.version="${PLAYWRIGHT_VERSION}"

# Install Python 3, system dependencies, and configure sudo for pwuser
# (sudo needed for `npx playwright install` to install browser system deps)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3-pip \
    sudo \
    fontconfig \
    tigervnc-standalone-server \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --break-system-packages boto3 && \
    echo "pwuser ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/pwuser && \
    chmod 640 /etc/sudoers.d/pwuser

# Create test and results directories owned by pwuser (FR-017).
RUN mkdir -p /home/pwuser/tests /home/pwuser/results /home/pwuser/testscripts-cache && \
    chown pwuser:pwuser /home/pwuser/tests /home/pwuser/results /home/pwuser/testscripts-cache

# Switch to pwuser
USER pwuser
WORKDIR /home/pwuser

# Lightpanda versioning note:
# - `@lightpanda/browser` is an npm package published from the separate
#   `lightpanda-io/node-packages` repository. Its published versions are 1.x.
# - The native Lightpanda browser binary is released from
#   `lightpanda-io/browser`. NOTE the release-tag scheme changed: the old
#   0.2.x line was tagged `v0.2.x` (with a `v`), but the 0.3.x releases dropped
#   the prefix and are tagged plain `0.3.x` (`v0.3.4` 404s). Pin without the `v`.
# - These are different version streams and must not be assumed to match.
# - To keep the container reproducible, we pin BOTH:
#   - the npm wrapper package via package.json/package-lock.json
#   - the native browser binary via LIGHTPANDA_BROWSER_VERSION below.
# - We also point LIGHTPANDA_EXECUTABLE_PATH at the final stable install path
#   before `npm ci` so the package postinstall does not download a moving
#   nightly binary into ~/.cache and accidentally override the pin.
ARG LIGHTPANDA_BROWSER_VERSION=1.0.2
ENV LIGHTPANDA_DISABLE_TELEMETRY=true \
    LIGHTPANDA_EXECUTABLE_PATH=/usr/local/bin/lightpanda

# Set environment — consolidate all PATH additions here so cep_codegen works in base
ENV NODE_PATH=/home/pwuser/node_modules \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/home/pwuser/playwright-report \
    NODE_OPTIONS="--max-http-header-size=120480" \
    PATH="/home/pwuser/.local/bin:/home/pwuser/node_modules/.bin:/home/pwuser/.npm-global/bin:${PATH}"

# Copy local helper modules (before npm install so local file: deps resolve)
COPY --chown=pwuser:pwuser check-cep-vision/ ./check-cep-vision/
COPY --chown=pwuser:pwuser check-cep-helpers/ ./check-cep-helpers/

# Optional npm dependencies: replace the zero-byte package.json and
# package-lock.json in src/container/ with real ones to bake npm deps into the image.
COPY --chown=pwuser:pwuser package.json package-lock.json ./
RUN if [ -s package-lock.json ]; then \
        echo "--- Installing NPM packages from user-provided package-lock.json ---" && \
        npm ci --foreground-scripts; \
    else \
        echo "--- No user-provided package-lock.json, installing @playwright/test ---" && \
        rm -f package.json package-lock.json && \
        npm init -y && \
        npm install @playwright/test; \
    fi && \
    BUNDLED=$(npx playwright --version | awk '{print $2}') && \
    if [ "$BUNDLED" != "${PLAYWRIGHT_VERSION}" ]; then \
        echo "Playwright mismatch: base/arg ${PLAYWRIGHT_VERSION} vs bundled ${BUNDLED}"; exit 1; \
    fi

# Install the pinned Lightpanda browser binary to the stable runtime path.
# This intentionally bypasses the npm postinstall cache download so the image
# never depends on a moving nightly binary during build.
RUN ARCH=$(uname -m) && \
    LP_URL="https://github.com/lightpanda-io/browser/releases/download/${LIGHTPANDA_BROWSER_VERSION}/lightpanda-${ARCH}-linux" && \
    echo "--- Fetching pinned Lightpanda binary ${LIGHTPANDA_BROWSER_VERSION} from ${LP_URL} ---" && \
    curl -fsSL --retry 3 -o /tmp/lightpanda "$LP_URL" && \
    chmod 755 /tmp/lightpanda && \
    sudo cp /tmp/lightpanda /usr/local/bin/lightpanda && \
    sudo chmod 755 /usr/local/bin/lightpanda && \
    echo "--- Lightpanda binary installed to /usr/local/bin/lightpanda ---"

# 3. Playwright Browser Engines
RUN npx playwright install --with-deps msedge chrome && \
    npm config set update-notifier false && \
    npm config set color false && \
    npm cache clean --force

# Keep package.json/package-lock.json: a self-describing node_modules keeps any
# later `npm install` (e.g. the ai stage) ADDITIVE. Deleting them orphans the
# tree, so npm's reification would prune @playwright/test on the next install.

# Copy container-side code
USER root
COPY image/run.py /home/pwuser/run.py
COPY image/plugins/ /home/pwuser/plugins/
COPY image/patch-lightpanda.js /home/pwuser/patch-lightpanda.js
COPY image/chrome-wrapper /tmp/chrome-wrapper
# Replace the real Chromium binary with a wrapper that injects GPU-disable
# and Wayland flags.  The original binary is kept as chrome.real.
# This means ALL Playwright commands (test, codegen, etc.) get the right
# flags without any Playwright-level config workarounds.
RUN CHROME=$(node -e "const { chromium } = require('playwright'); console.log(chromium.executablePath())") && \
    mv "$CHROME" "${CHROME}.real" && \
    cp /tmp/chrome-wrapper "$CHROME" && \
    rm /tmp/chrome-wrapper && \
    mkdir -p /home/pwuser/.local/bin && \
    printf '#!/bin/bash\nexec npx playwright codegen "$@"\n' > /home/pwuser/.local/bin/cep_codegen && \
    chmod 755 /home/pwuser/run.py /home/pwuser/.local/bin/cep_codegen "$CHROME" && \
    chown -R pwuser:pwuser /home/pwuser

USER pwuser
CMD ["python3", "./run.py"]

# ── AI STAGE ───────────────────────────────────────────────────────────────
FROM base AS ai

# opencode CLI version pin (npm dist-tag, pinned)
ARG OPENCODE_VERSION=1.18.4

# chrome-devtools-mcp: live-browser inspection/remote-control tool for the
# authoring agent (spec 020, research R13). Pinned; authoring image only.
ARG CHROME_DEVTOOLS_MCP_VERSION=1.5.0

# AI npm packages (opencode CLI + playwright-cli + chrome-devtools-mcp),
# installed additively into the same node_modules as the base image. Because
# the base stage keeps its package.json, @playwright/test and the
# `playwright` bin the authoring RUN phase needs survive this install.
# chrome-devtools-mcp is registered below as an opencode local MCP server: it
# spawns the Playwright-installed Chrome (the GPU-disable wrapper) headless
# and isolated so it runs as pwuser in rootless Podman without an unsandboxed
# or second browser. Exploration is two-tool (chrome-devtools-mcp discovers,
# @playwright/cli confirms).
ARG AI_NODE_PACKAGES="opencode-ai@${OPENCODE_VERSION} @playwright/cli chrome-devtools-mcp@${CHROME_DEVTOOLS_MCP_VERSION}"
RUN mkdir -p /home/pwuser/.config/opencode && \
    echo "--- Installing AI Addons ---" && \
    npm install $AI_NODE_PACKAGES && \
    node -e 'const fs=require("fs");const {chromium}=require("playwright");const chrome=chromium.executablePath();const config={"$schema":"https://opencode.ai/config.json",model:"opencode/big-pickle",permission:{edit:"allow",bash:"allow"},mcp:{"chrome-devtools":{type:"local",command:["cep-cdp-mcp","--isolated=true","--viewport=1280x720","--executablePath="+chrome,"--chromeArg=--no-sandbox","--chromeArg=--disable-dev-shm-usage"],enabled:true}},agent:{critic:{description:"Read-only reviewer for authored CEP tests",permission:{edit:"deny",bash:"deny"}}}};fs.writeFileSync("/home/pwuser/.config/opencode/opencode.json",JSON.stringify(config,null,2)+"\n");'

# Install git temporarily; clone playwright-cli skills AND playwright-skill in one layer
USER root
RUN apt-get update && apt-get install -y git && \
    git clone --depth 1 https://github.com/microsoft/playwright-cli.git /tmp/pw-cli && \
    git clone --depth 1 https://github.com/lackeyjb/playwright-skill.git /tmp/pw-skill && \
    mkdir -p /home/pwuser/.agents/skills && \
    cp -r /tmp/pw-cli/skills/* /home/pwuser/.agents/skills/ && \
    cp -r /tmp/pw-skill/skills/playwright-skill /home/pwuser/.agents/skills/ && \
    chown -R pwuser:pwuser /home/pwuser/.agents && \
    rm -rf /tmp/pw-cli /tmp/pw-skill && \
    apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy local agent skills (check-cep-vision + sakuli-migration + cep-test-authoring).
# opencode natively discovers skills at ~/.agents/skills/<name>/SKILL.md — no
# registration or symlink needed (unlike gemini's .gemini/skills wiring).
COPY --chown=pwuser:pwuser .agents-skills/ /home/pwuser/.agents/skills/

# Authoring-mode operator tools (spec 020): the unattended orchestrator and the
# shared packaging tool. Siblings of cep_codegen in /home/pwuser/.local/bin.
# Authoring `ai` image only — the base/scheduled image never ships these.
COPY image/cep_authoring image/cep_package image/cep-cdp-mcp /home/pwuser/.local/bin/
RUN chmod 755 /home/pwuser/.local/bin/cep_authoring /home/pwuser/.local/bin/cep_package /home/pwuser/.local/bin/cep-cdp-mcp && \
    chown pwuser:pwuser /home/pwuser/.local/bin/cep_authoring /home/pwuser/.local/bin/cep_package /home/pwuser/.local/bin/cep-cdp-mcp

USER pwuser
CMD ["python3", "./run.py"]
