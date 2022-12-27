import os
import json
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
                 groups: bool = True, subtemplates: bool = True, thesaurus: bool = True,
                 **kwargs):

        super().__init__(**kwargs)

        if not self.check_admin():
            print(utils.warningred("You must be logged-in as Admin to generate a backup !"))
            return

        print("Backup started...")

        if backup_dir is None:
            self.backup_dir = f"GeocatBackup_{datetime.now().strftime('%Y%m%d-%H%M%S')}"

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
        # if thesaurus:
        #     self.backup_thesaurus()

        # self.write_logfile()
        # self.backup_unpublish_report()

        print(utils.okgreen("Backup Done"))

    def __backup_metadata(self):

        if not os.path.isdir(os.path.join(self.backup_dir, "metadata")):
            os.mkdir(os.path.join(self.backup_dir, "metadata"))

        uuids = self.get_uuids(with_harvested=False, with_templates=True)
        self.backup_metadata(uuids=uuids, backup_dir=os.path.join(self.backup_dir, "metadata"))

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

        subtpl_uuids = self.get_ro_uuids()

        def export_subtemplate(uuid):
            headers = {"accept": "application/xml", "Content-Type": "application/xml"}
            parameters = {"lang": "ger,fre,ita,eng,roh"}

            response = self.session.get(
            url=self.env + f"/geonetwork/srv/api/registries/entries/{uuid}", 
            headers=headers, params=parameters)

            if response.status_code != 200:
                print(f"{utils.warningred('The following contact could not be backup : ') + uuid}")
                return

            xmlroot = ET.fromstring(response.text)

            if xmlroot.tag == "apiError":
                print(f"{utils.warningred('The following contact could not be backup : ') + uuid}")
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
