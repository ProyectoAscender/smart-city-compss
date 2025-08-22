ARG ROOT_CONTAINER=oriolmac/compss-nvidia-debug:3.3
FROM $ROOT_CONTAINER AS builder

WORKDIR /root

# 1) Paquetes base + Python toolchain (incluye pip, dev headers y numpy ANTES de compilar OpenCV)
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential cmake git pkg-config \
    python3 python3-pip python3-dev python3-venv \
    libgtk-3-dev libavcodec-dev libavformat-dev libswscale-dev \
    libtbb2 libtbb-dev libjpeg-dev libpng-dev libtiff-dev \
    libdc1394-22-dev libv4l-dev v4l-utils \
    gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    libgstreamer-plugins-base1.0-dev \
    libgdal-dev libeigen3-dev nano vim \
 && rm -rf /var/lib/apt/lists/*

# Asegurar pip actualizado y Numpy disponible (OpenCV CMake lo interroga)
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel numpy

# 2) Compilar OpenCV con GStreamer (OJO: sin trailing spaces en las barras invertidas)
RUN git clone --branch 4.x --depth 1 https://github.com/opencv/opencv.git && \
    git clone --branch 4.x --depth 1 https://github.com/opencv/opencv_contrib.git && \
    mkdir -p /root/opencv/build && cd /root/opencv/build && \
    cmake -D CMAKE_BUILD_TYPE=RELEASE \
          -D CMAKE_INSTALL_PREFIX=/usr/local \
          -D OPENCV_EXTRA_MODULES_PATH=/root/opencv_contrib/modules \
          -D WITH_GSTREAMER=ON \
          -D WITH_FFMPEG=ON \
          -D BUILD_EXAMPLES=OFF \
          -D BUILD_opencv_java=OFF \
          -D BUILD_opencv_python2=OFF \
          -D BUILD_opencv_python3=ON \
          -D PYTHON3_EXECUTABLE=$(command -v python3) \
          -D PYTHON3_PACKAGES_PATH=$(python3 -c "import site; print(site.getsitepackages()[0])") \
          -D PYTHON3_INCLUDE_DIR=$(python3 -c "import sysconfig; print(sysconfig.get_path('include'))") \
          -D PYTHON3_NUMPY_INCLUDE_DIRS=$(python3 -c "import numpy; print(numpy.get_include())") \
          .. && \
    make -j"$(nproc)" && \
    make install && \
    ldconfig

# Verificación GStreamer en la build de OpenCV
RUN python3 - <<'PY' | grep -i gstreamer || (echo 'ERROR: OpenCV no tiene GStreamer' && exit 1)
import cv2
print(cv2.getBuildInformation())
PY

# 3) (Opcional) GDAL/ubuntugis (si de verdad lo necesitas). Mejor evitar PPA si no es imprescindible.
# Si lo requieres, descomenta:
# RUN apt-get update -y && apt-get install -y --no-install-recommends gdal-bin && \
#     echo 'GDAL VERSION:' && ogrinfo --version

# 4) Clonar el repo de smart-city-compss (usa deploy key/token via ARG/—mount, NO hardcode)
#    ⚠️ Elimina/rota tu token: lo has expuesto en el historial.
ARG GIT_USER=gitlab-ci-token
ARG GIT_TOKEN=***REPLACE_ME***
RUN --mount=type=secret,id=git_token \
    GIT_TOKEN="$(cat /run/secrets/git_token || echo "$GIT_TOKEN")" && \
    git clone https://${GIT_USER}:${GIT_TOKEN}@gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss.git -b LisDevelop

# 5) Fijar WORKDIR al proyecto (coherente con lo que luego usas en COMPSs)
WORKDIR /root/smart-city-compss

# 6) Instalar dependencias Python del proyecto
#    (Evita fallos si requirements.txt usa GDAL: en tal caso añade 'pip install gdal==<versión>')
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# 7) Miscelánea
RUN mkdir -p /root/b2drop
ENV PYDEVD_WARN_EVALUATION_TIMEOUT=30

# 8) (Opcional) X11 utils si realmente lo necesitas
RUN apt-get update -y && apt-get install -y --no-install-recommends x11-apps && rm -rf /var/lib/apt/lists/*

LABEL org.opencontainers.image.source="https://github.com/proyectoAscender/smart-city-compss"

# ENTRYPOINT ["./entrypoint.sh"]
