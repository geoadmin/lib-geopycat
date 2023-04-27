import zipfile
import os
from lxml import etree as ET
import geopycat


class Restore(geopycat.geocat):
    """
    Class to restore metadata and subtemplates
    """

    def __init__(self, **kwargs):

        super().__init__(**kwargs)

        headers = {"accept": "application/json", "Content-Type": "application/json"}

        params = {
            "withReservedGroup": True
        }

        res = self.session.get(self.env + "/geonetwork/srv/api/groups",
                                    headers=headers, params=params)

        if res.status_code == 200:
            self.groups = res.json()
        else:
            raise Exception("Could not fetch groups information")

    def __get_permissions(self, xml: bytes) -> dict:
        """
        Fetches permissions from info.xml file inside MEF.
        Args:
            xml : the info.xml file as bytes
        """

        permissions = {
            "clear": True,
            "privileges": []
        }

        xml_root = ET.fromstring(xml)

        for group in xml_root.findall("./privileges/group"):

            # Get group ID from group name
            i = [i for i in self.groups if i["name"] == group.attrib["name"]]

            if len(i) != 1:
                raise Exception("Could not fetch group ID from group name")
            
            permissions["privileges"].append({
                "group": i[0]["id"],
                "operations": {
                    "view": False,
                    "download": False,
                    "dynamic": False,
                    "featured": False,
                    "notify": False,
                    "editing": False
                }
            })

            for operation in group.findall("operation"):
                permissions["privileges"][-1]["operations"][operation.attrib["name"]] = True

        return permissions

    def restore_metadata_from_mef(self, mef: str):
        """
        Restore a metadata from its MEF file.
        UUID, permissions are taken from MEF.
        Ownership is taken from exsiting record.
        An internal validation process is performed on the restored record.
        """

        # Get info.xml from MEF
        filename = os.path.splitext(os.path.basename(mef))[0]
        archive = zipfile.ZipFile(mef, 'r')
        xml = archive.read(f'{filename}/info.xml')

        # Get UUID from MEF
        xml_root = ET.fromstring(xml)
        uuid = xml_root.find("./general/uuid").text

        # Get ownership
        ownership = self.get_metadata_ownership(uuid=uuid)

        # Upload MEF
        headers = {"accept": "application/json"}

        params = {
            "metadataType": "METADATA",
            "uuidProcessing": "OVERWRITE",
            "group": ownership["group_ID"],
            "transformWith": "_none_"
        }

        with open(mef, 'rb') as fileobj:
            res = self.session.post(url=self.env + "/geonetwork/srv/api/records",
                params=params, headers=headers, files={"file": (os.path.basename(mef), fileobj)})

        if not geopycat.utils.process_ok(res):
            raise Exception("Could not upload metadata")
        
        # Validate metadata
        self.validate_metadata(uuid=uuid)

        # set permissions (handles publication status as well)
        permission = self.__get_permissions(xml=xml)
        res = self.set_metadata_permission(uuid=uuid, permission=permission)

        if res.status_code != 204:
            raise Exception("Could not set metadata permission back")
        
        # set ownership
        res = self.set_metadata_ownership(uuid=uuid, group_id=ownership["group_ID"], 
                                            user_id=ownership["owner_ID"])
        if not geopycat.utils.process_ok(res):
            raise Exception("Could not set metadata ownership back")

        print(geopycat.utils.okgreen("metadata successfully restored"))
