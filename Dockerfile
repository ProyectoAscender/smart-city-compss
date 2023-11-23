ARG ROOT_CONTAINER=registry.gitlab.bsc.es/ppc-bsc/software/compss/compss:2.10
FROM $ROOT_CONTAINER as builder

FROM ubuntu:18.04
WORKDIR /root
LABEL maintainer="Unai Perez <unai.perez@bsc.es>"

ENV JAVA_HOME=/usr/lib/jvm/java-8-openjdk-arm64


COPY --from=builder /opt/COMPSs /opt/COMPSs
COPY --from=builder /etc/profile.d/compss.sh /etc/profile.d/compss.sh
COPY --from=builder /usr/local/lib/python3.6 /usr/local/lib/python3.6

RUN apt update && \
    apt install -y openjdk-8-jre-headless uuid-runtime && \
    echo ". /etc/profile.d/compss.sh" >> /root/.bashrc

RUN apt install -qq -y openjdk-8-jre-headless openjdk-8-jdk openssh-server openssh-client uuid-runtime python3 python3-pip python3-setuptools libgmp3-dev flex bison libbison-dev texinfo libffi-dev libxml2 gfortran libpapi-dev papi-tools nano vim rsync
                            
# SSH
RUN apt install -qq -y openssh-server openssh-client && \
    ssh-keygen -q -N "" -f ~/.ssh/id_rsa && \
    cat ~/.ssh/id_rsa.pub > ~/.ssh/authorized_keys && \
    echo "StrictHostKeyChecking no" >> /etc/ssh/ssh_config && \
    service ssh start && \
    echo "service ssh start > /dev/null 2>&1" >> ~/.bashrc

# SSHPass
RUN apt install -y sshpass

# Tzdata
RUN DEBIAN_FRONTEND="noninteractive" apt install -y tzdata
RUN ln -fs /usr/share/zoneinfo/Europe/Madrid /etc/localtime && \
    echo Europe/Madrid > /etc/timezone


# Eigen 3
RUN apt install -y git cmake libeigen3-dev libflann-dev python3-matplotlib python-dev python-dev libflann-dev

RUN ln -s /usr/include/eigen3/Eigen /usr/include/Eigen


# Pybind11
RUN apt install -y python3-pip && python3 -m pip install pytest

RUN git clone https://github.com/pybind/pybind11.git && \
    cd pybind11 && \
    mkdir build && \
    cd build && \
    cmake .. && \
    make check -j8 && \
    make install




# Deduplicator dependencies
RUN apt install -y libeigen3-dev python3-matplotlib python-dev libgdal-dev libcereal-dev libyaml-cpp-dev libpthread-stubs0-dev


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


# Compss obstacle detection dependencies
RUN python3 -m pip install geolib pymap3d zmq requests pygeohash paho-mqtt pandas shapely geopandas

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

RUN git clone https://pat:gc7sMZHxho-jyyFfcQRi@gitlab.bsc.es/ppc/benchmarks/smart-city/smart-city-compss.git
# # Tracker class project
RUN git clone https://pat:zn1XXoMgB4896i533XPo@gitlab.bsc.es/ppc/benchmarks/smart-city/tracker.git -b dev && \
    cd tracker && \
    git submodule update --init --recursive && \
    mkdir build  && \
    cd build && \
    cmake .. -DWITH_MATPLOTLIB=OFF && \
    make -j8

# RUN mkdir tracker
# COPY tracker ./tracker

RUN ls && cp /root/tracker/build/track.cpython-36m-aarch64-linux-gnu.so smart-city-compss/lib/
#RUN cp /root/deduplicator/build/deduplicator.cpython-36m-aarch64-linux-gnu.so smartcity-compss/lib
    # cp /root/deduplicator/build/deduplicator.cpython-36m-x86_64-linux-gnu.so . && \


# RUN mkdir -p /root/data/florencia/batoni/roi/
# COPY roi/ /root/data/florencia/batoni/roi/
RUN mkdir -p /root/data 
# Establishing entrypoint for downloading the stubs and making the image ready at runtime
WORKDIR /root/smartcity-compss
# ENTRYPOINT ["./entrypoint.sh"]