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

    def es_deep_search(self, body: dict) -> list:
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

    def get_users(self, admin: bool = True, useradmin: bool = True, reviewer: bool = True,
                editor: bool = True, registered_user: bool = True, inactive: bool = True,
                owner_only : bool = False, harvester_only : bool = False) -> list:
        """
        Get list of geocat users

        Args:
            admin: include Administrator profile
            useradmin: include UserAdmin profile
            reviewer: include Reviewer profile
            editor: include Editor profile
            registered_user: include RegisteredUser profile
            inactive: include disabled users
            owner_only: get only users that have at least one record
        """

        headers = {"accept": "application/json", "Content-Type": "application/json"}

        users = []

        if owner_only:

            res = self.session.get(url=f"{self.env}/geonetwork/srv/api/users/owners",
                                    headers=headers)
            res.raise_for_status()

            for owner in res.json():
                res = self.session.get(url=f"{self.env}/geonetwork/srv/api/users/{owner['id']}",
                                    headers=headers)

                if res.status_code == 200:
                    users.append(res.json())
                else:
                    print(f"{utils.warningred('No information retrieved from user : ') + owner['id']}")

        else:

            res = self.session.get(url=f"{self.env}/geonetwork/srv/api/users",
                                    headers=headers)
            res.raise_for_status()

            users = res.json()

        if not admin:
            users = [user for user in users if user['profile'] != "Administrator" ]

        if not useradmin:
            users = [user for user in users if user['profile'] != "UserAdmin" ]

        if not reviewer:
            users = [user for user in users if user['profile'] != "Reviewer" ]

        if not editor:
            users = [user for user in users if user['profile'] != "Editor" ]

        if not registered_user:
            users = [user for user in users if user['profile'] != "RegisteredUser" ]

        if not inactive:
            users = [user for user in users if user['enabled'] is True ]

        if harvester_only:

            body = copy.deepcopy(settings.SEARCH_UUID_API_BODY)

            query = utils.get_search_query(q="isHarvested:true")
            body["query"] = query

            body["aggregations"] = {
                "owner": {
                    "terms": {
                        "field": "owner",
                        "size": 100
                    },
                    "meta": {
                        "field": "owner"
                    }
                }
            }

            body = json.dumps(body)

            r = self.session.post(url=f"{self.env}/geonetwork/srv/api/search/records/_search",
                                    headers=headers, data=body)

            harvester = [int(i["key"]) for i in r.json()["aggregations"]["owner"]["buckets"]]
            users = [user for user in users if user['id'] in harvester]

        return users

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
            q (str): search using the lucene query synthax
        """

        body = copy.deepcopy(settings.SEARCH_UUID_API_BODY)

        query = utils.get_search_query(with_harvested=with_harvested, valid_only=valid_only,
                                published_only=published_only, with_templates=with_templates,
                                in_groups=in_groups, not_in_groups=not_in_groups, 
                                keywords=keywords, q=q)

        body["query"] = query

        indexes = self.es_deep_search(body=body)

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

        subtemplate_types = {
            "contact": "che:CHE_CI_ResponsibleParty",
            "extent" : "gmd:EX_Extent",
            "format": "gmd:MD_Format"
        }

        body = copy.deepcopy(settings.SEARCH_UUID_API_BODY)

        body["query"] = {
            "bool": {
                    "must": []
                }
            }
        
        query_string = str()

        if valid_only:
            query_string = query_string + "(valid:\"1\") AND"
        
        if published_only:
            query_string = query_string + "(isPublishedToAll:\"true\") AND"
        
        if with_template:
            body["query"]["bool"]["must"].append({"terms": {"isTemplate": ["s", "t"]}})
        else:
            body["query"]["bool"]["must"].append({"terms": {"isTemplate": ["s"]}})

        if len(query_string) > 0:
            query_string = query_string[:-4]
            body["query"]["bool"]["must"].insert(
                0, 
                {"query_string": {"query": query_string,
                "default_operator": "AND"}}
            )

        output = {}

        for type in subtemplate_types:
            
            body["query"]["bool"]["must"].append(
                {
                    "terms": {
                        "root": [
                            subtemplate_types[type]
                        ]
                    }
                }
            )
        
            indexes = self.es_deep_search(body=body)
            output[type] = [i["_source"]["uuid"] for i in indexes]

            body["query"]["bool"]["must"].pop()
       
        return output

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

            uuid = uuid.replace(":", "_").replace("/", "_").replace("\\", "_").replace("'", "_").replace('"', "_")

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

            uuid = uuid.replace(":", "_").replace("/", "_").replace("\\", "_").replace("'", "_").replace('"', "_")

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

    def validate_external_metadata(self, uuid: str) -> None:
        """
        Performs external validation of a given metadata.
        External validation corresponds to validator outside the editor.
        It does not save the metadat first, hence does not perform update-info.xsl

        Parameters:
            uuid: metadata's UUID
        """

        headers = {
        "accept": "application/json", 
        "Content-Type": "application/json"
        }

        params = {
            "uuids": [uuid]
        }

        res = self.session.put(url=f"{self.env}/geonetwork/srv/api/records/validate",
                            params=params, headers=headers)

        res.raise_for_status()

        res = res.json()

        if res["numberOfRecords"] != 1 or res["numberOfRecordNotFound"] != 0 \
            or res["numberOfNullRecords"] != 0 or res["numberOfRecordsProcessed"] != 1:

            raise Exception("validation process failed")

    def reset_validation_status(self, uuid: str) -> None:
        """
        Reset validation status of given metadata.

        Parameters:
            uuid: metadata's UUID
        """

        headers = {
            "accept": "application/json", 
            "Content-Type": "application/json"
        }

        params = {
            "uuids": [uuid]
        }

        res = self.session.delete(url=f"{self.env}/geonetwork/srv/api/records/validate",
                            params=params, headers=headers)

        res.raise_for_status()

        if not utils.process_ok(res):
            raise Exception("resetting validation status failed")

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

    def search_db(self, search: str, escape_wildcard: bool = True) -> list:
        """
        Performs search at the DB level. Returns list of metadata UUID where search
        input was found.

        Parameters:
            search (str): value to search for
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
        
        return metadata_uuids

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