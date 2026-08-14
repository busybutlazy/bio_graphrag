# --- lint stage: dev tooling only, used by `make lint` / `make format` --------
# Deliberately NOT built on top of the runtime stage: installing only
# requirements-dev.txt reproduces exactly what CI's type-check has always seen
# (no runtime packages, so mypy's ignore_missing_imports still applies). Making
# mypy see real fastapi/pydantic types is a separate change, not this one.
# Kept FIRST on purpose: an untargeted `docker build` resolves to the LAST stage,
# which must stay the runtime image.
FROM python:3.12-slim AS lint

COPY requirements-dev.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt
# The repo is bind-mounted here by the compose `lint` service.
WORKDIR /repo

# --- runtime stage: the image the app actually runs as ------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY pytest.ini .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
