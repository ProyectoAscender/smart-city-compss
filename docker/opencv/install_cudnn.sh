#!/usr/bin/env bash
echo $CUDNN_URL
echo $CUDNN_DEB
echo $CUDNN_PACKAGES

ls /etc/apt/sources.list.d/ && \
    apt-get update && \
    apt-cache search cudnn

echo "Downloading ${CUDNN_DEB}" && \
    rm -rf /tmp/cudnn && mkdir /tmp/cudnn && cd /tmp/cudnn && \
    wget ${WGET_FLAGS} ${CUDNN_URL} && \
    dpkg -i *.deb && \
    cp /var/cudnn-*-repo-*/cudnn-*-keyring.gpg /usr/share/keyrings/ && \
    apt-get update && \
    apt-cache search cudnn && \
    apt list --installed | grep 'cuda\|cudnn\|cublas' && \
    apt-get install -y --no-install-recommends ${CUDNN_PACKAGES} file && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean && \
    dpkg --list | grep cudnn && \
    dpkg -P ${CUDNN_DEB} && \
    rm -rf /tmp/cudnn

cd /usr/src/cudnn_samples_v*/conv_sample/ && \
    make -j$(nproc)