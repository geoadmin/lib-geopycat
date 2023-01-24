import argparse
import os
import colorama
from geopycat.subtemplate.delete_unused_subtpl import DeleteUnusedSubtemplate

colorama.init()

parser = argparse.ArgumentParser()

parser.add_argument("-env", nargs= '?', const="int", default="int")
parser.add_argument("-older-than", nargs= '?', type=int, const=3, default=3)
parser.add_argument("--no-backup", action="store_false")
parser.add_argument("-db-user")
parser.add_argument("-db-password")

args = parser.parse_args()

if __name__ == "__main__":

    if args.db_user is not None:
        os.environ["DB_USERNAME"] = args.db_user

    if args.db_password is not None:
        os.environ["DB_PASSWORD"] = args.db_password

    DeleteUnusedSubtemplate(env=args.env, older_than=args.older_than, with_backup=args.no_backup)