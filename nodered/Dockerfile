# ============================================================================
# EnMS - Node-RED Data Pipeline
# Custom Dockerfile with PostgreSQL and MQTT Support
# ============================================================================

FROM nodered/node-red:3.1.0

# Switch to root to install packages
USER root

# Install additional packages (using your working pattern)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    build-base \
    python3-dev \
    postgresql-client \
    cmake \
    curl

# Switch back to node-red user for Node-RED setup
USER node-red
WORKDIR /data

# Copy package.json if it exists (following your pattern)
COPY package.json* ./

# Note: flows.json will be mounted as a volume from host, not copied during build
# Note: settings.js will be provided via environment variables instead

# Configure npm for better network handling and install packages
RUN npm config set registry https://registry.npmjs.org/ && \
    npm config set timeout 600000 && \
    npm config set fetch-timeout 600000 && \
    npm config set fetch-retry-mintimeout 30000 && \
    npm config set fetch-retry-maxtimeout 180000 && \
    npm config set fetch-retries 5 && \
    npm install --no-audit --no-fund --verbose || \
    (sleep 30 && npm install --no-audit --no-fund --verbose) || \
    (sleep 60 && npm install --no-audit --no-fund --verbose)

# Install Node-RED contrib packages globally to ensure they're available
WORKDIR /usr/src/node-red
RUN npm install --save \
    node-red-contrib-postgresql@0.15.4 \
    node-red-dashboard@3.6.0 \
    node-red-node-email@1.18.4 \
    --no-audit --no-fund

# Fix permissions (following your pattern)
USER root
RUN chown -R node-red:node-red /data

# Switch back to node-red user
USER node-red
WORKDIR /usr/src/node-red

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:1880/ || exit 1

# Use default Node-RED entrypoint
CMD ["npm", "start"]