#!/bin/bash
# SECONDS=0 && \
# nohup python3 src/main.py agx13:8884 --with_dataclay > ./program.log 2>&1 & \
# bg_pid=$! && \
# echo "one $!" && \
# wait $bg_pid && echo "waiting job seconds: $SECONDS" && \
# rsync -uazPt *.in ~/data/florencia/batoni/logs

export PYTHONPATH=$COMPSS_HOME/Bindings/python/3:$PYTHONPATH
python3 src/main.py  --edge_ips=agx13:8883 --mode='udp' --semantics=True --save_plot=True --view_plot=True 