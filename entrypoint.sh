#!/bin/bash
set -e
echo $1
echo Your container args are: "$@"

# If this image is a worker
if [[ "$1" == "master" ]]; then
python3 entrypoint.py
echo "..deploying master"
shift 1
fi
# If this image is master
if [[ "$1" == "worker" ]]; then
echo ".. deploying worker"
MASTER_USER="flo01"
LOGICMODULE_HOST="192.168.121.248"
PATH_TO_STUBS_MASTER="/root/smartcity-compss/stubs/"
whoami
ls -la .
ls -la ${MASTER_USER}@${LOGICMODULE_HOST}:${PATH_TO_STUBS_MASTER}
scp -r ${MASTER_USER}@${LOGICMODULE_HOST}:${PATH_TO_STUBS_MASTER} .
fi

exec "$@"
echo "EXEC REALIZADO"
