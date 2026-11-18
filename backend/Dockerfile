# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so code changes don't bust the dependency layer.
COPY pyproject.toml ./
RUN mkdir -p app scripts && touch app/__init__.py scripts/__init__.py \
 && pip install . \
 && rm -rf app scripts

COPY . .
RUN pip install --no-deps .

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
