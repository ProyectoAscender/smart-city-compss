# SmartCity COMPSs

`bash scripts/runDocker.sh` ejecutará smart-city en un contenedor en segundo plano. El contendor se borrará automáticamente si el mismo se para manualmente o por error.El archivo que correrá por defecto es `scripts/run.sh`que contiene:

`python3 src/main.py  --edge_ips 192.168.89.254:8883  --mode='udp' --save_results=True --only_results=True`

Las flags pueden ser consultadas dese la línea 35 de src.main.py. 
--edge_ips es una lista de ip's de las que se necesita leer las cajas por udp. En este caso, `192.168.89.254` es la ip de máquina que corre camera-edge. `8883` es el puerto que se establece en `portCommunicator`en el yaml de camera-edge. 

El stdout de este run puede ser invocado sin entrar al contenedor con el comando docker logs. 
