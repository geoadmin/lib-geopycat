import psycopg2
from geopycat import geocat
from geopycat import utils

class ManageSubtemplate(geocat):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    def replace_subtpl(self, old_uuid: str, new_uuid: str):
        """
        Replace a subtemplate in all metadata
        """

        if not self.check_admin():
            raise Exception("You must be admin to use this function")

        metadata_uuids = list()

        try:
            connection = self.db_connect()
            with connection.cursor() as cursor:

                cursor.execute("SELECT uuid FROM public.metadata where (istemplate='n' OR istemplate='y')" \
                                f"AND data like '%{old_uuid}%'")

                for row in cursor:
                    metadata_uuids.append(row[0])

        except (Exception, psycopg2.Error) as error:
            print("Error while fetching data from PostgreSQL", error)

        finally:
            if connection:
                connection.close()

        headers = {"accept": "application/json", "Content-Type": "application/json"}

        if len(metadata_uuids) == 0:
            print(utils.warningred(f"Subtemplate {old_uuid} not found in any metadata"))
            return

        for uuid in metadata_uuids:

            params = {
                "search": old_uuid,
                "replace": new_uuid,
                "uuids": [uuid],
                "updateDateStamp": False
            }

            response = self.session.post(self.env + "/geonetwork/srv/api/processes/db/search-and-replace",
                                params=params, headers=headers)

            if utils.process_ok(response):
                print(utils.okgreen(f"Metadata {uuid} : subtemplate {old_uuid} successfully replaced by {new_uuid}"))
            else:
                print(utils.warningred(f"Metadata {uuid} : subtemplate {old_uuid} unsuccessfully replaced by {new_uuid}"))

