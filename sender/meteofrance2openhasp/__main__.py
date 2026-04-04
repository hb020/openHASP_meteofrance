import argparse
import logging
import sys
import traceback

from version import __version__
import config_utils
from bridge import Bridge

Logger = logging.getLogger(__name__)


# ----------------------------------
def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        prog="meteofrance2openhasp",
        description="Gateway that reads data from Meteo France and posts it to a MQTT queue for consumption by OpenHASP plates.",
    )
    parser.add_argument("-v", "--version", action="version", version=f"meteofrance2openhasp version {__version__}")
    default_config_path = "config/configuration.yaml"
    default_secrets_path = "config/secrets.yaml"
    parser.add_argument(
        "-c",
        "--config",
        required=False,
        default=default_config_path,
        help=f"Path to the configuration file. Default: {default_config_path}",
    )
    parser.add_argument(
        "-s",
        "--secrets",
        required=False,
        default=default_secrets_path,
        help=f"Path to the secret file. Default: {default_secrets_path}",
    )

    args = parser.parse_args()

    try:

        # Some defaults to standard environment variables
        env_defaults = {
            "MQTT_PORT": "1883",
            "MQTT_USERNAME": "",
            "MQTT_PASSWORD": "",
        }

        # Default configuration values for logging
        config_defaults = {
            "logging.level": "INFO",
            "logging.console": True,
            "logging.file": None,
            "logging.format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        }

        # Load configuration files
        config = config_utils.ConfigLoader(args.config, args.secrets)
        config.load_secrets()
        config.load_config(env_defaults)

        print("Starting meteofrance2openhasp...")
        print(config.dumps())

        print(f"meteofrance2openhasp version: {__version__}")
        print(f"Running on Python version: {sys.version}")

        # Set up logging
        logging_file = config.get("logging.file", config_defaults["logging.file"])
        logging_console = bool(config.get("logging.console", config_defaults["logging.console"]))
        logging_level = config.get("logging.level", config_defaults["logging.level"])
        logging_format = config.get("logging.format", config_defaults["logging.format"])
        
        if not isinstance(logging_file, (str, type(None))):
            logging_file = str(logging_file)
        
        if not isinstance(logging_console, bool):
            logging_console = str(logging_console).lower() in ("true", "1", "yes")
        
        if not isinstance(logging_level, str):
            logging_level = ""
        
        if not isinstance(logging_format, str):
            logging_format = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

        # Convert logging level from string to integer
        if logging_level.upper() == "DEBUG":
            level = logging.DEBUG
        elif logging_level.upper() == "INFO":
            level = logging.INFO
        elif logging_level.upper() == "WARNING":
            level = logging.WARNING
        elif logging_level.upper() == "ERROR":
            level = logging.ERROR
        elif logging_level.upper() == "CRITICAL":
            level = logging.CRITICAL
        else:
            level = logging.INFO

        # logging_file may be empty or None
        logging.basicConfig(filename=logging_file, level=level, format=logging_format)

        if logging_file and logging_console:
            # Add a console handler manually, but only if logging to file is also enabled
            # if logging_file is not set, basicConfig already logs to console
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)  # Set logging level for the console
            console_handler.setFormatter(logging.Formatter(logging_format))  # Customize console format

            # Get the root logger and add the console handler
            logging.getLogger().addHandler(console_handler)

        Logger.info(f"Starting meteofrance2openhasp version {__version__}")
        Logger.info(f"Running on Python version: {sys.version}")

        # Log configuration
        Logger.info(f"Configuration:\n{config.dumps()}")

        # Start the bridge
        bridge = Bridge(config)
        bridge.run()

        Logger.info("meteofrance2openhasp stopped.")

        return 0

    except BaseException:  # pylint: disable=broad-except
        errorMessage = f"An error occured while running meteofrance2openhasp: {traceback.format_exc()}"
        Logger.error(errorMessage)
        print(errorMessage)
        raise


# ----------------------------------
if __name__ == "__main__":
    sys.exit(main())
