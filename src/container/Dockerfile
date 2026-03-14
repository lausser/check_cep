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

# Set environment
ENV NODE_PATH=/home/pwuser/node_modules \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/home/pwuser/playwright-report \
    NODE_OPTIONS="--max-http-header-size=120480"

# Copy vision helper module (before npm install so local file: dep resolves)
COPY --chown=pwuser:pwuser check-cep-vision/ ./check-cep-vision/

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

# Install Lightpanda binary to a stable system path.
# The npm postinstall downloads the native binary to ~/.cache/lightpanda-node/.
# Copy it to /usr/local/bin/ so it survives cache cleanup.
RUN LPBIN="$HOME/.cache/lightpanda-node/lightpanda" && \
    if [ -x "$LPBIN" ]; then \
      sudo cp "$LPBIN" /usr/local/bin/lightpanda && \
      sudo chmod 755 /usr/local/bin/lightpanda && \
      echo "--- Lightpanda binary installed to /usr/local/bin/lightpanda ---"; \
    fi

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
