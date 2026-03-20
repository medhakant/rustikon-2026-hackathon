# Rust HTTP Server

A simple local HTTP server built with standard Rust libraries (`std::net::TcpListener`) for the Rustikon 2026 Hackathon.

## Prerequisites

- [Rust Toolchain](https://rustup.rs/) (includes `rustc` and `cargo`). 

## How to Run Locally

You can run the server directly using Cargo:

```bash
cargo run
```

This will compile and start the server, which will listen for incoming HTTP connections.

Alternatively, if you wish to build it first and test the release build:

```bash
# Build the binary
cargo build --release

# Run the binary
./target/release/rust_http_server
```

## How to Run with Docker

You can use Docker to run the server in an isolated container without needing the Rust toolchain installed locally. This uses the multi-stage `Dockerfile` and builds a lightweight runtime image.

1. **Build the Docker image**:
```bash
docker build -t rust-web-server .
```

2. **Run the Docker container**:
```bash
docker run -p 8080:8080 rust-web-server
```

## Testing the Server

Once the server is running, it will output: `Server running on http://127.0.0.1:8080`.

You can test the server using:
- **Browser**: Open your web browser and navigate to [http://127.0.0.1:8080](http://127.0.0.1:8080).
- **cURL**: Run `curl http://127.0.0.1:8080` in your terminal.

You should receive the following response text:
`Welcome to Rust hackaton`
