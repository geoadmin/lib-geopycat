import json
import logging
from geopycat import settings

def xpath_ns_url2code(path: str) -> str:
    """Replace the namespace url by the namespace acronym in the given xpath"""
    for key in settings.NS:
        path = path.replace("{" + settings.NS[key] + "}", f"{key}:")

    return path


def xpath_ns_code2url(path: str) -> str:
    """Replace the namespace url by the namespace acronym in the given xpath"""
    for key in settings.NS:
        path = path.replace(f"{key}:", "{" + settings.NS[key] + "}")

    return path


def setup_logger(name: str, level=logging.INFO) -> object:
    """Setup a logger for logging

    Args:
        name: required, the mane of the logger
        log_file: required, the path where to write the logger
        level: optional, the level to log

    Returns:
        Logger object
    """
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", '%d-%m-%y %H:%M:%S')

    logfile = f"{name}.log"

    handler = logging.FileHandler(logfile)

    handler.setFormatter(formatter)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


def okgreen(text):
    return f"\033[92m{text}\033[00m"


def warningred(text):
    return f"\033[91m{text}\033[00m"


def process_ok(response):
    """
    Process the response of the geocat API requests.

    Works for following requests :
     - /{portal}/api/0.1/records/batchediting
     - /{portal}/api/0.1/records/validate
     - /{portal}/api/0.1/records/{metadataUuid}/ownership

    Args:
        response:
            object, required, the response object of the API request

    Returns:
        boolean: True if the process was successful, False if not
    """
    if response.status_code == 201:
        r_json = json.loads(response.text)
        if len(r_json["errors"]) == 0 and r_json["numberOfRecordNotFound"] == 0 \
        and r_json["numberOfRecordsNotEditable"] == 0 and r_json["numberOfNullRecords"] == 0 \
        and r_json["numberOfRecordsWithErrors"] == 0 and r_json["numberOfRecordsProcessed"] == 1:
            return True
        else:
            return False
    else:
        return False
