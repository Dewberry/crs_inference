FROM python:3.12-slim

WORKDIR /app

# Install crs-inference (root library) — cached unless root pyproject/sources change
COPY pyproject.toml ./
COPY crs_inference/ ./crs_inference/
RUN pip install --no-cache-dir .

# Install backend app dependencies — cached unless backend pyproject.toml changes
COPY crs-finder/backend/pyproject.toml ./backend/
RUN mkdir -p backend/src/crs_finder && touch backend/src/crs_finder/__init__.py \
    && pip install --no-cache-dir ./backend/ \
    && rm -f backend/src/crs_finder/__init__.py

COPY crs-finder/backend/src/ ./backend/src/

ENV PYTHONPATH=/app/backend/src

EXPOSE 8000

CMD ["uvicorn", "crs_finder.main:app", "--host", "0.0.0.0", "--port", "8000"]
