FROM ubuntu:latest

RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates python3.12 python3.12-venv python3-pip

WORKDIR /process

# Install UV
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

# Install python dependencies
COPY pyproject.toml uv.lock ./
RUN uv venv .venv
RUN uv sync --frozen --no-install-project

# Copy project files
COPY . .

# Install the app
RUN uv pip install -e .
