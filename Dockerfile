FROM python:3.9-slim

# Install uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies (curl for optional container checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install requirements using uv (extremely fast and cached)
COPY pyproject.toml uv.lock /app/
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy project files
COPY . /app/

# Run the bot
CMD ["python", "bot.py"]

