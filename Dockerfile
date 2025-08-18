# ARG ROOT_CONTAINER=oriolmac/compss-nvidia-debug:3.3
# FROM $ROOT_CONTAINER AS builder

# # FROM ubuntu:18.04
# WORKDIR /root


# # Install base dependencies
# RUN apt-get update -y && apt-get install -y --no-install-recommends \
#     build-essential cmake git pkg-config \
#     libgtk-3-dev libavcodec-dev libavformat-dev libswscale-dev \
#     libtbb2 libtbb-dev libjpeg-dev libpng-dev libtiff-dev \
#     libdc1394-22-dev libv4l-dev v4l-utils \
#     gstreamer1.0-tools gstreamer1.0-plugins-base \
#     gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
#     gstreamer1.0-plugins-ugly gstreamer1.0-libav \
#     libgstreamer-plugins-base1.0-dev \
#     libgdal-dev libeigen3-dev nano vim \
#     && rm -rf /var/lib/apt/lists/*

# # Clone and build OpenCV with GStreamer & CUDA support
# RUN git clone --branch 4.x --depth 1 https://github.com/opencv/opencv.git && \
#     git clone --branch 4.x --depth 1 https://github.com/opencv/opencv_contrib.git && \
#     mkdir -p opencv/build && cd opencv/build && \
#     cmake -D CMAKE_BUILD_TYPE=RELEASE \
#           -D CMAKE_INSTALL_PREFIX=/usr/local \
#           -D OPENCV_EXTRA_MODULES_PATH=/root/opencv_contrib/modules \
#           -D WITH_GSTREAMER=ON \
#           -D WITH_FFMPEG=ON \
#           -D BUILD_EXAMPLES=OFF \
#           -D BUILD_opencv_java=OFF \ 
#           -D PYTHON_EXECUTABLE=$(which python3) \
#           -D PYTHON3_PACKAGES_PATH=$(python3 -c "import site; print(site.getsitepackages()[0])") \
#           -D PYTHON3_INCLUDE_DIR=$(python3 -c "import sysconfig; print(sysconfig.get_path('include'))") \
#           -D PYTHON3_NUMPY_INCLUDE_DIRS=$(python3 -c "import numpy; print(numpy.get_include())") \
#           .. && \
#     make -j"$(nproc)" && \
#     make install && \
#     ldconfig

# # Verify OpenCV installation
# RUN python3 -c "import cv2; print(cv2.getBuildInformation())" | grep -i gstreamer || \
#     (echo 'ERROR: OpenCV was not built with GStreamer support!' && exit 1)






# RUN apt update -y && apt install -y software-properties-common

# # Deduplicator dependencies
# RUN add-apt-repository ppa:ubuntugis/ppa &&  \
#     apt update -y && \
#     apt-get install -y gdal-bin && \
#     echo 'GDAL VERSION:   ' && ogrinfo --version
#     # Version needs to be inserted into requirements txt
# RUN export CPLUS_INCLUDE_PATH=/usr/include/gdal && \ 
#     export C_INCLUDE_PATH=/usr/include/gdal
# RUN apt install -y libgdal-dev
# # RUN pip install GDAL==3.0.4 && 
# # RUN pip install fiona==1.8


# # RUN apt install -y libeigen3-dev python3-matplotlib python-dev libgdal-dev libcereal-dev libyaml-cpp-dev libpthread-stubs0-dev


# # # Deduplicator project
# # RUN git clone https://gitlab.bsc.es/ppc-bsc/software/deduplicator -b bsc && \
# #     cd deduplicator && \
# #     git submodule update --init --recursive && \
# # #    sed -i '64s/.*/    double error;    \/\/ in meter/' masa_protocol/include/objects.hpp && \
# # #    sed -i '69s/.*/    int idx;\n    int idy;\n/' masa_protocol/include/objects.hpp && \
# # #    sed -i '75s/.*/        archive( camera_id, latitude, longitude, object_id, error, speed, orientation, category, idx, idy );/' masa_protocol/include/objects.hpp && \
# #     mkdir build && \
# #     cd build && \
# #     cmake .. && \
# #     make -j8

# RUN echo hola
# RUN git clone https://pat:gc7sMZHxho-jyyFfcQRi@gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss.git -b newtracker
# WORKDIR /root/smart-city-compss
# # Compss obstacle detection dependencies
# # COPY requirements.txt requirements.txt


# # Then install your requirements
# RUN python3 -m pip install -r requirements.txt


# # Compss obstacle detection
# # Tracker class project
# # RUN git clone https://gitlab.bsc.es/ppc-bsc/software/tracker_CLASS.git -b dev && \
# #     cd tracker_CLASS && \
# #     cat src/modules.cpp && \ 
# #     git submodule update --init --recursive && \
# #     mkdir build  && \
# #     cd build && \
# #     cmake .. -DWITH_MATPLOTLIB=OFF && \
# #     make -j8

# # # Tracker class project
# # RUN git clone https://pat:zn1XXoMgB4896i533XPo@gitlab.bsc.es/ppc/benchmarks/smart-city/tracker.git -b dev && \
# #     cd tracker && \
# #     git submodule update --init --recursive && \
# #     mkdir build  && \
# #     cd build && \
# #     cmake .. -DWITH_MATPLOTLIB=OFF && \
# #     make -j8

# # RUN mkdir tracker
# # COPY tracker ./tracker

