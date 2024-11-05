import io
import os

from setuptools import find_packages, setup

NAME = "tableconv"

here = os.path.abspath(os.path.dirname(__file__))
with io.open(os.path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = "\n" + f.read()
about = {}
with open(os.path.join(here, NAME, "__version__.py")) as f:
    exec(f.read(), about)

setup(
    name=NAME,
    version=about["__version__"],
    description="CLI data plumbing tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="John Miller",
    author_email="john@johngm.com",
    python_requires=">=3.7.0",
    url="https://github.com/personalcomputer/tableconv",
    packages=find_packages(include=["tableconv_daemon", "tableconv_daemon.*", "tableconv", "tableconv.*"]),
    entry_points={
        "console_scripts": [
            "tableconv=tableconv_daemon.main:main_wrapper",
        ],
    },
    install_requires=[
        "black",  # >=22.10.0",
        "boto3",  # >=1.25.4",
        "ciso8601",  # >=2.2.0",
        "duckdb>=0.10.0",
        "fsspec",  # >=2022.11.0",
        "genson",  # >=1.2.2",
        "google-api-python-client",  # >=2.68.0",
        "httplib2",  # >=0.20.2",
        "lxml",  # >=4.9.1",
        "marko",  # >=1.2.2",
        "oauth2client",  # >=4.1.3",
        "pandas>=2.0.0",
        "python-dateutil",  # >=2.8.2",
        "PyYAML",  # >=5.4.1",
        "tabulate",  # >=0.8.10",
        "pexpect",  # >=4.8.0",
        # pandas io deps below. ref: https://pandas.pydata.org/docs/getting_started/install.html#optional-dependencies
        "fastparquet",  # >=2022.11.0",
        "lxml",  # >=4.9.1",
        "openpyxl",  # >=3.0.10",
        "psycopg2-binary",  # >=2.9.5",
        "pyarrow",  # >=10.0.1",
        "PyMySQL",  # >=1.0.2",
        "SQLAlchemy>=2.0.0",
        "xlrd",  # >=2.0.1",
        "XlsxWriter",  # >=3.0.3",
        "xlwt",  # >=1.3.0",
        # 'tables",  # needed for hd5
        # 'dpkt', # >=1.9.8  # needed for pcap
    ],
    extras_require={},
    include_package_data=True,
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
)
