# ============================================================================
# EnMS Analytics Service - Dockerfile
# ============================================================================
# Phase 4 Session 2 - Updated with Prophet & ARIMA support
# Base: Python 3.12-slim
# ============================================================================

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# Install system dependencies
# Prophet requires gcc, g++, make and other build tools
# Playwright/Chromium requires glib, nss, fonts, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    postgresql-client \
    curl \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium

# Install CmdStan for Prophet (required binary backend)
# This downloads and compiles CmdStan - takes a few minutes but only on build
RUN python -m cmdstanpy.install_cmdstan --cores 2 --progress

# Copy application code
COPY . .

# Create directories for model storage and logs
RUN mkdir -p /app/models/saved/baseline && \
    mkdir -p /app/models/saved/anomaly && \
    mkdir -p /app/models/saved/forecast && \
    mkdir -p /app/logs && \
    chmod -R 755 /app/models

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/api/v1/health || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--log-level", "info"]