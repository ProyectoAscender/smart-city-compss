COMPSS_VERSION=3.3
SMARTCITY_VERSION=1.3
TAG=${SMARTCITY_VERSION}-${COMPSS_VERSION}
# IMAGE=registry.gitlab.bsc.es/ppc/software/compss/compss_nvidia:${COMPSS_VERSION}
IMAGE=smart-city-compss
PREFIX=registry.gitlab.bsc.es/ppc/benchmarks/smart-city/
PREFIX2=ghcr.io/proyectoascender/smart-city/

export DISPLAY=:10

# registry.gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss:3.3-arm--1.0
docker run -d --rm --runtime  nvidia -it --name smartcity_$USER  -e DISPLAY=$DISPLAY -v ~/.Xauthority:/root/.Xauthority -v /tmp/.X11-unix:/tmp/.X11-unix  --net=host -v ~/smart-city-compss:/root/smart-city-compss -v ~/opencv:/root/smart-city-compss/data/opencv/build -v /mnt/b2drop/smartCity:/root/smart-city-compss/data  ${PREFIX}${IMAGE}:${TAG}
