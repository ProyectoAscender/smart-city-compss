#!/bin/bash
# SECONDS=0 && \
# nohup python3 src/main.py agx13:8884 --with_dataclay > ./program.log 2>&1 & \
# bg_pid=$! && \
# echo "one $!" && \
# wait $bg_pid && echo "waiting job seconds: $SECONDS" && \
# rsync -uazPt *.in ~/data/florencia/batoni/logs


python3 src/main.py  --edge_ips=agx13:8883 --mode='udp'