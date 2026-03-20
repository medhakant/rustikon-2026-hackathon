FROM rust:1.94-slim AS builder

# Install build dependencies (pkg-config, libopencv-dev and clang are required for compiling the opencv rust crate)
RUN apt-get update && apt-get install -y \
    pkg-config \
    libopencv-dev \
    clang \
    libclang-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

# Cache dependencies by building them first separately
COPY Cargo.toml Cargo.lock ./
RUN mkdir src \
    && echo "fn main() { println!(\"If you see this, the build failed.\"); }" > src/main.rs \
    && cargo build --release \
    && rm -rf src

# Copy the actual source code
COPY src ./src

# Ensure main.rs is touched so cargo knows the source changed, then build the real release binary
RUN touch src/main.rs \
    && cargo build --release

# The final runtime image
FROM debian:bookworm-slim

# Install runtime dependencies needed by the opencv crate
RUN apt-get update && apt-get install -y \
    libopencv-core406 \
    libopencv-highgui406 \
    libopencv-imgproc406 \
    libopencv-videoio406 \
    # If specific versions aren't found, falling back to libopencv-dev guarantees the shared libs are present
    libopencv-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the compiled binary from the builder environment
COPY --from=builder /usr/src/app/target/release/rust_http_server /usr/local/bin/rust_http_server

# Expose the server port that is mentioned in README.md
EXPOSE 8080

# Run the server
CMD ["rust_http_server"]
