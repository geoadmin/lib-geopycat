import os
import json
import psycopg2
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime
from geopycat import geocat
from geopycat import utils


class GeocatBackup(geocat):
    """
    Generate a backup of geocat.
    """

    def __init__(self, backup_dir: str = None, catalogue: bool = True, users: bool = True,
                 groups: bool = True, subtemplates: bool = True, **kwargs):

        super().__init__(**kwargs)

        if not self.check_admin():
            print(utils.warningred("You must be logged-in as Admin to generate a backup !"))
            return

        print("Backup started...")

        if backup_dir is None:
            self.backup_dir = f"GeocatBackup_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        else:
            self.backup_dir = backup_dir

        if not os.path.isdir(self.backup_dir):
            os.mkdir(self.backup_dir)

        if catalogue:
            self.__backup_metadata()
        if users:
            self.__backup_users()
        if groups:
            self.__backup_groups()
        if subtemplates:
            self.__backup_subtemplates()
        
        self.__backup_thesaurus()
        self.__backup_unpublish_report()
        self.__backup_harvesting_settings()
        self.__write_logfile()

        print(utils.okgreen("Backup Done"))

    def __backup_metadata(self):

        if not os.path.isdir(os.path.join(self.backup_dir, "metadata")):
            os.mkdir(os.path.join(self.backup_dir, "metadata"))

        uuids = self.get_uuids(with_harvested=False, with_templates=True)
        self.backup_metadata(uuids=uuids, backup_dir=os.path.join(self.backup_dir, "metadata"), 
                                with_related=False)

    def __backup_users(self):
        """
        Backup all users in a single json file.
        Backup a json file per user with group information.
        Backup a csv file with list of users.
        """
        print("Backup users : ", end="\r")
        output_dir = os.path.join(self.backup_dir, "users")

        # If output dir doesn't already exist, creates it.
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        # Save the users list as json file
        headers = {"accept": "application/json", "Content-Type": "application/json"}

        response = self.session.get(url=self.env + "/geonetwork/srv/api/users", headers=headers)

        with open(os.path.join(output_dir, "users.json"), 'w') as file:
            json.dump(response.json(), file)

        # Collect group information for each user
        if not os.path.exists(os.path.join(output_dir, "users_with_groups")):
            os.mkdir(os.path.join(output_dir, "users_with_groups"))

        columns = ["id", "username", "profile", "enabled", "group_name", "groupID_UserAdmin", 
                    "groupID_Editor", "groupID_Reviewer", "groupID_RegisteredUser"]

        df = pd.DataFrame(columns=columns)
        total = len(json.loads(response.text))
        count = 0

        for user in json.loads(response.text):
            response_usergroup = self.session.get(
                url=self.env + f"/geonetwork/srv/api/users/{user['id']}/groups", headers=headers)

            # Save a json file per user with groups information
            with open(os.path.join(output_dir, f"users_with_groups/{user['id']}.json"), 'w') as file:
                json.dump(response_usergroup.json(), file)

            # Create a DataFrame with information about the users, one row per user
            group_names = []
            useradmin_id = []
            editor_id = []
            reviewer_id = []
            registereduser_id = []

            for user_group in json.loads(response_usergroup.text):
                if user_group["group"]["name"] not in group_names:
                    group_names.append(user_group["group"]["name"])
                if user_group["id"]["profile"] == "UserAdmin" and user_group["id"]["groupId"] not in useradmin_id:
                    useradmin_id.append(user_group["id"]["groupId"])
                if user_group["id"]["profile"] == "Editor" and user_group["id"]["groupId"] not in editor_id:
                    editor_id.append(user_group["id"]["groupId"])
                if user_group["id"]["profile"] == "Reviewer" and user_group["id"]["groupId"] not in reviewer_id:
                    reviewer_id.append(user_group["id"]["groupId"])
                if user_group["id"]["profile"] == "RegisteredUser" and user_group["id"][
                    "groupId"] not in registereduser_id:
                    registereduser_id.append(user_group["id"]["groupId"])

            group_names = "/".join(group_names)
            useradmin_id = "/".join([str(i) for i in useradmin_id])
            editor_id = "/".join([str(i) for i in editor_id])
            reviewer_id = "/".join([str(i) for i in reviewer_id])
            registereduser_id = "/".join([str(i) for i in registereduser_id])

            if user["profile"] == "Administrator":
                group_names, useradmin_id, editor_id, reviewer_id, registereduser_id = "all", "all", "all", "all", "all"

            row = {
                "id": user["id"],
                "username": user["username"],
                "profile": user["profile"],
                "enabled": user["enabled"],
                "group_name": group_names,
                "groupID_UserAdmin": useradmin_id,
                "groupID_Editor": editor_id,
                "groupID_Reviewer": reviewer_id,
                "groupID_RegisteredUser": registereduser_id,
            }

            df = df.append(row, ignore_index=True)

            count += 1
            print(f"Backup users : {round((count / total) * 100)}%", end="\r")

        df.to_csv(os.path.join(output_dir, "users_with_groups.csv"), index=False)
        print(f"Backup users : {utils.okgreen('Done')}")

    def __backup_groups(self):
        """
        Backup all groups in a single json file
        Backup a json file per group with list of users
        Backup a csv with list of groups
        """
        print("Backup groups : ", end="\r")
        output_dir = os.path.join(self.backup_dir, "groups")

        # If output dir doesn't already exist, creates it.
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        # Save the groups list as json file
        headers = {"accept": "application/json", "Content-Type": "application/json"}

        params = {"withReservedGroup": True}

        response = self.session.get(url=self.env + "/geonetwork/srv/api/groups", params=params,
                                        headers=headers)

        with open(os.path.join(output_dir, "groups.json"), 'w') as file:
            json.dump(response.json(), file)

        # Save one json per group with list of users of this group and logo of the group
        # If output dir doesn't already exist, creates it.
        if not os.path.exists(os.path.join(output_dir, "groups_users")):
            os.mkdir(os.path.join(output_dir, "groups_users"))

        if not os.path.exists(os.path.join(output_dir, "groups_logo")):
            os.mkdir(os.path.join(output_dir, "groups_logo"))

        # Create csv file with the following attributes
        df = pd.DataFrame(columns=["id", "group_name", "users_number"])

        total = len(json.loads(response.text))
        count = 0

        for group in json.loads(response.text):
            response_group_users = self.session.get(url=self.env + 
                f"/geonetwork/srv/api/groups/{group['id']}/users", headers=headers)

            with open(os.path.join(output_dir, f"groups_users/{group['id']}.json"), 'w') as file:
                json.dump(response_group_users.json(), file)

            # Save logo only if exists
            if group["logo"] != "" and group["logo"] is not None:
                logo_extension = group["logo"].split(".")[-1]

                response_group_logo = self.session.get(url=self.env + 
                    f"/geonetwork/srv/api/groups/{group['id']}/logo", headers=headers)

                with open(os.path.join(output_dir, f"groups_logo/{group['id']}.{logo_extension}"), 
                    'wb') as file:
                    file.write(response_group_logo.content)

            row = {"id": str(group['id']), "group_name": group['name'],
                   "users_number": str(len(json.loads(response_group_users.text)))}
            df = df.append(row, ignore_index=True)

            count += 1
            print(f"Backup groups : {round((count / total) * 100)}%", end="\r")

        df.to_csv(os.path.join(output_dir, "groups.csv"), index=False)
        print(f"Backup groups : {utils.okgreen('Done')}")

    def __backup_subtemplates(self):
        """
        Backup all subtemplates in XML found in the DB.
        """
        print("Backup subtemplates")

        output_dir_contacts = os.path.join(self.backup_dir, "Subtemplates_contacts")
        output_dir_extents = os.path.join(self.backup_dir, "Subtemplates_extents")
        output_dir_formats = os.path.join(self.backup_dir, "Subtemplates_formats")

        # If output dir doesn't already exist, creates it.
        if not os.path.exists(output_dir_contacts):
            os.mkdir(output_dir_contacts)
        if not os.path.exists(output_dir_extents):
            os.mkdir(output_dir_extents)
        if not os.path.exists(output_dir_formats):
            os.mkdir(output_dir_formats)

        subtpl_uuids = self.get_ro_uuids(with_template=True)

        def export_subtemplate(uuid):
            headers = {"accept": "application/xml", "Content-Type": "application/xml"}

            response = self.session.get(
            url=self.env + f"/geonetwork/srv/api/records/{uuid}/formatters/xml", headers=headers)

            if response.status_code != 200:
                print(f"{utils.warningred('The following subtemplate could not be backup : ') + uuid}")
                return

            xmlroot = ET.fromstring(response.text)

            if xmlroot.tag == "apiError":
                print(f"{utils.warningred('The following subtemplate could not be backup : ') + uuid}")
                return

            return response.content

        # Backup contacts
        count = 0
        print("Backup contacts : ", end="\r")
        for uuid in subtpl_uuids["contact"]:

            subtpl = export_subtemplate(uuid=uuid)

            if subtpl is not None:
                with open(os.path.join(output_dir_contacts, f"{uuid}.xml"), 'wb') as file:
                    file.write(subtpl)

            count += 1
            print(f"Backup contacts : {round((count / len(subtpl_uuids['contact'])) * 100)}%", end="\r")
        print(f"Backup contacts : {utils.okgreen('Done')}")

        # Backup extents
        count = 0
        print("Backup extents : ", end="\r")
        for uuid in subtpl_uuids["extent"]:

            subtpl = export_subtemplate(uuid=uuid)

            if subtpl is not None:
                with open(os.path.join(output_dir_extents, f"{uuid}.xml"), 'wb') as file:
                    file.write(subtpl)

            count += 1
            print(f"Backup extents : {round((count / len(subtpl_uuids['extent'])) * 100)}%", end="\r")
        print(f"Backup extents : {utils.okgreen('Done')}")

        # Backup formats
        count = 0
        print("Backup formats : ", end="\r")
        for uuid in subtpl_uuids["format"]:

            subtpl = export_subtemplate(uuid=uuid)

            if subtpl is not None:
                with open(os.path.join(output_dir_formats, f"{uuid}.xml"), 'wb') as file:
                    file.write(subtpl)

            count += 1
            print(f"Backup formats : {round((count / len(subtpl_uuids['format'])) * 100)}%", end="\r")
        print(f"Backup formats : {utils.okgreen('Done')}")

        print(f"Backup subtemplates : {utils.okgreen('Done')}")

    def __backup_thesaurus(self):
        """
        Backup custom thesaurus in rdf format (xml) : geocat.ch
        """
        print("Backup thesaurus...", end="\r")
        thesaurus_ref = ["local.theme.geocat.ch"]

        headers = {"accept": "text/xml", "Content-Type": "text/xml"}

        for thesaurus_name in thesaurus_ref:
            response = self.session.get(
                url=self.env + f"/geonetwork/srv/api/registries/vocabularies/{thesaurus_name}",
                headers=headers)

            with open(os.path.join(self.backup_dir, f"{thesaurus_name}.rdf"), 'wb') as file:
                file.write(response.content)

        print(f"Backup thesaurus {utils.okgreen('Done')}")

    def __backup_unpublish_report(self):
        """
        Backup the de-publication report in csv
        """
        response = self.session.get(url=self.env + "/geonetwork/srv/fre/unpublish.report.csv")

        with open(os.path.join(self.backup_dir, "unpublish_report.csv"), 'wb') as file:
            file.write(response.content)

    def __write_logfile(self):
        """
        Write a logfile. Runs everytime the class is initiated
        """
        if os.path.isfile(os.path.join(self.backup_dir, "backup.log")):
            os.remove(os.path.join(self.backup_dir, "backup.log"))

        # Number of metadata
        md_folder = os.path.join(self.backup_dir, "metadata")
        with open(os.path.join(self.backup_dir, "backup.log"), "w") as logfile:
            logfile.write(f"Metadatas backup : {len(os.listdir(md_folder))}\n")

        # Number of users
        if os.path.isfile(self.backup_dir + "/users/users.json"):
            with open(self.backup_dir + "/users/users.json") as users:
                with open(os.path.join(self.backup_dir, "backup.log"), "a") as logfile:
                    logfile.write(f"Users backup : {len(json.load(users))}\n")

        # Number of groups
        if os.path.isfile(self.backup_dir + "/groups/groups.json"):
            with open(self.backup_dir + "/groups/groups.json") as groups:
                with open(os.path.join(self.backup_dir, "backup.log"), "a") as logfile:
                    logfile.write(f"Groups backup : {len(json.load(groups))}\n")

        # Number of ro contacts
        if os.path.isdir(self.backup_dir + "/Subtemplates_contacts"):
            with open(os.path.join(self.backup_dir, "backup.log"), "a") as logfile:
                logfile.write(
                    f"Contacts (reusable objects) backup : {len(os.listdir(self.backup_dir + '/Subtemplates_contacts'))}\n")

        # Number of ro extents
        if os.path.isdir(self.backup_dir + "/Subtemplates_extents"):
            with open(os.path.join(self.backup_dir, "backup.log"), "a") as logfile:
                logfile.write(
                    f"Extents (reusable objects) backup : {len(os.listdir(self.backup_dir + '/Subtemplates_extents'))}\n")

        # Number of ro formats
        if os.path.isdir(self.backup_dir + "/Subtemplates_formats"):
            with open(os.path.join(self.backup_dir, "backup.log"), "a") as logfile:
                logfile.write(
                    f"Formats (reusable objects) backup : {len(os.listdir(self.backup_dir + '/Subtemplates_formats'))}\n")

    def __backup_harvesting_settings(self):
        """
        Backup harvesting setting from DB into a json file.
        """

        print("Backup harvesting settings...", end="\r")
        harvesting = dict()

        try:
            connection = self.db_connect()

            with connection.cursor() as cursor:

                cursor.execute("SELECT name,value FROM public.harvestersettings " \
                                "WHERE value != '' ORDER BY id ASC")

                for row in cursor:
                    if row[0] == "name":
                        name = row[1]
                        harvesting[name] = {}
                    else:
                        if "name" in locals():
                            harvesting[name][row[0]] = row[1]

        except (Exception, psycopg2.Error) as error:
            print("Error while fetching data from PostgreSQL", error)

        else:
            with open(os.path.join(self.backup_dir, "harvesting_settings.json"), "w") as file:
                json.dump(harvesting, file, indent=4)

        finally:
            if connection:
                connection.close()

        print(f"Backup harvesting settings {utils.okgreen('Done')}")
