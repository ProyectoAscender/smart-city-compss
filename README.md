# SmartCity COMPSs

This repository contains the necessary tools to execute the smartcity workflow using COMPSs. To build the environment [Docker](https://docs.docker.com/engine/install/) technology has been used, make sure to have it installed. Also, to execute the smartcity-compss code it is necessary to have already executing [Camera Edge](https://gitlab.bsc.es/ppc-bsc/software/camera-edge) program, with inside in its respective Docker image.

## Environment (Docker images)

In order to build the image with the compss program running we have to take a look to different files.

### Files definition

#### Dockerfile

This file contains the description of the image to execute the SmartCity with COMPSs. The image receive an argument for the building and has all the prerequisites necessaries for the installation/execution of COMPSs in a **arm64** architecture.

The file follows the next structure:

1. Copy the content from a **COMPSs base image**.
2. Install **Java 8** and **Python**.
3. Install **SSH**, **SSHpass**.
4. Install **Tzdata**.
5. Install **Eigen 3**.
6. Install **Pybindll**.
7. Install **deduplicator dependencies**.
8. Install **COMPSs obstacle detection dependencies**.
9. Clone the repository of the [smartcity-comps](https://gitlab.bsc.es/ppc-bsc/software/smartcity-compss.git).
10. Copy data from `roi/` folder.
11. Establishing **entrypoint** for downloading the stubs, and making the image readt at runtime.

For further details take a look.

#### Makefile

This file executes the commands to build and push the Docker image with respective name. Currently the image is only pushed to **Docker Hub**.

### Building the image

In order to build the Docker image, it is necessary to execute the following command in the root folder. It will take a long time to build everything.

```bash
make
```

The resulting image by default, has the name `bscppc/smartcity-compss:2.10` and it will be pushed to Docker Hub.

## Smartcity workflow

### Files definition

#### runDocker.sh

This file contains everything related to:

- Mapping volumes.
- Ports.

```bash
#!/bin/bash

docker run -it --name smartcity01   -p 8887:8887 -p 43001:43001 -p 43002:43002 --net bridge --gpus all -v ~/smartcity-compss:/root/smartcity-compss -v /root/smartcity-compss/lib -v /root/smartcity-compss/dataclay -v ~/data:/root/data  bscppc/smartcity-compss:2.10-3.6 master /bin/bash
```

#### run.sh

This file launches the workflow, `tracker.py`, and captures all the information emited through the *logs*. It is important to have in mind that this script does not execute the workflow using COMPSs but, launches a linux process running in the background (`nohup`).

```bash
#!/bin/bash

SECONDS=0 && \
nohup python3 tracker.py 10.50.100.3:8887 10.50.100.3:8886 --with_dataclay > ./program.log 2>&1 & \
bg_pid=$! && \
echo "one $!" && \
wait $bg_pid && echo "waiting job seconds: $SECONDS" && \
rsync -uazPt *.in ~/data/florencia/batoni/logs
```

#### runcompss.sh

This file launches the workflow and captures all the information emited through the *logs*. The script uses COMPSs in order to improve the performance of the workflow. Inside the file it can be found the different flags when executing the workflow with COMPSs.

```bash
#!/bin/bash

scripts/user/runcompss-docker  --worker-containers=1 \
                  --swarm-manager='192.168.121.183:2377' \
                  --image-name='bscppc/smartcity-compss:2.10-3.6' \
                  --context-dir='/root/smartcity-compss/' \
                  -d -t --python_interpreter=python3 --lang=python --master_name=192.168.121.183 --master_port=43001 \
                  --scheduler="es.bsc.compss.scheduler.fifo.FIFOScheduler"  \
                  tracker.py edge01:8887 edge01:8886 --with_dataclay 
```

### Executing the workflow

Firstly, we have to launch the Docker Image generated previously (`bscppc/smartcity-compss:2.10`). This can be done by executing the `runDocker.sh` script.

```bash
./runDocker.sh
```

After executing the script, the terminal will enter into the container to execute the different commands.

Finally, run the `runcompss.sh` script to execute the workflow with COMPSs. *If you want to run the code without using COMPSs, it is also possible by running the `run.sh` script.*

```bash
./runcompss.sh # Executing workflow with COMPSs

# OR #

./run.sh # Executing workflow without COMPSs
```

**\*Important\*: Make sure that the Camera Edge program is running in another container before executing smartcity-compss program; otherwise, it will not work.**