# # RUN ls && cp /root/tracker/build/track.cpython-36m-aarch64-linux-gnu.so smart-city-compss/lib/
# #RUN cp /root/deduplicator/build/deduplicator.cpython-36m-aarch64-linux-gnu.so smartcity-compss/lib
#     # cp /root/deduplicator/build/deduplicator.cpython-36m-x86_64-linux-gnu.so . && \


# # RUN mkdir -p /root/data/florencia/batoni/roi/
# # COPY roi/ /root/data/florencia/batoni/roi/
# RUN mkdir -p /root/b2drop 
# # Avoid warn message when waiting too much for getting path data from b2drop
# ENV PYDEVD_WARN_EVALUATION_TIMEOUT 30
# RUN apt install -y x11-apps
# LABEL org.opencontainers.image.source https://github.com/proyectoAscender/smart-city-compss

# # Establishing entrypoint for downloading the stubs and making the image ready at runtime
# # ENTRYPOINT ["./entrypoint.sh"]

ARG ROOT_CONTAINER=oriolmac/compss-nvidia-debug:3.3
FROM $ROOT_CONTAINER AS builder

WORKDIR /root
ARG DEBIAN_FRONTEND=noninteractive

# Show base distro (helps debugging Debian vs Ubuntu vs version)
RUN cat /etc/os-release || true

# Core build deps + Python (for OpenCV Python bindings)
# - Use BuildKit cache mounts for apt for speed/reliability
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    set -eux; \
    apt-get update -o Acquire::Retries=5 -o Acquire::http::Timeout=30; \
    # If base is Ubuntu, enable universe (no-op on Debian)
    (command -v add-apt-repository >/dev/null || apt-get install -y --no-install-recommends software-properties-common) || true; \
    (grep -qi ubuntu /etc/os-release && add-apt-repository -y universe && apt-get update -o Acquire::Retries=5) || true; \
    apt-get install -y --no-install-recommends \
        ca-certificates apt-transport-https gnupg dirmngr \
        build-essential cmake git pkg-config \
        python3 python3-dev python3-pip python3-setuptools python3-wheel \
        libgtk-3-dev libavcodec-dev libavformat-dev libswscale-dev \
        libtbb2 libtbb-dev libjpeg-dev libpng-dev libtiff-dev \
        libdc1394-dev libv4l-dev v4l-utils \
        gstreamer1.0-tools gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-ugly gstreamer1.0-libav \
        libgstreamer-plugins-base1.0-dev \
        libgdal-dev libeigen3-dev nano vim; \
    rm -rf /var/lib/apt/lists/*

# Ensure numpy exists before running OpenCV CMake (it needs include dirs)
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir numpy

# Build OpenCV (with GStreamer & FFmpeg)
RUN git clone --branch 4.x --depth 1 https://github.com/opencv/opencv.git && \
    git clone --branch 4.x --depth 1 https://github.com/opencv/opencv_contrib.git && \
    mkdir -p opencv/build && cd opencv/build && \
    cmake -D CMAKE_BUILD_TYPE=RELEASE \
          -D CMAKE_INSTALL_PREFIX=/usr/local \
          -D OPENCV_EXTRA_MODULES_PATH=/root/opencv_contrib/modules \
          -D WITH_GSTREAMER=ON \
          -D WITH_FFMPEG=ON \
          -D BUILD_EXAMPLES=OFF \
          -D BUILD_opencv_java=OFF \
          -D PYTHON3_EXECUTABLE=$(command -v python3) \
          -D PYTHON3_PACKAGES_PATH=$(python3 -c "import site; print(site.getsitepackages()[0])") \
          -D PYTHON3_INCLUDE_DIR=$(python3 -c "import sysconfig; print(sysconfig.get_path('include'))") \
          -D PYTHON3_NUMPY_INCLUDE_DIRS=$(python3 -c "import numpy; print(numpy.get_include())") \
          .. && \
    make -j"$(nproc)" && \
    make install && \
    ldconfig

# Verify GStreamer is enabled
RUN python3 -c "import cv2; print(cv2.getBuildInformation())" | grep -i gstreamer

# (Optional) GDAL from PPA — only if base is Ubuntu. Guard it.
# If you truly need ubuntugis PPA (newer GDAL), keep this guarded block:
RUN set -eux; \
    if grep -qi ubuntu /etc/os-release; then \
      apt-get update -o Acquire::Retries=5; \
      apt-get install -y --no-install-recommends software-properties-common; \
      add-apt-repository -y ppa:ubuntugis/ppa; \
      apt-get update -o Acquire::Retries=5; \
      apt-get install -y --no-install-recommends gdal-bin libgdal-dev; \
      rm -rf /var/lib/apt/lists/*; \
      ogrinfo --version || true; \
    fi

# Set GDAL include paths for any later native builds (use ENV not export)
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal \
    C_INCLUDE_PATH=/usr/include/gdal

# Smart-city project (⚠️ Avoid keeping PATs in Dockerfiles; use build args or CI secrets)
# RUN git clone https://pat:<TOKEN>@gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss.git -b newtracker
RUN git clone https://gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss.git -b newtracker
WORKDIR /root/smart-city-compss

# Install Python deps for the project
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# X11 tools (refresh index first)
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    set -eux; \
    apt-get update -o Acquire::Retries=5; \
    apt-get install -y --no-install-recommends x11-apps; \
    rm -rf /var/lib/apt/lists/*

ENV PYDEVD_WARN_EVALUATION_TIMEOUT=30
LABEL org.opencontainers.image.source="https://github.com/proyectoAscender/smart-city-compss"
