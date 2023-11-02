# Getting Started

## Installation (requires an installation of git)

The package requires `python 3`

**Using pip** - install from github

```console
$ pip install git+https://github.com/benoitregamey/geopycat.git
---> 100%
Installed
```
**From swisstopo network** - through proxy
```console
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\Scripts\pip3" install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host github.com --proxy=proxy-bvcol.admin.ch:8080 git+https://github.com/benoitregamey/geopycat.git
```
**Install an older version**
```console
$ pip install git+https://github.com/benoitregamey/geopycat.git@version
```

## Not having **git** installed ?
Download the package as a zip file
```console
$ curl -L0 https://github.com/benoitregamey/geopycat/archive/refs/heads/main.zip --output geopycat.zip
```
Unzip it, if on UNIX 
```console
$ unzip geopycat.zip
```
Go into the directory and install the package from here
```console
$ cd geopycat-main
$ pip3 install .
```
If on **swisstopo network**
```console
cd geopycat-main
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\Scripts\pip3" install --trusted-host pypi.org --trusted-host pypi.python.org --proxy=proxy-bvcol.admin.ch:8080 .
```