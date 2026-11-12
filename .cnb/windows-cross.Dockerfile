FROM node:24.14.0-bookworm

# Tauri CLI checks the host tray library even when bundling a Windows target.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates clang lld llvm nsis python3 python3-venv \
       cmake ninja-build pkg-config libayatana-appindicator3-dev \
    && pkg-config --exists ayatana-appindicator3-0.1 \
    && rm -rf /var/lib/apt/lists/*

ENV CARGO_HOME=/root/.cargo RUSTUP_HOME=/root/.rustup
ENV PATH=/opt/cargo-xwin/bin:/root/.cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup.sh \
    && sh /tmp/rustup.sh -y --profile minimal --default-toolchain 1.96.0 \
    && rustup target add x86_64-pc-windows-msvc \
    && rm /tmp/rustup.sh \
    && python3 -m venv /opt/cargo-xwin \
    && /opt/cargo-xwin/bin/pip install --no-cache-dir cargo-xwin==0.23.1
