FROM debian:bookworm-slim

# Build dependencies for BFGMiner + USB diagnostic tools
RUN apt-get update && apt-get install -y \
    autoconf \
    automake \
    libtool \
    pkg-config \
    libcurl4-gnutls-dev \
    libjansson-dev \
    libudev-dev \
    libusb-1.0-0-dev \
    libncurses5-dev \
    uthash-dev \
    libevent-dev \
    libhidapi-dev \
    git \
    make \
    usbutils \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Redirect git:// -> https:// because GitHub disabled the git protocol (port 9418).
# The libblkmaker submodule uses git:// and would fail otherwise.
RUN git config --global url."https://".insteadOf git://
RUN git clone https://github.com/luke-jr/bfgminer.git /opt/bfgminer-src
WORKDIR /opt/bfgminer-src
RUN ./autogen.sh && \
    ./configure --prefix=/opt/bfgminer --enable-nanofury && \
    make -j$(nproc) && \
    make install && \
    echo "/opt/bfgminer/lib" > /etc/ld.so.conf.d/bfgminer.conf && ldconfig

ENV PATH="/opt/bfgminer/bin:${PATH}"
ENV TERM=xterm

WORKDIR /opt/bfgminer/bin
ENTRYPOINT ["/opt/bfgminer/bin/bfgminer"]
