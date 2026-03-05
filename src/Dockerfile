ARG PLAYWRIGHT_VERSION
FROM mcr.microsoft.com/playwright:${PLAYWRIGHT_VERSION}-jammy

# Re-declare ARG after FROM
ARG PLAYWRIGHT_VERSION
ENV PLAYWRIGHT_VERSION=${PLAYWRIGHT_VERSION} \
    DEBIAN_FRONTEND="noninteractive" \
    TZ="UTC"

# Install Python 3, system dependencies, and configure sudo for pwuser
# (sudo needed for `npx playwright install` to install browser system deps)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3-pip \
    sudo \
    fontconfig \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir boto3 && \
    echo "pwuser ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/pwuser && \
    chmod 640 /etc/sudoers.d/pwuser

# Create test and results directories owned by pwuser (FR-017).
RUN mkdir -p /home/pwuser/tests /home/pwuser/results && \
    chown pwuser:pwuser /home/pwuser/tests /home/pwuser/results

# Switch to pwuser
USER pwuser
WORKDIR /home/pwuser

# Set environment
ENV NODE_PATH=/home/pwuser/node_modules \
    PLAYWRIGHT_HTML_OUTPUT_DIR=/home/pwuser/playwright-report \
    NODE_OPTIONS="--max-http-header-size=120480"

# Optional npm dependencies: replace the zero-byte package.json and
# package-lock.json in src/ with real ones to bake npm deps into the image.
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
    npx playwright install --with-deps msedge && \
    npx playwright install --with-deps chrome && \
    npm config set update-notifier false && \
    npm config set color false

# Cleanup npm artifacts
RUN rm -f package.json package-lock.json

# Copy container-side code
USER root
COPY container/run.py /home/pwuser/run.py
COPY container/plugins/ /home/pwuser/plugins/
RUN chmod 755 /home/pwuser/run.py && \
    chown -R pwuser:pwuser /home/pwuser/run.py /home/pwuser/plugins/

USER pwuser
CMD ["python3", "./run.py"]
