geopycat provides a CLI script to delete subtemplates that are not referenced in any metadata. In order to successfully
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
```bash
delete_unused_subtpl [-env [env]]  [-older-than [older-than]] [--no-backup] [-db-user [database username]] [-db-password [database password]]
```

* `env` int or prod (optional, by default int)
* `older-than` integer (number of months), delete subtemplates that have not been updated since x months (optional, by default 3)
* `--no-backup` do not backup subtemplates before deletion (optional)
* `db username`: database username (optional, see Database connection)
* `db password`: database password (optional, see Database connection)

## Running on windows
```bash
python delete_unused_subtpl.py [-env [env]]  [-older-than [older-than]] [--no-backup] [-db-user [database username]] [-db-password [database password]]
```
## Running on windows (swisstopo)
```bash
& "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\scripts\delete_unused_subtpl.py" [-env [env]]  [-older-than [older-than]] [--no-backup] [-db-user [database username]] [-db-password [database password]]
```
## Example (swisstopo)
```bash
& "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\scripts\delete_unused_subtpl.py" -env prod  -older-than 3
```