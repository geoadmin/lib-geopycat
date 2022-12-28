import argparse
import os
from geopycat.GeocatBackup import GeocatBackup

parser = argparse.ArgumentParser()

parser.add_argument("-env", nargs= '?', const="int", default="int")
parser.add_argument("-o", "--output-folder")
parser.add_argument("-m", "--metadata", action="store_false")
parser.add_argument("-u", "--users", action="store_false")
parser.add_argument("-g", "--groups", action="store_false")
parser.add_argument("-s", "--subtpl", action="store_false")
parser.add_argument("-db-user")
parser.add_argument("-db-password")

args = parser.parse_args()

if __name__ == "__main__":

    if args.db_user is not None:
        os.environ["DB_USERNAME"] = args.db_user

    if args.db_password is not None:
        os.environ["DB_PASSWORD"] = args.db_password

    GeocatBackup(env=args.env, backup_dir=args.output_folder, catalogue=args.metadata,
                    users=args.users, groups=args.groups, subtemplates=args.subtpl)
