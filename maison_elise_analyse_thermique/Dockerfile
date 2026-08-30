FROM python:3.12-slim

ARG BUILD_VERSION=0.1.0-dev.14
ARG BUILD_ARCH=amd64

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8099
CMD ["python", "-m", "app.haos_entrypoint"]
