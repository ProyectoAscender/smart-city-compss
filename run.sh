#!/bin/bash
SECONDS=0 && \
nohup python3 tracker.py 172.17.0.2:8887 --with_dataclay > ./program.log 2>&1 & \
bg_pid=$! && \
echo "one $!" && \
wait $bg_pid && echo "waiting job seconds: $SECONDS" && \
rsync -uazPt *.in ~/data/florencia/batoni/logs