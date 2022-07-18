#!/bin/bash
set -e
# echo $1
echo Your container args are: "$@"

# If this image is a worker
# if [[ "$1" == "master" ]]; then
# python3 entrypoint.py
# echo "..deploying master"
# shift 1
# # If this image is master
# else
# echo ".. deploying worker"
# MASTER_USER="flo01"
# LOGICMODULE_HOST="192.168.121.183"
# PATH_TO_STUBS_MASTER="/home/flo01/smartcity-compss/stubs/"
# whoami
# scp -r ${MASTER_USER}@${LOGICMODULE_HOST}:${PATH_TO_STUBS_MASTER} .
# fi

exec "$@"
echo "EXEC REALIZADO"
