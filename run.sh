#!/bin/bash
SECONDS=0 && \
nohup python3 tracker.py 10.50.100.3:8887 10.50.100.3:8886 --with_dataclay > ./program.log 2>&1 & \
bg_pid=$! && \
echo "one $!" && \
wait $bg_pid && echo "waiting job seconds: $SECONDS" && \
rsync -uazPt *.in ~/data/florencia/batoni/logs