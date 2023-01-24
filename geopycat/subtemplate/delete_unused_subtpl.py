import psycopg2
from geopycat import geocat
from geopycat import utils
from datetime import datetime
from dateutil.relativedelta import relativedelta


class DeleteUnusedSubtemplate(geocat):
    """
    Delete unused subtemplates
    Args:
        env: 'int' or 'prod'
        older_than: delete only subtemplates older than x months
        with_backup: backup subtemplates before deletion
    """

    def __init__(self, older_than: int = 3, with_backup: bool = True, **kwargs):

        super().__init__(**kwargs)
        self.date_limit = datetime.today() - relativedelta(months=older_than)

        if not self.check_admin():
            raise Exception("You have to be admin to run this program")

        uuids = self.__get_unused_subtemplates()

        if with_backup:
            for key in uuids:
                self.backup_metadata_xml(uuids=uuids[key], backup_dir=f"Backup_{key}")

        for key in uuids:

            if len(uuids[key]) > 0:
                res = input(f"{len(uuids[key])} {key} found. Are you sure to delete them ? (y/n)")
                if res == 'y':
                    for uuid in uuids[key]:
                        response = self.delete_metadata(uuid=uuid)

                        if response.status_code == 204:
                            print(f"{key} {uuid} : {utils.okgreen('successfully deleted')}")
                        else:
                            print(f"{key} {uuid} : {utils.warningred('could not be deleted')}")

    def __get_unused_subtemplates(self) -> dict:
        """Get uuids of unused subtemplates"""

        uuids_contact = list()
        uuids_extent = list()
        uuids_format = list()

        print("Analysing RO usage : ", end="\r")

        try:
            connection = self.db_connect()

            with connection.cursor() as cursor:

                cursor.execute(
                    "SELECT UUID,data FROM public.metadata WHERE (istemplate='s')" \
                    "and uuid NOT LIKE '%hoheitsgebiet%' " \
                    "and uuid NOT LIKE '%bezirk%' " \
                    "and uuid NOT LIKE '%kantonsgebiet%' " \
                    "and uuid NOT LIKE '%landesgebiet%' " \
                    f"and changedate < '{self.date_limit.strftime('%Y-%m-%d')}'"
                )

                count = 0

                for row in cursor:
                    with connection.cursor() as cur2:
                        cur2.execute(f"SELECT uuid FROM public.metadata WHERE data ~ '.*{row[0]}[^0-9].*'")
                        if cur2.rowcount == 0:
                            if row[1].startswith("<che:CHE_CI_ResponsibleParty"):
                                uuids_contact.append(row[0])
                            elif row[1].startswith("<gmd:EX_Extent"):
                                uuids_extent.append(row[0])
                            elif row[1].startswith("<gmd:MD_Format"):
                                uuids_format.append(row[0])

                    count += 1
                    print(f"Analysing RO usage: {round((count / cursor.rowcount) * 100, 1)}%", end="\r")
                print(f"Analysing RO usage : {utils.okgreen('Done')}")

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
