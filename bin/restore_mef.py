import argparse
import colorama
import os
from geopycat.GeocatBackup import Restore
from geopycat import utils
from datetime import datetime

colorama.init()

parser = argparse.ArgumentParser()

parser.add_argument("-env", nargs= '?', const="int", default="int")
parser.add_argument("--mef-folder", nargs=1, type=str)

args = parser.parse_args()

if __name__ == "__main__":

    restore = Restore(env=args.env)

    mefs = [os.path.join(args.mef_folder, i) for i in os.listdir(args.mef_folder) if i.endswith(".zip")]

    count = 0

    for mef in mefs:

        count += 1

        try:
            restore.restore_metadata_from_mef(mef=mef)

        except:
            print(utils.warningred(f"[{round((count / len(mefs)) * 100, 1)}%] {mef} - unable to restore record"))
            continue

        print(utils.okgreen(f"[{round((count / len(mefs)) * 100, 1)}%] {mef} - record restored successfully"))
