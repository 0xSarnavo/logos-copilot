FROM python:3.12-slim
WORKDIR /app
# git: needed by the ingester to clone repos. curl: healthchecks/debug.
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "-m", "logos_copilot.server"]
