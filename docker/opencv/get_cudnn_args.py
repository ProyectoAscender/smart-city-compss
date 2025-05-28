from l4t_version import L4T_VERSION, CUDA_VERSION, IS_TEGRA, IS_SBSA
from packaging.version import Version
import os
# Define the default CUDNN_VERSION either from environment variable or
# as to what version of cuDNN was released with that version of CUDA
if 'CUDNN_VERSION' in os.environ and len(os.environ['CUDNN_VERSION']) > 0:    
    CUDNN_VERSION = Version(os.environ['CUDNN_VERSION'])
else:
    if L4T_VERSION.major >= 36:
        if CUDA_VERSION >= Version('13.0'):
            CUDNN_VERSION = Version('10.0')
        elif CUDA_VERSION >= Version('12.8'):
            CUDNN_VERSION = Version('9.8')
        elif CUDA_VERSION == Version('12.6'):
            CUDNN_VERSION = Version('9.3')
        elif CUDA_VERSION == Version('12.4'):
            CUDNN_VERSION = Version('9.0')
        else:
            CUDNN_VERSION = Version('8.9')
    elif L4T_VERSION.major >= 34:
        CUDNN_VERSION = Version('8.6')
    elif L4T_VERSION.major >= 32:
        CUDNN_VERSION = Version('8.2')

CUDNN_URL='https://developer.download.nvidia.com/compute/cudnn'



pkg = package
    # Si el paquete es una tupla (contiene más de un diccionario)
if isinstance(pkg, tuple):
    for sub_pkg in pkg:
        if version in sub_pkg['name']:
            filtered_packages.append(sub_pkg)
# Si el paquete es un diccionario (solo un diccionario)
elif isinstance(pkg, dict):
    if version in pkg['name']:
        filtered_packages.append(pkg)
        
        
# Mostrar los paquetes filtrados
for x in filtered_packages:
    if f'opencv:{version}' == x['name']:
        out = x

for k, v in out['build_args'].items():
    if isinstance(v, dict):  # Si es un diccionario, podemos convertirlo en una cadena
        v = str(v)  # Convertimos el diccionario a cadena (esto es opcional dependiendo de cómo quieres que aparezca)
    # Imprime cada clave y valor como variable de entorno para bash
    print(f"export {k}={v}")