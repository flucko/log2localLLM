# Log2LocalLLM

Log2LocalLLM is a lightweight, containerized utility designed to actively monitor Docker container logs, auto-detect errors, and stream those errors—along with surrounding context—to a local Ollama LLM (`gemma4:e4b` by default) for root cause analysis and resolution generation. It features a modern, real-time glassmorphism web dashboard to review findings.

## Features

- 🐳 **Native Docker Integration**: Attaches directly to the Docker socket to stream logs securely without relying on third-party aggregators.
- 🧠 **Local LLM Analysis**: Sends a snapshot of the error (including ~100ms of context lines before and after) to a locally running Ollama instance, protecting data privacy.
- 🎨 **Glassmorphism Dashboard**: A beautifully designed, responsive dark-mode Web UI that updates dynamically as errors occur.
- 🛑 **Smart Exclusions**: Easily click a button in the UI to suppress specific string patterns per-container (e.g., standard startup/restart logs), preventing LLM spam.
- 💾 **Stateful Analytics**: Stores historical queries and exclusion rules in a local Python SQLite database.

## Prerequisites

1.  **Docker & Docker Compose**: Necessary for running the backend and mounting the socket.
2.  **Ollama**: Install and run Ollama locally or on an accessible network host.
    ```bash
    ollama run gemma4:e4b
    ```

## Setup & Execution

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/yourusername/log2localllm.git
    cd log2localllm
    ```

2.  **Configure Environment Variables**
    Copy the template to your live environment file:
    ```bash
    cp .env.template .env
    ```
    Edit `.env` to ensure `OLLAMA_BASE_URL` points accurately to your Ollama API. If running on the local host with standard Docker Desktop, `http://host.docker.internal:11434` usually works directly out of the box.

3.  **Run the App**
    ```bash
    docker-compose up -d --build
    ```
    This will build the log processor and UI image and launch the container in the background.

4.  **Access the Dashboard**
    Open your browser to `http://localhost:8080`.

## Configuration Overview

Inside your `.env` file, the following flags are exposed:

- `OLLAMA_BASE_URL`: The URL/port of your Ollama listener (default: `http://host.docker.internal:11434`).
- `OLLAMA_MODEL`: Specific model targeted (default: `gemma4:e4b`).
- `ERROR_KEYWORDS`: Comma-separated list of keywords that trigger a dump to the LLM (default: `ERROR,FATAL,Exception,CRITICAL`).
- `IGNORE_CONTAINERS`: Comma-separated list of container names to bypass globally (e.g. `log2localllm,dozzle`).

## CI/CD 

This repository includes a GitHub Actions workflow (`.github/workflows/docker-publish.yml`) that automatically builds and pushes the image to GitHub Packages (`ghcr.io`) upon merging to `main` or cutting a GitHub release tag.
