#!/bin/bash
​#If there are already existing smart-city 
user="flo01"
for worker_ip in `grep "<ComputeNode" config/resources.xml | cut -d'"' -f2`;
do
	echo "Removing worker docker in $worker_ip"
	docker_workers=$(ssh "$user@$worker_ip" "docker ps -a" | grep "smartcity-compss-" | awk '{print $1}')
	echo "$(ssh "$user@$worker_ip" "docker ps -a" | grep "smartcity-compss-" | awk '{print $1}')"
	for worker in $docker_workers;
	do
		echo "WORKER TO BE REMOVED IS $worker"
		ssh "$user@$worker_ip" "docker rm -f ${worker}"
	done
done


# runcompss -d --python_interpreter=python3 --lang=python --master_name=192.168.121.248 --master_port=43001 \
#           --scheduler="es.bsc.compss.scheduler.fifo.FIFOScheduler"  \
#           --project=config/project.xml --resources=config/resources.xml \
#           --classpath=/root/smartcity-compss/dataclay/dataclay.jar \
#           --storage_conf=/root/smartcity-compss/cfgfiles/session.properties tracker.py 10.50.100.3:8887 --with_dataclay 

/runcompss-docker  --worker-containers=3 \
                  --swarm-manager='192.168.121.246:2377' \
                  --image-name='bscppc/smartcity-compss:2.10-3.6' \
                  --context-dir='/root/smartcity-compss/' \
                  -d --python_interpreter=python3 --lang=python --master_name=192.168.121.248 --master_port=43001 \
                  --scheduler="es.bsc.compss.scheduler.fifo.FIFOScheduler"  \
                  --project=config/project.xml --resources=config/resources.xml \
                  --classpath=/root/smartcity-compss/dataclay/dataclay.jar \
                  --storage_conf=/root/smartcity-compss/cfgfiles/session.properties tracker.py 10.50.100.3:8887 --with_dataclay 