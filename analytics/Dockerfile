FROM python:3.11-slim

WORKDIR /app

COPY analytics/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY analytics /app/analytics

ENV HOST=0.0.0.0
ENV PORT=8090
ENV INPUT_DIR=/data/runs/exp/20260712
ENV VIDEO_START_TIME=

EXPOSE 8090

CMD ["sh", "-c", "python /app/analytics/app.py --input-dir \"${INPUT_DIR}\" --host \"${HOST}\" --port \"${PORT}\" ${VIDEO_START_TIME:+--video-start-time \"${VIDEO_START_TIME}\"}"]
