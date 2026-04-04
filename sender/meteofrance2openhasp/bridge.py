import json
import logging
import signal
import time

import paho.mqtt.client as mqtt

import config_utils
from send_weather import MeteoFrance2OpenHasp


# ----------------------------------
class Bridge:

    # ----------------------------------
    def __init__(self, config: config_utils.ConfigLoader):

        # Scan interval (in seconds)
        self._scan_interval = int(config.get("sender.scan_interval"))   # type: ignore

        # MQTT configuration
        if bool(config.get("mqtt.mock", False)):  # type: ignore
            logging.info("MQTT mock mode enabled. Data will not be sent to MQTT, but will be logged at info level.")
            self._mqtt_client = None
        else:
            self._mqtt_broker = config.get("mqtt.broker")
            if not isinstance(self._mqtt_broker, str):
                raise ValueError("MQTT broker address must be a string.")
            self._mqtt_port = int(config.get("mqtt.port"))  # type: ignore
            mqtt_username = config.get("mqtt.username")
            mqtt_password = config.get("mqtt.password")
            self._mqtt_keepalive = int(config.get("mqtt.keepalive"))  # type: ignore

            self._mqtt_base_topic = config.get("mqtt.base_topic")

            # Initialize MQTT client
            self._mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="meteofrance2openhasp", protocol=mqtt.MQTTv5)  # type: ignore
            self._mqtt_client.username_pw_set(mqtt_username, mqtt_password)  # type: ignore

            # Set up MQTT callbacks
            self._mqtt_client.on_connect = self.on_connect
            self._mqtt_client.on_disconnect = self.on_disconnect

        # Initialize MeteoFrance2OpenHasp
        self._sender = MeteoFrance2OpenHasp(self._mqtt_client)
        if not self._sender.load_config(config.get("sender")):   # type: ignore
            raise ValueError("Invalid sender configuration.")

        # Set up signal handler
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        # Initialize running flag
        self._running = False

    # ----------------------------------
    def on_connect(self, client, userdata, connect_flags, rc, properties):  # pylint: disable=unused-argument
        logging.info(f"Connected to MQTT broker with result: {rc}")
        
    # ----------------------------------
    def on_disconnect(self, client, userdata, disconnect_flags, rc, properties):  # pylint: disable=unused-argument
        logging.info("Disconnected from broker")

    # ----------------------------------
    # Graceful shutdown function
    def handle_signal(self, signum, frame):  # pylint: disable=unused-argument
        print(f"Signal {signum} received. Shutting down gracefully...")
        logging.info(f"Signal {signum} received. Shutting down gracefully...")
        self._running = False

    # ----------------------------------
    def run(self):

        # Start the network loop in a separate thread
        if self._mqtt_client:
            logging.info("Connecting to MQTT broker...")
            self._mqtt_client.connect(self._mqtt_broker, self._mqtt_port, self._mqtt_keepalive)  # type: ignore
            self._mqtt_client.loop_start()
            logging.info("Connected to MQTT broker.")

        # Set running flag
        self._running = True

        try:
            while self._running:
                # Publish data to MQTT
                logging.info("Fetching weather data and publishing to MQTT...")
                self._sender.publish_weather()
                logging.info("Data published to MQTT.")

                # Publish bridge availability
                if self._mqtt_client:
                    self._mqtt_client.publish(
                        f"{self._mqtt_base_topic}/bridge/availability",
                        json.dumps({"state": "online"}),
                        retain=True,
                        qos=2,
                    )

                # Wait before next scan
                logging.info(f"Waiting {self._scan_interval} minutes before next scan...")

                # Check if the scan interval is 0 and leave the loop.
                if self._scan_interval == 0:
                    time.sleep(5)  # flush out the MQTT queue. It seems that wait_for_publish() does not work properly 
                    break

                self._await_with_interrupt(self._scan_interval * 60, 5)
        except KeyboardInterrupt:
            print("Keyboard interrupt detected. Shutting down gracefully...")
            logging.info("Keyboard interrupt detected. Shutting down gracefully...")
        finally:
            # Publish bridge availability
            if self._mqtt_client:
                self._mqtt_client.publish(
                    f"{self._mqtt_base_topic}/bridge/availability",
                    json.dumps({"state": "offline"}),
                    retain=True,
                    qos=2
                )

            self.dispose()

    # ----------------------------------
    def dispose(self):
        # Dispose of MeteoFrance2OpenHasp.
        self._sender.dispose()

        # Stop the network loop
        if self._mqtt_client:
            logging.info("Disconnecting from MQTT broker...")
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()
            logging.info("Disconnected from MQTT broker.")

    # ----------------------------------
    def _await_with_interrupt(self, total_sleep_time: int, check_interval: int):
        elapsed_time = 0
        while elapsed_time < total_sleep_time:
            time.sleep(check_interval)
            elapsed_time += check_interval
            # Check if an interrupt signal or external event requires breaking
            if not self._running:  # Assuming `running` is a global flag
                break
