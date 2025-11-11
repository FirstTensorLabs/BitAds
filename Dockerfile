# syntax=docker/dockerfile:1.6
# Use official Python 3.12 slim image pinned to Debian Bookworm to ensure Playwright deps install reliably
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install base system dependencies only (no Node.js)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install pip and poetry
RUN pip install --upgrade pip

## Node and Playwright steps removed

# Copy the rest of the project and install Python package and deps from pyproject
WORKDIR /app
COPY . .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# Copy and set up entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Use entrypoint script that reads env vars and passes them as args
ENTRYPOINT ["/entrypoint.sh"]

# No default CMD - all args come from environment variables via entrypoint