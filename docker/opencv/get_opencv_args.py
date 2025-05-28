import json
import sys
from packaging.version import Version

from l4t_version import (
  L4T_VERSION, LSB_RELEASES, l4t_version_from_tag, l4t_version_compatible, CUDA_VERSION, CUDA_ARCHITECTURES,
  get_l4t_base, get_l4t_version,get_cuda_arch, get_cuda_version, get_jetpack_version, get_lsb_release
)

def opencv(version, requires=None, default=False, url=None):
    cv = {}
    cv['build_args'] = {
        'OPENCV_VERSION': version,
        'OPENCV_PYTHON': f"{version.split('.')[0]}.x",
        'CUDA_ARCH_BIN': ','.join([f'{x/10:.1f}' for x in CUDA_ARCHITECTURES]),
    }
    if url:
        cv['build_args']['OPENCV_URL'] = url
        cv['name'] = f'opencv:{version}-deb'
        cv['alias'] = ['opencv:deb']
    else:
        cv['name'] = f'opencv:{version}'
    if requires:
        cv['requires'] = requires
    builder = cv.copy()
    builder['name'] = builder['name'] + '-builder'
    builder['build_args'] = {**builder['build_args'], 'FORCE_BUILD': 'on'}
    meta = cv.copy()
    meta['name'] = meta['name'] + '-meta'
    meta['depends'] = [cv['name']]
    meta['dockerfile'] = 'Dockerfile.meta'
    if default:
        cv['alias'] = cv.get('alias', []) + ['opencv']
        meta['alias'] = 'opencv:meta'
        builder['alias'] = 'opencv:builder'
    if url:
        return cv
    else:
        return cv, builder, meta

# def getVersionInfo():
#     data = {}
#     data['L4T_VERSION'] = get_l4t_version()
#     if not 'L4T_VERSION' in data:
#         print(f"Missing L4T_VERSION")
#         return data
#     l4t_version = data['L4T_VERSION']
#     data.setdefault('JETPACK_VERSION', get_jetpack_version(l4t_version=l4t_version))
#     data.setdefault('CUDA_VERSION', get_cuda_version(l4t_version=l4t_version))
#     data.setdefault('CUDA_ARCH2', get_cuda_arch(l4t_version=l4t_version, format=str))
#     data.setdefault('LSB_RELEASE', get_lsb_release(l4t_version=l4t_version))
#     for k,v in data.items():
#         if not v:
#             del k
#             continue
#         data[k] = str(v)
#     print('sadasd')
#     print(data)    
#     return data

# data = getVersionInfo()


if __name__ == '__main__':
    
    version = sys.argv[1] if len(sys.argv) > 1 else "4.8.1"
    
    packages = [
        # JetPack 5/6
        opencv('4.5.0', '==35.*', default=False),
        opencv('4.8.1', '>=35', default=(CUDA_VERSION <= Version('12.2'))),
        opencv('4.10.0', '>=35', default=(CUDA_VERSION >= Version('12.4') and CUDA_VERSION <= Version('12.6'))),
        opencv('4.11.0', '>=35', default=(CUDA_VERSION > Version('12.6'))),

        # JetPack 4
        opencv('4.5.0', '==32.*', default=True, url='https://nvidia.box.com/shared/static/5v89u6g5rb62fpz4lh0rz531ajo2t5ef.gz'),

        # Debians (c++)
        opencv('4.5.0', '==35.*', default=False, url='https://nvidia.box.com/shared/static/2hssa5g3v28ozvo3tc3qwxmn78yerca9.gz'),
        opencv('4.8.1', '==36.*', default=False, url='https://nvidia.box.com/shared/static/ngp26xb9hb7dqbu6pbs7cs9flztmqwg0.gz')
    ]

    filtered_packages = []
    for pkg in packages:
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
#     for pkg in package:
#         if isinstance(pkg, tuple):
#             args = pkg[0]['build_args']
#             if args['OPENCV_VERSION'] == version:
#                 break
#         elif isinstance(pkg, dict):
#             args = pkg['build_args']
#             if args['OPENCV_VERSION'] == version:
#                 break
#     else:
#         print(f"# No se encontró versión {version}")
#         sys.exit(1)

#     for k, v in args.items():
#             print(f"{k}={v}")