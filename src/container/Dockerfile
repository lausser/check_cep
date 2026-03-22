ARG PLAYWRIGHT_VERSION=v1.58.2
FROM mcr.microsoft.com/playwright:${PLAYWRIGHT_VERSION}-noble

# Re-declare ARG after FROM
ARG PLAYWRIGHT_VERSION=v1.58.2
ENV PLAYWRIGHT_VERSION=${PLAYWRIGHT_VERSION} \
    DEBIAN_FRONTEND="noninteractive" \
    TZ="UTC"

# Helpful addons for assisted writing of test scripts
ARG AI_NODE_PACKAGES="@google/gemini-cli @playwright/cli"

# Install Python 3, system dependencies, and configure sudo for pwuser
# (sudo needed for `npx playwright install` to install browser system deps)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3-pip \
    sudo \
    fontconfig \
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
#   `lightpanda-io/browser` and currently uses v0.2.x tags.
# - These are different version streams and must not be assumed to match.
# - To keep the container reproducible, we pin BOTH:
#   - the npm wrapper package via package.json/package-lock.json
#   - the native browser binary via LIGHTPANDA_BROWSER_VERSION below.
# - We also point LIGHTPANDA_EXECUTABLE_PATH at the final stable install path
#   before `npm ci` so the package postinstall does not download a moving
#   nightly binary into ~/.cache and accidentally override the pin.
ARG LIGHTPANDA_BROWSER_VERSION=v0.2.6
ENV LIGHTPANDA_DISABLE_TELEMETRY=true \
    LIGHTPANDA_EXECUTABLE_PATH=/usr/local/bin/lightpanda

# Set environment
ENV NODE_PATH=/home/pwuser/node_modules \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/home/pwuser/playwright-report \
    NODE_OPTIONS="--max-http-header-size=120480"

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

# AI Tooling
ENV GEMINI_YOLO=true \
    GEMINI_CONFIG_HOME="/home/pwuser/.gemini" \
    PATH="/home/pwuser/.local/bin:/home/pwuser/node_modules/.bin:${PATH}"
RUN if [ -n "$AI_NODE_PACKAGES" ]; then \
        mkdir -p /home/pwuser/.gemini && \
        echo "--- Installing AI Addons locally ---" && \
        npm install $AI_NODE_PACKAGES && \
        # Create settings.json to silence root warnings and telemetry
        printf '{\n  "security": {\n    "folderTrust": {\n      "enabled": false\n    },\n    "auth": {\n      "selectedType": "gemini-api-key"\n    },\n    "enablePermanentToolApproval": true\n  },\n  "ui": {\n    "showHomeDirectoryWarning": false,\n    "theme": "Default Light",\n    "showCompatibilityWarnings": false\n  },\n  "general": {\n    "defaultApprovalMode": "default"\n  }\n}\n' > /home/pwuser/.gemini/settings.json; \
    fi

# Ensure global npm binaries are in the PATH
ENV PATH="/home/pwuser/.npm-global/bin:${PATH}"

# 3. Playwright Browser Engines
RUN npx playwright install --with-deps msedge chrome && \
    npm config set update-notifier false && \
    npm config set color false && \
    npm cache clean --force

# Cleanup npm artifacts
RUN rm -f package.json package-lock.json

# Install git temporarily and fetch the skills
USER root
RUN apt-get update && apt-get install -y git && \
    git clone --depth 1 https://github.com/microsoft/playwright-cli.git /tmp/pw-cli && \
    mkdir -p /home/pwuser/.gemini/skills && \
    cp -r /tmp/pw-cli/skills/* /home/pwuser/.gemini/skills/ && \
    chown -R pwuser:pwuser /home/pwuser/.gemini && \
    rm -rf /tmp/pw-cli && \
    apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy AI agent skills (check-cep-vision, sakuli-migration, playwright-skill)
# These are documentation/reference files for AI coding agents — no build step needed.
# The Makefile copies .agents/skills/ into .agents-skills/ before building
# (dereferencing symlinks) so the files are inside the build context.
COPY --chown=pwuser:pwuser .agents-skills/ /home/pwuser/.agents/skills/
RUN ln -sf /home/pwuser/.agents/skills /home/pwuser/.gemini/skills/agents

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
