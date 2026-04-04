# Meteofrance to OpenHASP sender

Meteofrance2OpenHASP is a gateway that reads data from Meteo France (the French weather service) posts it to a MQTT message broker for direct consumption by OpenHASP plates.

## Installation and Running

Meteofrance2OpenHASP can be used and installed in two ways.

### 1. As a python script

1. Fetch the code from github
2. Install the python dependencies. If you do it via a virtual environment, do:

    ```sh
    cd /path/to/my_install_folder/
    cd sender/meteofrance2openhasp
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

3. Prepare the configuration files. See the [Configuration section below](#configuration).
4. Run the program. If you do it via a virtual environment, do:

    ```sh
    cd /path/to/my_install_folder/
    cd sender/meteofrance2openhasp
    source .venv/bin/activate
    cd ..
    python3 meteofrance2openhasp -c config/configuration.yaml -s config/secrets.yaml
    ```

### 2. Using Containers ("docker")

The following steps allow you to run the program in a container. Since the container image is not published, you will need to build the image yourself and make sure the image arrives on the server that will run the container.

The following steps show you how to build the Docker image based on the local source files.

1. Fetch the code from github
2. Build the image:

    ```sh
    cd /path/to/my_install_folder/
    cd sender/
    cp docker/docker-compose.yaml .
    docker compose build
    ```

    This will have inserted the `hb020/meteofrance2openhasp:latest` image in the local container store.

    If you want more options, you can for example do the following to force a full rebuild from another Dockerfile, without cache, with more explicit logs, into a different tag: ```docker image build . -f docker/Dockerfile --no-cache --progress=plain --tag hb020/meteofrance2openhasp:beta```

3. If you want to run the image on another server, copy the image there:
   1. ```docker save -o <path for generated tar file> <image name>```
   2. copy the tar file to the destination, and on the target:
   3. ```docker load -i <path to image tar file>```
4. Prepare the configuration files. See the [Configuration section below](#configuration).
5. Set up the `docker-compose.yaml` file, potentially together with other containers if you want.
6. Run the container:

    ```sh
    docker compose up -d
    ```

This will run the container in detached mode, and will by default use the local `./config` and `./log` folders for configuration and logging.

Alternatively you can also do one of the following to see what is going on:

* ```docker compose up``` will not run in detached mode: the logs will be on the console.
* ```docker run --rm -it --entrypoint bash hb020/meteofrance2openhasp:latest```, will let you start the container but not the program. You will be in the container and you can do more in depth debugging, like see if `entrypoint.sh` has problems.

## Configuration

The configuration is to be provided using two YAML files: a configuration file and a secret file. The latter is used to fill in the `!secret xxxxx` parts in the configuration file.

Both these files may or may not use environment variables.

The construction of the effective configuration works the same for all installation types. In order to assist in debugging, the application will log, at startup, the effective configuration as constructed from the config file, the secret file, and any environment variables that are used.

### Configuration files

The default configuration file is below.

```yaml
logging:
  file: log/meteofrance2openhasp.log # Path to the log file. If not provided, logging to file is disabled, and logging to console will be enabled.
  console: true
  level: info
  format: '%(asctime)s %(levelname)s [%(name)s] %(message)s'

sender:
  scan_interval: 5         # Number of minutes between each data retrieval (0 means no scan: a single data retrieval at startup, then stops).
  city: "Paris"            # City for which to retrieve the data.
  plates:
  - name: plate01
    start_page: 2          # the page number for the main weather page
    nr_days_detail: 4      # the number of pages with detail weather
    extra_tempnow: p11b7   # the element to which to replicate temp now, for example to "idle" page. Leave empty if not needed.
    extra_iconnow: p11b6   # the element to which to replicate weather icon now, for example to "idle" page. Leave empty if not needed.
  - name: plate02
    start_page: 3          # the page number for the main weather page
    nr_days_detail: 4      # the number of pages with detail weather
    extra_tempnow: p12b7   # the element to which to replicate temp now, for example to "idle" page. Leave empty if not needed.
    extra_iconnow: p12b6   # the element to which to replicate weather icon now, for example to "idle" page. Leave empty if not needed.

mqtt:
  mock: false              # If true, it will not send to MQTT, but will log at info level. This is useful for testing the configuration without sending data to MQTT.
  broker: "!secret mqtt.broker"
  port: "!secret mqtt.port"
  username: "!secret mqtt.username"
  password: "!secret mqtt.password"
  keepalive: 60
  base_topic: meteofrance2openhasp
```

The default secret file:

```yaml
mqtt.broker: "${MQTT_BROKER}"
mqtt.port: "${MQTT_PORT}"
mqtt.username: "${MQTT_USERNAME}"
mqtt.password: "${MQTT_PASSWORD}"
```

If you use the container and do not provide a configuration file or secret file, the above default templates will be used automatically: they will be copied to wherever you map `/app/config` to, the first time you execute the container. You must in that case however make sure that the container has the correct access rights, in order to be able to write those files.

If you set `scan_interval` to 0, the program will do a single weather update, and then will stop. This is useful if you want to run the program via cron, for example every hour.

### Environment variables

By default, the configuration files make use of the environment variables below:

| Environment variable | Description                                                                   | Required | Default value  |
| -------------------- | ----------------------------------------------------------------------------- | -------- | -------------- |
| MQTT_BROKER          | MQTT broker IP address                                                        | Yes      | -              |
| MQTT_PORT            | MQTT broker port number                                                       | No       | 1883           |
| MQTT_USERNAME        | MQTT broker account user name                                                 | No       | ""             |
| MQTT_PASSWORD        | MQTT broker account password                                                  | No       | ""             |

It is however not mandatory to use these variables; you are free to rename them, or to not use them, as long as you adapt the configuration files accordingly.

If you use containers, environment variables are often the easiest way to provide secrets to the application.
You can set them directly in a docker-compose.yaml file (environment section) or from a Docker command line (-e option).
