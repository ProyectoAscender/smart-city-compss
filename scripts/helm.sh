kubectl create secret generic regcred --from-file=.dockerconfigjson=/home/vmasip/.docker/config.json     --type=kubernetes.io/dockerconfigjson -n smartcity
helm template .
helm uninstall smartcity-compss -n smartcity
helm install -n smartcity smartcity-compss .
# check:
kubectl get pods
kubectl get pods --watch
kubectl exec -it <pod_name> -c master -- bash
