#!/bin/bash
# SECONDS=0 && \
# bg_pid=$! && \
# echo "one $!" && \
# wait $bg_pid && echo "waiting job seconds: $SECONDS" && \
# rsync -uazPt *.in ~/data/florencia/batoni/logs
export GST_DEBUG=0
export PYTHONPATH=$COMPSS_HOME/Bindings/python/3:$PYTHONPATH

MODE=${1:-csv}

cd /root/smart-city-compss
find visualizer -name "*.pyc" -delete 2>/dev/null

# main.py starts its own embedded web visualizer on port 8080 (visualizer.start()).
# Do NOT also launch `python3 -m visualizer.app` here: it would grab port 8080
# first, making main.py's embedded server (and its push_frame calls) a no-op.

# python3 src/main.py  --edge_ips 192.168.88.249:8884 192.168.88.249:8883  --mode='udp' --semantics=True --view_plot=True
# python3 src/main.py  --edge_ips 192.168.88.243:8883  --mode='udp' --save_results=True --only_results=False --get_speed=True --print_time=True --get_semantic=True --save_plot=True
# python3 src/main.py    --edge_ips 192.168.89.254:8883  --mode='udp' --save_results=True --only_results=False --get_speed=True --print_time=True --get_semantic=True

if [ "$MODE" = "csv" ]; then
    if [ -n "$2" ]; then
        export CSV_DAY="$2"
    fi
    python3 src/main.py --edge_ips dummy --mode='csv' --save_results=True --only_results=False --get_speed=True --print_time=True --get_semantic=True
elif [ "$MODE" = "udp" ]; then
    shift
    if [ "$#" -eq 0 ]; then
        echo "Uso: bash scripts/run.sh udp <edge_ip:port> ..."
        exit 1
    fi
    python3 src/main.py --edge_ips "$@" --mode='udp' --save_results=True --only_results=False --get_speed=True --print_time=True --get_semantic=True
else
    echo "Uso: bash scripts/run.sh [csv [YYYYMMDD] | udp <edge_ip:port> ...]"
    exit 1
fi
