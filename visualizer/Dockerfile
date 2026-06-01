# Amazon ECR Public — mirror oficial de Docker Hub, sin rate limit ni cuenta
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Install OS deps (numpy needs libc; watchdog needs inotify on Linux)
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY visualizer/requirements.txt /app/visualizer/requirements.txt
RUN pip install --no-cache-dir -r /app/visualizer/requirements.txt

# Copy visualizer source
COPY visualizer/ /app/visualizer/

# data_cache, runs, and .env are mounted as volumes at runtime (see docker-compose.yml)

EXPOSE 8080

CMD ["python", "-m", "visualizer.app"]
