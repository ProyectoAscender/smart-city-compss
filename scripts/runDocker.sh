#!/bin/bash
# docker run --runtime nvidia -it --name smartcity01 --net=host -v ~/smart-city-compss:/root/smartcity-compss -v /mnt/b2drop/smartCity:/root/smartcity-compss/data  registry.gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss:3.0-heuristics-arm---1.0 /bin/bash




docker run --runtime nvidia -it --name smartcity01 --net=host -v ~/smart-city-compss:/root/smartcity-compss -v /mnt/b2drop/smartCity:/root/smartcity-compss/data  registry.gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss:3.3-arm---3.3 /bin/bash