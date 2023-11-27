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

load_dotenv()

class GeocatAPI():
    """
    Class to facilitate work with the geocat Restful API.
    Connect to geocat.ch with your username and password.
    Store request's session, XSRF Token, http authentication, proxies

    Parameters :
        env (str) (default = 'int'), can be set to 'prod'
        username: geocat username
        password: geocat password
        no_login: if set to true, use the package without being authenticated in geocat
    """

    def __init__(self, env: str = 'int', username: str = None, password: str = None,
                no_login: bool = False):

        if env not in settings.ENV:
            print(utils.warningred(f"No environment : {env}"))
            sys.exit()
        if env == 'prod':
            print(utils.warningred("WARNING : you choose the Production environment ! " \
                "Be careful, all changes will be live on geocat.ch"))
        self.env = settings.ENV[env]

        if no_login:
            self.__username = ""

        else:
            # Access credentials from env variable if not given in parameters
            if username is None:
                self.__username = os.getenv('GEOCAT_USERNAME')
            else:
                self.__username = username
            
            if password is None:
                self.__password = os.getenv('GEOCAT_PASSWORD')
            else:
                self.__password = password

            # If credentials not found in env variables, prompt for it
            if self.__username is None or self.__password is None:
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

        # Access database credentials from env variable if exists
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

    def __deep_search(self, body: dict) -> list:
        """
        Performs deep paginated search using ES search API request.
        Args: body, the request's body

        returns list of metadata index
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
                        uuids.append(hit)

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
                    not_in_groups: list = None, keywords: list = None, q: str = None) -> list:
        """
        Get a list of metadata uuid.
        The AND operator is used between the parameters, The OR operator is used within parameter (list).

        Parameters:
            with_harvested (bool): fetches harvested records as well
            valid_only (bool): fetches only valid records
            published_only (bool): fetches only published records
            with_templates (bool): fetches templates records as well
            in_groups (list): fetches records belonging to list of group ids. ids given as int
            not_in_groups (list): fetches records not belonging to list of group ids. ids given as int
            keywords (list): fetches records having at least one of the given keywords
            q (str): search unsing the lucene query synthax
        """

        body = copy.deepcopy(settings.SEARCH_UUID_API_BODY)

        query = utils.get_search_query(with_harvested=with_harvested, valid_only=valid_only,
                                published_only=published_only, with_templates=with_templates,
                                in_groups=in_groups, not_in_groups=not_in_groups, 
                                keywords=keywords, q=q)

        body["query"] = query

        indexes = self.__deep_search(body=body)

        return [i["_source"]["uuid"] for i in indexes]

    def get_ro_uuids(self, valid_only: bool = False, published_only: bool = False,
                        with_template: bool = False) -> dict:
        """
        Get UUID of all reusable objects (subtemplates).

        Paramters:
            valid_only (bool): fetches only valid records
            published_only (bool): fetches only published records
            with_templates (bool): fetches templates records as well        

        Returns:
            Dict with the 3 kinds of RO : {"contact": list,"extent": list,"format": list}
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

        Parameters:
            uuid: metadata's UUID
        """

        headers = {"accept": "application/x-gn-mef-2-zip"}

        params = {
            "withRelated": False
        }

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
            print(f"{utils.warningred('The following Metadata could not be exported in MEF : ') + uuid}")
            return None

        with ZipFile(io.BytesIO(response.content)) as zip:
            if f"{uuid}/metadata/metadata.xml" in zip.namelist():
                return zip.open(f"{uuid}/metadata/metadata.xml").read()
            else:
                print(f"{utils.warningred('The following Metadata could not be exported in MEF : ') + uuid}")

    def get_metadata_index(self, uuid: str) -> dict:
        """
        Fetches the elastic search index for a given metadata

        Parameters:
            uuid: metadata's UUID
        """

        body = copy.deepcopy(settings.GET_MD_INDEX_API_BODY)
        body["query"]["bool"]["must"][0]["multi_match"]["query"] = uuid

        headers = {"accept": "application/json", "Content-Type": "application/json"}

        body = json.dumps(body)

        response = self.session.post(url=self.env +
                    "/geonetwork/srv/api/search/records/_search", headers=headers, data=body)

        if response.status_code == 200:
            index = response.json()
            return index["hits"]["hits"][0]
        else:
            print(f"{utils.warningred('Could not retrieve index for md : ') + uuid}")

    def get_metadata_ownership(self, uuid: str) -> str:
        """
        Returns the metadata group owner ID and user owner ID

        Parameters:
            uuid: metadata's UUID

        Returns:
            Dict {"owner_ID": int, "group_ID": int}
        """

        index = self.get_metadata_index(uuid=uuid)

        ownership = {
            "owner_ID": int(index["ownerId"]),
            "group_ID": int(index["_source"]["groupOwner"])
        }

        return ownership

    def backup_metadata(self, uuids: list, backup_dir: str = None, with_related: bool = True):
        """
        Backup list of metadata as MEF zip file.

        Parameters:
            uuids (list): list of metadata uuids to export
            Backup_dir (str): path to directory where to save the metadata
            with_related (bool): export related metadata as well
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

        Parameters:
            uuids (list): list of metadata uuids to export
            Backup_dir (str): path to directory where to save the metadata
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

    def set_metadata_ownership(self, uuid: str, group_id: int, user_id: int) -> object:
        """
        Set metadata ownership

        Parameters:
            uuid (str): metadata's uuid
            group_id (int): new group ID
            user_id (int): new user ID
        """

        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        parameters = {
            "groupIdentifier": group_id,
            "userIdentifier": user_id,
        }

        res = self.session.put(url=self.env + f"/geonetwork/srv/api/records/{uuid}/ownership",
                                    headers=headers, params=parameters)
        
        return res

    def set_metadata_permission(self, uuid: str, permission: dict) -> object:
        """
        Set metadata permission

        Parameters:
            uuid (str): metadata's uuid
            permission (dict): permission in form of dict.
        """
     
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        body = json.dumps(permission)

        res = self.session.put(url=self.env + f"/geonetwork/srv/api/records/{uuid}/sharing",
                                        headers=headers, data=body)

        return res

    def edit_metadata(self, uuid: str, body: list, updateDateStamp: str ='true') -> object:
        """
        Edit a metadata by giving sets of xpath and xml.

        Args:
            uuid (str) : the uuid of the metadata to edit.
            body (list) : the edits you want to perform : [{"xpath": xpath, "value": xml}, ...]
            updateDateStamp (bool): 'true' or 'false', default = 'true'. If 'false',
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

    def validate_metadata(self, uuid: str) -> object:
        """
        Performs internal validation of a given metadata.
        Internal validation corresponds to the validator inside geocat editor.

        Parameters:
            uuid: metadata's UUID
        """

        params = {
            "currTab": "default",
            "starteditingsession": "yes"
        }

        res = self.session.get(url = self.env + f"/geonetwork/srv/api/records/{uuid}/editor", 
                         params=params)
        
        if res.status_code != 200:
            raise Exception("Could not start an edit session")
        
        headers = {"accept": "application/json"}

        res = self.session.put(url = self.env + f"/geonetwork/srv/api/records/{uuid}/validate/internal",
                               headers=headers)
        
        if res.status_code != 201:

            self.session.delete(url = self.env + f"/geonetwork/srv/api/records/{uuid}/editor")
            raise Exception("Could not perform validation")
        
        res = self.session.delete(url = self.env + f"/geonetwork/srv/api/records/{uuid}/editor")
        
        if res.status_code != 204:
            raise Exception("Could not close edit session")

    def search_and_replace(self, search: str, replace: str, escape_wildcard: bool = True):
        """
        Performs search and replace at the DB level.

        Parameters:
            search (str): value to search for
            replace (str): replace by this value
            escape_wildcard (bool): if True, "%" wildcard are escaped "\%"
        """

        if not self.check_admin():
            raise Exception("You must be admin to use this function")

        metadata_uuids = list()

        if escape_wildcard:
            search_sql = search.replace("%", "\%")
        else:
            search_sql = search

        try:
            connection = self.db_connect()
            with connection.cursor() as cursor:

                cursor.execute("SELECT uuid FROM public.metadata where (istemplate='n' OR istemplate='y')" \
                                f"AND data like '%{search_sql}%'")

                for row in cursor:
                    metadata_uuids.append(row[0])

        except (Exception, psycopg2.Error) as error:
            print("Error while fetching data from PostgreSQL", error)

        finally:
            if connection:
                connection.close()

        headers = {"accept": "application/json", "Content-Type": "application/json"}

        if len(metadata_uuids) == 0:
            print(utils.warningred(f"{search} not found in any metadata"))
            return

        for uuid in metadata_uuids:

            params = {
                "search": search,
                "replace": replace,
                "uuids": [uuid],
                "updateDateStamp": False
            }

            response = self.session.post(self.env + "/geonetwork/srv/api/processes/db/search-and-replace",
                                params=params, headers=headers)

            if utils.process_ok(response):
                print(utils.okgreen(f"Metadata {uuid} : {search} successfully replaced by {replace}"))
            else:
                print(utils.warningred(f"Metadata {uuid} : {search} unsuccessfully replaced by {replace}"))

    def delete_metadata(self, uuid: str) -> object:
        """
        Delete metadata

        Parameters:
            uuid: metadata's UUID

        Returns:
            The response of the request delete
        """

        headers = {"accept": "application/json", "Content-Type": "application/json"}
        params = {
            "withBackup": False
        }

        response = self.session.delete(self.env + f"/geonetwork/srv/api/records/{uuid}",
                            params=params, headers=headers)

        return response