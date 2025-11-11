FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN pip install --no-cache-dir pandas matplotlib scikit-learn scipy

# Expose /app for mounting your code as a volume
VOLUME ["/app"]

# Start an interactive shell by default
CMD ["bash"]


# docker build -t bernatx/dataan .

# docker run -it --rm -v /home/xandri/ascender/scripts/:/app bernatx/dataan