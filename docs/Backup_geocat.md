geopycat provides a CLI script to generate backups of geocat.ch. In order to successfully
run this script, you should have admin rights and be able to connect to the PostgreSQL database of geocat.ch.

## Database connection
You can specify the username and password for connecting to the database in environment variables.
If not, the script will prompt for credentials.

In a `.env` file
```bash
DB_USERNAME=username
DB_PASSWORD=password
```

## Running on UNIX system
```bash
geocat_backup [-env] [-o] [-m] [-u] [-g] [-s] [-db-user] [-db-password]
```
```
-env: int or prod
-o: output folder
-m: do not bakcup metadata
-u: do not bakcup users
-g: do not bakcup groups
-s: do not bakcup subtemplates
-db-user: database username
-db-password: database password
```
## Running on windows
```bash
python geocat_backup.py [-env] [-o] [-m] [-u] [-g] [-s] [-db-user] [-db-password]
```
## Running on windows (swisstopo)
```bash
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\scripts\geocat_backup.py" [-env] [-o] [-m] [-u] [-g] [-s] [-db-user] [-db-password]
```