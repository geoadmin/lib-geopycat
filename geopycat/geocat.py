import getpass
import os
import sys
import xml.etree.ElementTree as ET
import json
from datetime import datetime
from zipfile import ZipFile
import io
import copy
import requests
import urllib3
from dotenv import load_dotenv
import psycopg2
from geopycat import settings
from geopycat import utils


class GeocatAPI():
    """
    Class to facilitate work with the geocat Restful API.
    Connect to geocat.ch with your username and password.
    Store request's session, XSRF Token, http authentication, proxies

    Parameters :
        env -> str (default = 'int'), can be set to 'prod'
    """

    def __init__(self, env: str = 'int'):
        if env not in settings.ENV:
            print(utils.warningred(f"No environment : {env}"))
            sys.exit()
        if env == 'prod':
            print(utils.warningred("WARNING : you choose the Production environment ! " \
                "Be careful, all changes will be live on geocat.ch"))
        self.env = settings.ENV[env]
        self.__username = input("Geocat Username or press enter to continue without login: ")
        if self.__username != "":
            self.__password = getpass.getpass("Geocat Password : ")
        self.session = self.__get_token()

    def __get_token(self) -> object:
        """Function to get the token and test which proxy is needed"""
        session = requests.Session()
        session.cookies.clear()

        if self.__username != "":
            session.auth = (self.__username, self.__password)

        for proxies in settings.PROXY:
            try:
                session.post(url=self.env + '/geonetwork/srv/eng/info?type=me', proxies=proxies)
            except (requests.exceptions.ProxyError, OSError, urllib3.exceptions.MaxRetryError):
                pass
            else:
                break

        session.proxies.update(proxies)

        cookies = session.cookies.get_dict()
        token = cookies["XSRF-TOKEN"]
        session.headers.update({"X-XSRF-TOKEN": token})

        if self.__username != "":

            response = session.post(url=self.env + '/geonetwork/srv/eng/info?type=me')

            if response.status_code != 200:
                print(utils.warningred('Username or password not valid !'))
                sys.exit()

            xmlroot = ET.fromstring(response.text)
            if xmlroot.find("me").attrib["authenticated"] != "true":
                print(utils.warningred('Username or password not valid !'))
                sys.exit()

        return session

    def db_connect(self) -> object:
        """Connect to geocat DB and returns a psycopg2 connection object"""

        # Access database credentials from .env variable if exist
        load_dotenv()

        db_username = os.getenv('DB_USERNAME')
        db_password = os.getenv('DB_PASSWORD')

        if db_username is None or db_password is None:
            db_username = getpass.getpass("Geocat Database Username : ")
            db_password = getpass.getpass("Geocat Database Password : ")

        _env = [k for k, v in settings.ENV.items() if v == self.env][0]

        connection = psycopg2.connect(
                host="database-lb.geocat.swisstopo.cloud",
                database=f"geocat-{_env}",
                user=db_username,
                password=db_password)

        return connection

    def __search_uuid(self, body: dict) -> list:
        """
        Performs deep paginated search using ES search API request.
        Args: body, the request's body
        """
        uuids = []

        proxies = self.session.proxies
        unauth_session = requests.Session()
        unauth_session.proxies = proxies

        headers = {"accept": "application/json", "Content-Type": "application/json"}
        size = 2000

        published_only = False
        if "query_string" in body["query"]["bool"]["must"][0]:
            query_string = body["query"]["bool"]["must"][0]["query_string"]["query"]
            if "(isPublishedToAll:\"true\")" in query_string:
                published_only = True

        body["size"] = size
        body = json.dumps(body)

        iterations = ["unauth"]
        if not published_only and self.session.auth is not None:
            iterations.append("auth")

        for i in iterations:
            while True:

                if i == "unauth":
                    response = unauth_session.post(url=self.env +
                        "/geonetwork/srv/api/search/records/_search", headers=headers, data=body)
                elif i == "auth":
                    response = self.session.post(url=self.env +
                        "/geonetwork/srv/api/search/records/_search", headers=headers, data=body)

                if response.status_code == 200:
                    for hit in response.json()["hits"]["hits"]:
                        uuids.append(hit["_source"]["uuid"])

                    if len(response.json()["hits"]["hits"]) < size:
                        break

                    body = json.loads(body)
                    body["search_after"] = response.json()["hits"]["hits"][-1]["sort"]
                    body = json.dumps(body)

                else:
                    break

            body = json.loads(body)
            if "search_after" in body:
                del body["search_after"]

            if "query_string" in locals():
                query_string = query_string + "AND (isPublishedToAll:\"false\")"
                body["query"]["bool"]["must"][0] = {"query_string": {"query": query_string,
                    "default_operator": "AND"}}
            else:
                body["query"]["bool"]["must"].insert(0, {"query_string":
                {"query": "(isPublishedToAll:\"false\")", "default_operator": "AND"}})

            body = json.dumps(body)

        return uuids

    def check_admin(self) -> bool:
        """
        Check if the user is a geocat admin. Returns True or False
        """
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        response = self.session.get(url=self.env + '/geonetwork/srv/api/me', headers=headers)

        if response.status_code == 200:
            if json.loads(response.text)["profile"] == "Administrator":
                return True
        return False

    def get_uuids(self, with_harvested: bool = True, valid_only: bool = False, published_only:
                    bool = False, with_templates: bool = False, in_groups: list = None,
                    not_in_groups: list = None, keywords: list = None) -> list:
        """
        Get a list of metadata uuid.
        You can specify if you want or not : harvested, valid, published records and templates.
        """

        body = copy.deepcopy(settings.SEARCH_UUID_API_BODY)

        if with_templates:
            body["query"]["bool"]["must"].append({"terms": {"isTemplate": ["y", "n"]}})
        else:
            body["query"]["bool"]["must"].append({"terms": {"isTemplate": ["n"]}})

        query_string = str()

        if not with_harvested:
            query_string = query_string + "(isHarvested:\"false\") AND"

        if valid_only:
            query_string = query_string + "(valid:\"1\") AND"

        if published_only:
            query_string = query_string + "(isPublishedToAll:\"true\") AND"

        if in_groups is not None:
            toadd = " OR ".join([f"groupOwner:\"{i}\"" for i in in_groups])
            query_string = query_string + f"({toadd}) AND"

        if not_in_groups is not None:
            toadd = " OR ".join([f"-groupOwner:\"{i}\"" for i in not_in_groups])
            query_string = query_string + f"({toadd}) AND"

        if keywords is not None:
            query_kw = " AND ".join([f"tag.default:\"{i}\" OR tag.langfre:\"{i}\"" \
                f"OR tag.langger:\"{i}\" OR tag.langita:\"{i}\" OR tag.langeng:\"{i}\""
                for i in keywords])

            query_string = query_string + f"({query_kw}) AND"

        if len(query_string) > 0:
            query_string = query_string[:-4]
            body["query"]["bool"]["must"].insert(0, {"query_string": {"query": query_string,
                    "default_operator": "AND"}})

        return self.__search_uuid(body=body)

    def get_ro_uuids(self, valid_only: bool = False, published_only: bool = False,
                        with_template: bool = False) -> dict:
        """
        Get UUID of all reusable objects (subtemplates).
        You can specify if you want only the valid and/or published records.
        The subtemplates template are not returned.
        Returns a dictionnary with the 3 kinds of RO : {"contact": ,"extent": ,"format": }
        """

        if not self.check_admin():
            print(utils.warningred("You need to be admin to use this method"))
            return

        uuids_contact = list()
        uuids_extent = list()
        uuids_format = list()

        if with_template:
            template = " or istemplate = 't'"
        else:
            template = str()

        try:
            connection = self.db_connect()

            with connection.cursor() as cursor:

                if valid_only and not published_only:
                    cursor.execute(f"SELECT UUID,data FROM public.metadata WHERE (istemplate='s' {template}) " \
                    "AND id IN (SELECT metadataid FROM public.validation WHERE status=1 AND required=true)")

                elif published_only and not valid_only:
                    cursor.execute(f"SELECT UUID,data FROM public.metadata WHERE (istemplate='s' {template}) " \
                    "AND id IN (SELECT metadataid FROM public.operationallowed WHERE groupid=1 AND operationid=0)")
                elif valid_only and published_only:
                    cursor.execute(f"SELECT UUID,data FROM public.metadata WHERE (istemplate='s' {template}) " \
                    "AND id IN (SELECT metadataid FROM public.validation WHERE status=1 AND required=true) " \
                    "AND id IN (SELECT metadataid FROM public.operationallowed WHERE groupid=1 AND operationid=0)")
                else:
                    cursor.execute(f"SELECT UUID,data FROM public.metadata WHERE (istemplate='s' {template})")

                for row in cursor:
                    if row[1].startswith("<che:CHE_CI_ResponsibleParty"):
                        uuids_contact.append(row[0])
                    elif row[1].startswith("<gmd:EX_Extent"):
                        uuids_extent.append(row[0])
                    elif row[1].startswith("<gmd:MD_Format"):
                        uuids_format.append(row[0])

        except (Exception, psycopg2.Error) as error:
            print("Error while fetching data from PostgreSQL", error)

        else:
            return {
                "contact": uuids_contact,
                "extent": uuids_extent,
                "format": uuids_format,
            }

        finally:
            if connection:
                connection.close()

    def get_metadata_from_mef(self, uuid: str) -> bytes:
        """
        Get metadata XML from MEF (metadata exchange format).
        """

        headers = {"accept": "application/x-gn-mef-2-zip"}

        proxy_error = True
        while proxy_error:
            try:
                response = self.session.get(url=self.env + f"/geonetwork/srv/api/records/{uuid}/formatters/zip",
                                            headers=headers)
            except requests.exceptions.ProxyError:
                print("Proxy Error Occured, retry connection")
            else:
                proxy_error = False

        if response.status_code != 200:
            print(f"{utils.warningred('The following Metadata could not be exported in MEF : ') + uuid}")
            return None

        with ZipFile(io.BytesIO(response.content)) as zip:
            if f"{uuid}/metadata/metadata.xml" in zip.namelist():
                return zip.open(f"{uuid}/metadata/metadata.xml").read()
            else:
                print(f"{utils.warningred('The following Metadata could not be exported in MEF : ') + uuid}")

    def get_metadata_languages(self, metadata: bytes) -> dict:
        """
        Fetches all languages of the metadata (given as bytes string).
        Returns main and additonal metadata languages in form of a dictionnary.
        """

        languages = {
            "mainLanguage": None,
            "languages": list(),
        }

        xml_root = ET.fromstring(metadata)

        languages["mainLanguage"] = xml_root.find("./gmd:language/gmd:LanguageCode",
                        namespaces=settings.NS).attrib["codeListValue"]

        for lang in xml_root.findall("./gmd:locale//gmd:LanguageCode", namespaces=settings.NS):
                languages["languages"].append(lang.attrib["codeListValue"])

        return languages

    def get_metadata_groupowner_id(self, uuid: str) -> str:
        """
        Returns the metadata group owner ID
        """

        headers = {"accept": "application/json"}

        proxy_error = True
        while proxy_error:
            try:
                response = self.session.get(url=self.env + f"/geonetwork/srv/api/records/{uuid}/sharing",
                                            headers=headers)
            except requests.exceptions.ProxyError:
                print("Proxy Error Occured, retry connection")
            else:
                proxy_error = False
        
        if response.status_code == 200:
            return response.json()["groupOwner"]
        else:
            print(f"{utils.warningred('Could not retrieve group owner ID for md : ') + uuid}")

    def backup_metadata(self, uuids: list, backup_dir: str = None, with_related: bool = True):
        """
        Backup list of metadata as MEF zip file.
        """
        if backup_dir is None:
            backup_dir = f"MetadataBackup_{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        if not os.path.isdir(backup_dir):
            os.mkdir(backup_dir)

        headers = {"accept": "application/x-gn-mef-2-zip"}

        print("Backup metadata : ", end="\r")

        params = {
            "withRelated": with_related
        }

        count = 1
        for uuid in uuids:

            proxy_error = True
            while proxy_error:
                try:
                    response = self.session.get(url=self.env + f"/geonetwork/srv/api/records/{uuid}/formatters/zip",
                                                headers=headers, params=params)
                except requests.exceptions.ProxyError:
                    print("Proxy Error Occured, retry connection")
                else:
                    proxy_error = False

            if response.status_code != 200:
                print(f"{utils.warningred('The following Metadata could not be backup : ') + uuid}")
                continue

            with open(os.path.join(backup_dir, f"{uuid}.zip"), "wb") as output:
                output.write(response.content)

            print(f"Backup metadata : {round((count / len(uuids)) * 100, 1)}%", end="\r")

            count += 1

        print(f"Backup metadata : {utils.okgreen('Done')}")

    def backup_metadata_xml(self, uuids: list, backup_dir: str = None):
        """
        Backup list of metadata as XML file.
        """
        if backup_dir is None:
            backup_dir = f"MetadataBackup_{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        if not os.path.isdir(backup_dir):
            os.mkdir(backup_dir)

        headers = {"accept": "application/xml", "Content-Type": "application/xml"}

        print("Backup metadata : ", end="\r")

        params = {
            "increasePopularity": False,
        }

        count = 1
        for uuid in uuids:

            proxy_error = True
            while proxy_error:
                try:
                    response = self.session.get(url=self.env + f"/geonetwork/srv/api/records/{uuid}/formatters/xml",
                                                headers=headers, params=params)
                except requests.exceptions.ProxyError:
                    print("Proxy Error Occured, retry connection")
                else:
                    proxy_error = False

            if response.status_code != 200:
                print(f"{utils.warningred('The following Metadata could not be backup : ') + uuid}")
                continue

            with open(os.path.join(backup_dir, f"{uuid}.xml"), "wb") as output:
                output.write(response.content)

            print(f"Backup metadata : {round((count / len(uuids)) * 100, 1)}%", end="\r")

            count += 1

        print(f"Backup metadata : {utils.okgreen('Done')}")    

    def edit_metadata(self, uuid: str, body: list, updateDateStamp: str ='true') -> object:
        """
        Edit a metadata by giving sets of xpath and xml.

        Args:
            uuid : the uuid of the metadata to edit.
            body : the edits you want to perform : [{"xpath": xpath, "value": xml}, ...]
            updateDateStamp : 'true' or 'false', default = 'true'. If 'false',
            the update date and time of the metadata is not updated.

        Returns:
            The response of the batchediting request
        """
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        params = {
            "uuids": [uuid],
            "updateDateStamp": updateDateStamp,
        }

        body = json.dumps(body)

        response = self.session.put(self.env + "/geonetwork/srv/api/records/batchediting",
                                    params=params, headers=headers, data=body)

        return response

    def delete_metadata(self, uuid: str):
        """
        Delete metadata by giving its uuid. Returns the response of delete request
        """

        headers = {"accept": "application/json", "Content-Type": "application/json"}
        params = {
            "withBackup": False
        }

        response = self.session.delete(self.env + f"/geonetwork/srv/api/records/{uuid}",
                            params=params, headers=headers)

        return response
