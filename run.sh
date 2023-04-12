#!/bin/bash
SECONDS=0 && \
nohup python3 tracker.py 172.17.0.2:8887 --with_dataclay > ./program.log 2>&1 & \
bg_pid=$! && \
echo "one $!" && \
wait $bg_pid && echo "waiting job seconds: $SECONDS" && \
rsync -uazPt *.in ~/data/florencia/batoni/logs


43.7677536010742    11.2096843719482
43.767752195075076, 11.209683482064989