#!/bin/bash
# SECONDS=0 && \
# bg_pid=$! && \
# echo "one $!" && \
# wait $bg_pid && echo "waiting job seconds: $SECONDS" && \
# rsync -uazPt *.in ~/data/florencia/batoni/logs
export GST_DEBUG=0
export PYTHONPATH=$COMPSS_HOME/Bindings/python/3:$PYTHONPATH

# Start the web visualizer in the background (accessible on port 8080)
cd /root/smart-city-compss
find visualizer -name "*.pyc" -delete 2>/dev/null
python3 -m visualizer.app &

# python3 src/main.py  --edge_ips 192.168.88.249:8884 192.168.88.249:8883  --mode='udp' --semantics=True --view_plot=True
# python3 src/main.py  --edge_ips 192.168.88.243:8883  --mode='udp' --save_results=True --only_results=False --get_speed=True --print_time=True --get_semantic=True --save_plot=True
python3 src/main.py    --edge_ips               dummy  --mode='csv' --save_results=True --only_results=False --get_speed=True --print_time=True --get_semantic=True
