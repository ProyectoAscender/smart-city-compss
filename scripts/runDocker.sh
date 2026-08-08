COMPSS_VERSION=3.3-arm
SMARTCITY_VERSION=1.2
TAG=${SMARTCITY_VERSION}-${COMPSS_VERSION}
# IMAGE=registry.gitlab.bsc.es/ppc/software/compss/compss_nvidia:${COMPSS_VERSION}
IMAGE=smart-city-compss
PREFIX=registry.gitlab.bsc.es/ppc/benchmarks/smart-city/
PREFIX2=ghcr.io/proyectoascender/smart-city/
MODE=${1:-csv}

if [ "$#" -gt 0 ]; then
    shift
fi

export DISPLAY=:10

# registry.gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss:3.3-arm--1.0
docker run -d --runtime  nvidia -it --name smartcity_$USER  -e DISPLAY=$DISPLAY -v ~/.Xauthority:/root/.Xauthority -v /tmp/.X11-unix:/tmp/.X11-unix  --net=host -v ~/smart-city-compss:/root/smart-city-compss -v ~/opencv:/root/smart-city-compss/data/opencv/build -v /mnt/b2drop/smartCity:/root/smart-city-compss/data  ${PREFIX}${IMAGE}:${TAG} /bin/bash scripts/run.sh "$MODE" "$@"
