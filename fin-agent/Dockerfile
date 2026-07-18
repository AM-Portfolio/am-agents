# --- Stage 1: Build React UI ---
FROM node:20-slim AS ui-builder
WORKDIR /ui
# Copy only package files first for better caching
COPY am_fin_api_testing/am-api-testing-ui/package*.json ./
RUN npm install

# Copy source and build
COPY am_fin_api_testing/am-api-testing-ui/ ./
RUN npm run build

# --- Stage 2: Final Python Image ---
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Python application code
COPY . .

# Copy the built UI from Stage 1
# This assumes your Vite build output goes to 'dist'
COPY --from=ui-builder /ui/dist ./am_fin_api_testing/am-api-testing-ui/dist

# Set permissions for /app
RUN chown -R 1000:1000 /app

# Switch to non-root user
USER 1000

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "api.py"]
