FROM python:3.11-slim

# Install system dependencies (untuk traceroute, ping, tzdata, VPN tools, dll)
RUN apt-get update && apt-get install -y \
    traceroute \
    iputils-ping \
    tzdata \
    sudo \
    sstp-client \
    ppp \
    xl2tpd \
    strongswan \
    iproute2 \
    iptables \
    kmod \
    procps \
    util-linux \
    wget \
    && wget -q https://github.com/osrg/gobgp/releases/download/v3.26.0/gobgp_3.26.0_linux_amd64.tar.gz \
    && tar -xzf gobgp_3.26.0_linux_amd64.tar.gz \
    && mv gobgp /usr/local/bin/ \
    && rm -f gobgpd gobgp_3.26.0_linux_amd64.tar.gz \
    && rm -rf /var/lib/apt/lists/*

# Set timezone ke WIB (Asia/Jakarta)
ENV TZ=Asia/Jakarta
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Build-time argument untuk mengetahui versi commit
ARG APP_COMMIT_SHA="docker"
ENV APP_VERSION_COMMIT=${APP_COMMIT_SHA}

WORKDIR /app

# Menyalin requirements (agar Docker bisa me-ng-cache layer ini jika tidak berubah)
COPY requirements.txt .

# Install dependencies Python
RUN pip install --no-cache-dir -r requirements.txt

# Menyalin seluruh kode backend
COPY . .

# Ekspos port FastAPI default
EXPOSE 8000
# Ekspos port Syslog dan NetFlow jika diperlukan
EXPOSE 5514/udp
EXPOSE 2055/udp
# Port BGP 179 ditangani langsung oleh gobgpd di HOST Ubuntu (systemd service)
# Tidak perlu EXPOSE di container

# Jalankan server.py (pastikan main app listen ke 0.0.0.0)
CMD ["python", "server.py"]
