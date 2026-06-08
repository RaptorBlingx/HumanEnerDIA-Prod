# Multi-stage build for Chatbot UI
# NOTE: This container runs the Express backend proxy only.
# Rasa server must be running separately (see README for setup).

# Stage 1: Build frontend
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install all dependencies (including dev for build)
RUN npm install

# Copy source files
COPY . .

# Build the frontend with Vite
RUN npm run build

# Stage 2: Production with Express backend
FROM node:20-alpine AS production

WORKDIR /app

# Install production dependencies only
COPY package*.json ./
RUN npm install --omit=dev

# Copy backend server
COPY server ./server

# Copy built frontend from builder stage
COPY --from=builder /app/dist ./dist

# Note: Rasa models should be mounted as volume or Rasa server run externally
# COPY models ./models

# Environment variables
ENV NODE_ENV=production
ENV BACKEND_PORT=5006

# Expose backend proxy port
EXPOSE 5006

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:5006/health || exit 1

# Start the backend server (Rasa must be started separately or externally)
CMD ["node", "server/index.js"]
