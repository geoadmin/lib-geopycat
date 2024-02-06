geopycat provides a CLI script to apply the process done while saving metadata. It basically saves and closes metadata.

## Running on UNIX system
```bash
save_and_close [-env [env]]  [--in-groups [in-groups]] [--not-in-groups [not-in-groups]]
```

* `env` int or prod (optional, by default int)
* `in-groups` integers (optional): groups ID list, process metadata from these groups. <br>E.g. `--in-groups 42 23 12`
* `not-in-groups` integers()optional): groups ID list, **do not** process metadata from these groups. <br>E.g. `--not-in-groups 42 23 12`

## Running on windows
```bash
python3 save_and_close.py [-env [env]]  [--in-groups [in-groups]] [--not-in-groups [not-in-groups]]
```
## Running on windows (swisstopo)
```bash
& "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\scripts\save_and_close.py" [-env [env]]  [--in-groups [in-groups]] [--not-in-groups [not-in-groups]]
```
