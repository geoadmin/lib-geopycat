geopycat provides a CLI script to generate backups of geocat.ch. In order to successfully
run this script, you should have admin rights and be able to connect to the PostgreSQL database of geocat.ch.

## Database connection
You can specify the username and password for connecting to the database in environment variables or in CLI parameters (see below).
If not, the script will prompt for credentials.

In a `.env` file
```bash
DB_USERNAME=username
DB_PASSWORD=password
```

## Running on UNIX system
``` bash
geocat_backup [-env [env]] [-o [o]] [-m] [-u] [-g] [-s] [-db-user [db username]] [-db-password [db password]]
```
```
env: int or prod    (optional, by default int)
o: output folder    (optionaL, if not set, the backup will be saved in the current working directory)
-m: do not backup metadata  (optional)
-u: do not backup users (optional)
-g: do not backup groups    (optional)
-s: do not backup subtemplates  (optional)
db username: database username  (optional, see Database connection)
db password: database password  (optional, see Database connection)
```
## Running on windows
```bash
python geocat_backup.py [-env [env]] [-o [o]] [-m] [-u] [-g] [-s] [-db-user [db username]] [-db-password [db password]]
```
## Running on windows (swisstopo)
```bash
& "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\scripts\geocat_backup.py" [-env] [-o] [-m] [-u] [-g] [-s] [-db-user] [-db-password]
```