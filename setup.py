import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="geopycat",
    version="0.2.4",
    author="Benoit G. Regamey",
    author_email="benoit.regamey@swisstopo.ch",
    description="Manage metadata and data of geocat.ch - a geonetwork instance for Switzerland",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        'requests >=2.25.1',
        'urllib3 >=1.26.6',
        'python-dotenv >=0.20.0',
        'psycopg2 >= 2.9.3',
        'pandas >= 1.2.3',
        'colorama >= 0.4.5',
        'python-dateutil >= 2.8.1',
    ],
    scripts=[
        'bin/geocat_backup.py',
        'bin/geocat_backup',
        'bin/delete_unused_subtpl.py',
        'bin/delete_unused_subtpl',
        'bin/save_and_close.py',
        'bin/save_and_close'
    ]
)
