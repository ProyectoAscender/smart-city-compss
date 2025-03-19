/home/vmasip/compss/compss/runtime/scripts/utils/compss_docker_gen_image --image-base="registry.gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss:1.0-3.3" \
                                                                         --image-name="registry.gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss:1.0-3.3-final" \
                                                                         --context-dir="/home/vmasip/smart-city-compss"

# How it works:
# image_base=patata
# image_final=patata-2

# docker inspect patata-arm (dockerhub or registry)
# if present
# docker pull patata-arm
# docker build from patata-arm to patata-2-arm

# docker inspect patata-amd
# if present
# docker pull patata-amd
# docker build from patata-amd to patata-2-amd
