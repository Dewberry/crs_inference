FROM python:3.12-slim

WORKDIR /app

# Install dependencies before copying source so this layer is cached
COPY pyproject.toml .
RUN mkdir -p src/crs_finder && touch src/crs_finder/__init__.py \
    && pip install --no-cache-dir . \
    && rm -rf src/crs_finder/__init__.py

COPY src/ src/

EXPOSE 8000

CMD ["uvicorn", "crs_finder.main:app", "--host", "0.0.0.0", "--port", "8000"]
