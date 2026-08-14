FROM python:3.12-slim

WORKDIR /process

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra ops

COPY crs_inference/ crs_inference/
COPY pyproject.toml README.md ./

RUN uv pip install --no-deps -e .
