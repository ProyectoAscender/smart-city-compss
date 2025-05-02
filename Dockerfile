ARG ROOT_CONTAINER=registry.gitlab.bsc.es/ppc/software/compss/compss_nvidia:3.3-arm
FROM $ROOT_CONTAINER as builder

# FROM ubuntu:18.04
WORKDIR /root


# Install base dependencies
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    build-essential cmake git pkg-config \
    libgtk-3-dev libavcodec-dev libavformat-dev libswscale-dev \
    libtbb2 libtbb-dev libjpeg-dev libpng-dev libtiff-dev \
    libdc1394-22-dev libv4l-dev v4l-utils \
    gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    libgstreamer-plugins-base1.0-dev \
    libgdal-dev libeigen3-dev nano vim \
    && rm -rf /var/lib/apt/lists/*

# Clone and build OpenCV with GStreamer & CUDA support
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
          -D PYTHON_EXECUTABLE=$(which python3) \
          -D PYTHON3_PACKAGES_PATH=$(python3 -c "import site; print(site.getsitepackages()[0])") \
          -D PYTHON3_INCLUDE_DIR=$(python3 -c "import sysconfig; print(sysconfig.get_path('include'))") \
          -D PYTHON3_NUMPY_INCLUDE_DIRS=$(python3 -c "import numpy; print(numpy.get_include())") \
          .. && \
    make -j"$(nproc)" && \
    make install && \
    ldconfig

# Verify OpenCV installation
RUN python3 -c "import cv2; print(cv2.getBuildInformation())" | grep -i gstreamer || \
    (echo 'ERROR: OpenCV was not built with GStreamer support!' && exit 1)






RUN apt update -y && apt install -y software-properties-common

# Deduplicator dependencies
RUN add-apt-repository ppa:ubuntugis/ppa &&  \
    apt update -y && \
    apt-get install -y gdal-bin && \
    echo 'GDAL VERSION:   ' && ogrinfo --version
    # Version needs to be inserted into requirements txt
RUN export CPLUS_INCLUDE_PATH=/usr/include/gdal && \ 
    export C_INCLUDE_PATH=/usr/include/gdal
RUN apt install -y libgdal-dev
# RUN pip install GDAL==3.0.4 && 
# RUN pip install fiona==1.8


# RUN apt install -y libeigen3-dev python3-matplotlib python-dev libgdal-dev libcereal-dev libyaml-cpp-dev libpthread-stubs0-dev


# # Deduplicator project
# RUN git clone https://gitlab.bsc.es/ppc-bsc/software/deduplicator -b bsc && \
#     cd deduplicator && \
#     git submodule update --init --recursive && \
# #    sed -i '64s/.*/    double error;    \/\/ in meter/' masa_protocol/include/objects.hpp && \
# #    sed -i '69s/.*/    int idx;\n    int idy;\n/' masa_protocol/include/objects.hpp && \
# #    sed -i '75s/.*/        archive( camera_id, latitude, longitude, object_id, error, speed, orientation, category, idx, idy );/' masa_protocol/include/objects.hpp && \
#     mkdir build && \
#     cd build && \
#     cmake .. && \
#     make -j8

RUN echo hola
RUN git clone https://pat:gc7sMZHxho-jyyFfcQRi@gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss.git -b newtracker
WORKDIR /root/smart-city-compss
# Compss obstacle detection dependencies
# COPY requirements.txt requirements.txt


# Then install your requirements
RUN python3 -m pip install -r requirements.txt


# Compss obstacle detection
# Tracker class project
# RUN git clone https://gitlab.bsc.es/ppc-bsc/software/tracker_CLASS.git -b dev && \
#     cd tracker_CLASS && \
#     cat src/modules.cpp && \ 
#     git submodule update --init --recursive && \
#     mkdir build  && \
#     cd build && \
#     cmake .. -DWITH_MATPLOTLIB=OFF && \
#     make -j8

# # Tracker class project
# RUN git clone https://pat:zn1XXoMgB4896i533XPo@gitlab.bsc.es/ppc/benchmarks/smart-city/tracker.git -b dev && \
#     cd tracker && \
#     git submodule update --init --recursive && \
#     mkdir build  && \
#     cd build && \
#     cmake .. -DWITH_MATPLOTLIB=OFF && \
#     make -j8

# RUN mkdir tracker
# COPY tracker ./tracker

# RUN ls && cp /root/tracker/build/track.cpython-36m-aarch64-linux-gnu.so smart-city-compss/lib/
#RUN cp /root/deduplicator/build/deduplicator.cpython-36m-aarch64-linux-gnu.so smartcity-compss/lib
    # cp /root/deduplicator/build/deduplicator.cpython-36m-x86_64-linux-gnu.so . && \


# RUN mkdir -p /root/data/florencia/batoni/roi/
# COPY roi/ /root/data/florencia/batoni/roi/
RUN mkdir -p /root/b2drop 
# Avoid warn message when waiting too much for getting path data from b2drop
ENV PYDEVD_WARN_EVALUATION_TIMEOUT 30
RUN apt install -y x11-apps
# Establishing entrypoint for downloading the stubs and making the image ready at runtime
# ENTRYPOINT ["./entrypoint.sh"]