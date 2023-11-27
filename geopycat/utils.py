import json
import logging
import xml.etree.ElementTree as ET
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


def get_log_config(logfile: str = None, level: str = "INFO", log2stdout: bool = True):
    """
    Generates a config dict for logging module

    Parameters:
        logfile: If log file should be written, specify the path
        level: logging level
        log2stdout: If true, print log to std out as well

    Returns:
        A dict for the method logging.config.dictConfig()
    """

    config = {
        "version":1,
        "root":{
            "handlers" : [],
            "level": level
        },
        "handlers":{},
        "formatters":{
            "std_out": {
                "format": "%(asctime)s - %(levelname)s - %(message)s",
                "datefmt":"%Y-%m-%d %H:%M:%S"
            }
        },
    }

    if log2stdout:

        config["root"]["handlers"].append("console")

        config["handlers"]["console"] = {
                "formatter": "std_out",
                "class": "logging.StreamHandler",
                "level": level
        }
    
    if logfile is not None:

        config["root"]["handlers"].append("file")

        config["handlers"]["file"] = {
                "formatter": "std_out",
                "class": "logging.FileHandler",
                "level": level,
                "filename": logfile
        }
    
    return config


def okgreen(text):
    return f"\033[92m{text}\033[00m"


def warningred(text):
    return f"\033[91m{text}\033[00m"


def process_ok(response):
    """
    Process the response of the geocat API requests.

    Works for following requests :
     - /{portal}/api/records/batchediting
     - /{portal}/api/records/validate
     - /{portal}/api/records/{metadataUuid}/ownership

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


def get_metadata_languages(metadata: bytes) -> dict:
    """
    Fetches all languages of the metadata (given as bytes string).
    Returns main and additonal metadata languages in form of a dictionnary.
    """

    languages = {
        "language": None,
        "locales": list(),
    }

    xml_root = ET.fromstring(metadata)

    languages["language"] = xml_root.find("./gmd:language/gmd:LanguageCode",
                    namespaces=settings.NS).attrib["codeListValue"]

    for lang in xml_root.findall("./gmd:locale//gmd:LanguageCode", namespaces=settings.NS):
            if lang.attrib["codeListValue"] != languages["language"] and \
                lang.attrib["codeListValue"] not in languages["locales"]:

                languages["locales"].append(lang.attrib["codeListValue"])

    return languages


def xmlify(string: str) -> str:
    """Replace XML special characters"""

    string = string.replace("&", "&amp;")
    string = string.replace(">", "&gt;")
    string = string.replace("<", "&lt;")
    string = string.replace("'", "&apos;")
    string = string.replace('"', "&quot;")

    return string


def get_search_query(**kwargs) -> dict:
    """
    Returns the query syntax for ES search API.
    
    This query is in a form of a python dict and is
    to be inserted in a ES API request's body.
    """

    query = {
        "bool": {
            "must": []
        }
    }

    if kwargs["with_templates"]:
        query["bool"]["must"].append({"terms": {"isTemplate": ["y", "n"]}})
    else:
        query["bool"]["must"].append({"terms": {"isTemplate": ["n"]}})

    query_string = str()

    if not kwargs["with_harvested"]:
        query_string = query_string + "(isHarvested:\"false\") AND"

    if kwargs["valid_only"]:
        query_string = query_string + "(valid:\"1\") AND"

    if kwargs["published_only"]:
        query_string = query_string + "(isPublishedToAll:\"true\") AND"

    if kwargs["in_groups"] is not None:
        toadd = " OR ".join([f"groupOwner:\"{i}\"" for i in kwargs["in_groups"]])
        query_string = query_string + f"({toadd}) AND"

    if kwargs["not_in_groups"] is not None:
        toadd = " OR ".join([f"-groupOwner:\"{i}\"" for i in kwargs["not_in_groups"]])
        query_string = query_string + f"({toadd}) AND"

    if kwargs["keywords"] is not None:
        query_kw = " OR ".join([f"tag.default:\"{i}\" OR tag.langfre:\"{i}\"" \
            f"OR tag.langger:\"{i}\" OR tag.langita:\"{i}\" OR tag.langeng:\"{i}\""
            for i in kwargs["keywords"]])

        query_string = query_string + f"({query_kw}) AND"

    if kwargs["q"] is not None:
        query_string = query_string + f"({kwargs['q']}) AND"

    if len(query_string) > 0:
        query_string = query_string[:-4]
        query["bool"]["must"].insert(0, {"query_string": {"query": query_string,
                "default_operator": "AND"}})
    
    return query
