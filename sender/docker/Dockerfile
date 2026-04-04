# The builder image, used to build the virtual environment
FROM python:3.14-bookworm AS builder

WORKDIR /app

COPY README.md ./
COPY LICENSE ./

COPY meteofrance2openhasp/ /app/meteofrance2openhasp

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r /app/meteofrance2openhasp/requirements.txt

# Environment variables
# MQTT_BROKER: The hostname of the MQTT broker
# MQTT_PORT: The port of the MQTT broker
# MQTT_USERNAME: The username to use to authenticate to the MQTT broker
# MQTT_PASSWORD: The password to use to authenticate to the MQTT broker

# Install the required system dependencies: envsubst
RUN apt-get update && apt-get install -y gettext-base

WORKDIR /app

COPY docker/entrypoint.sh /app
RUN  chmod +x /app/entrypoint.sh
COPY meteofrance2openhasp/ /app/meteofrance2openhasp
RUN  mkdir /app/config
RUN  mkdir /app/log
COPY README.md /app
COPY CHANGELOG.md /app
COPY LICENSE /app
COPY config/configuration.template.yaml /app
COPY config/secrets.template.yaml /app

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
