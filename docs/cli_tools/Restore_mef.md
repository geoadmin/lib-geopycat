# Restore records from MEF
geopycat provides a CLI script to retore multiple records saved as MEF (Metadata Exchange Format).
MEF has the advantage of packing record UUID, permissions and attachments.

:warning: For now, does not support records that have been deleted :warning:

**The script restores :**

* XML record by overriding current UUID
* Group owner and owner ID
* Attachments
* Permissions
* Performs validation of the record

## Running on UNIX system
```bash
restore_mef [-env [env]] --mef-folder [mef-folder]
```

* `env`: int or prod
* `mef-folder`: folder path containing the MEF files to restore

## Running on windows
```bash
python restore_mef.py [-env [env]] --mef-folder [mef-folder]
```
## Running on windows (swisstopo)
```bash
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\scripts\restore_mef.py" [-env [env]] --mef-folder [mef-folder]
```