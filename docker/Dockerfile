ARG ROOT_CONTAINER=registry.gitlab.bsc.es/ppc/software/compss/compss_nvidia:3.3-arm
FROM nvcr.io/nvidia/l4t-cuda:11.4.19-devel  as builder

# RUN apt update -y && apt install -y python3-pip software-properties-common
# RUN wget https://pypi.jetson-ai-lab.dev/jp5/cu114/+f/e6a/f633b44affeef/opencv_python-4.10.0-py3-none-any.whl#sha256=e6af633b44affeef80149711a4a24451b3b6e4b7c65801694bf59edcbba24103 && \ 
#     python3 -m pip install opencv_python-4.10.0-py3-none-any.whl
# RUN python3 -c "import cv2; print('OpenCV version:', str(cv2.__version__)); print(cv2.getBuildInformation())"
ARG OPENCV_VERSION \
    OPENCV_PYTHON \
    OPENCV_URL \
    CUDA_ARCH_BIN \
    FORCE_BUILD="on"
ENV OPENCV_VERSION=${OPENCV_VERSION} \
    OPENCV_URL=${OPENCV_URL}
RUN apt update -y && apt install -y python3-pip software-properties-common
    
RUN echo "Copying opencv files..."
RUN mkdir -p /tmp/opencv
WORKDIR /tmp/opencv

# Instal cudnn
RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/arm64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    apt-get update && \
    apt-get -y install nvidia-cudnn8-dev
    
    # RUN python -m pip install --upgrade pip
    RUN pip install packaging
    
    COPY docker/opencv/build.sh \
    docker/opencv/install.sh \
    docker/opencv/install_deps.sh \
    docker/opencv/install_cudnn.sh \
    docker/opencv/patches.diff \
    docker/opencv/get_opencv_args.py \
    docker/opencv/get_cudnn_args.py \
    docker/opencv/l4t_version.py \
    ./

RUN python3 -c "import cv2; print('OpenCV version:', str(cv2.__version__)); print(cv2.getBuildInformation())"

# RUN apt-get update && \
#     apt-get install zlib1g && \
#     wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/arm64/cuda-keyring_1.1-1_all.deb &&\
#     dpkg -i cuda-keyring_1.1-1_all.deb && \
#     apt update && \
#     apt-get -y install cudnn9-cuda-11


# RUN CUDNN_ARGS=$(python3 get_cudnn_args.py) && echo $CUDNN_ARGS && \
#     eval $CUDNN_ARGS && \
#     echo $CUDNN_ARGS && \
#     bash install_cudnn.sh || echo "Install CUDNN FAILED" 


RUN echo ${OPENCV_VERSION}  && \
    BUILD_ARGS=$(python3 get_opencv_args.py ${OPENCV_VERSION}) && echo $BUILD_ARGS && \
    eval $BUILD_ARGS && \
    echo $OPENCV_VERSION && echo $OPENCV_PYTHON && echo $OPENCV_URL && echo $CUDA_ARCH_BIN && echo $FORCE_BUILD && \
    echo $BUILD_ARGS && \
    bash install.sh || bash build.sh || echo "BUILD FAILED (OpenCV ${OPENCV_VERSION})"

RUN echo hola
# FROM $ROOT_CONTAINER
FROM nvcr.io/nvidia/l4t-cuda:11.4.19-devel
RUN mkdir -p /tmp/opencv/deb/
WORKDIR /tmp/opencv/
COPY --from=builder /tmp/debs/ .
COPY docker/opencv/opencv_install_debs.sh .
# ARG OPENCV_VERSION="4.7.0"
RUN bash /tmp/opencv/opencv_install_debs.sh

























# # RUN mkdir /root/opencv
# # RUN echo holaaaaaaa
# # COPY docker/build_opencv.sh build_opencv.sh 
# # RUN bash build_opencv.sh  ${OPENCV_VERSION} 
# # RUN cd /tmp/build_opencv/opencv/build && make package


# COPY docker/opencv_install_deps.sh opencv_install_deps.sh 
# RUN bash opencv_install_deps.sh
# COPY docker/opencv_install.sh opencv_install.sh 
# RUN bash opencv_install.sh
# # RUN ./OpenCV-4.7.0-aarch64.sh --prefix=/usr/local --skip-license
# # RUN apt update && apt install -y libzmq3-dev x11-apps
