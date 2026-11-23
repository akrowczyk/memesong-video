FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    CMAKE_POLICY_VERSION_MINIMUM=3.5 \
    HOST=0.0.0.0 \
    PORT=8765 \
    RELOAD=0

# System deps: ffmpeg/ffprobe, soundfile, system libopus (avoids CMake build of bundled opus), fonts, curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libopus-dev \
    pkg-config \
    build-essential \
    cmake \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better Docker layer caching
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

# Copy application code
COPY backend ./backend
COPY frontend ./frontend
COPY run.py ./

RUN mkdir -p /app/projects

EXPOSE 8765

CMD ["uv", "run", "--no-sync", "python", "run.py"]
