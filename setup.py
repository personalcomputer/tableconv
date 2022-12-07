import io
import os

from setuptools import find_packages, setup

NAME = 'tableconv'

here = os.path.abspath(os.path.dirname(__file__))
with io.open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = '\n' + f.read()
about = {}
with open(os.path.join(here, NAME, '__version__.py')) as f:
    exec(f.read(), about)

setup(
    name=NAME,
    version=about['__version__'],
    description='CLI data plumbing tool',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='John Miller',
    author_email='john@johngm.com',
    python_requires='>=3.7.0',
    url='https://github.com/personalcomputer/tableconv',
    packages=find_packages(include=['tableconv', 'tableconv.*']),
    entry_points={
        'console_scripts': ['tableconv=tableconv.__main__:main'],
    },
    install_requires=[
        'black',
        'boto3',
        'ciso8601',
        'duckdb',
        'fsspec',
        'genson',
        'google-api-python-client',
        'httplib2',
        'marko',
        'oauth2client',
        'python-dateutil',
        'PyYAML',
        'pymysql',
        'tabulate',
        'pandas',
        # pandas io deps below. ref: https://pandas.pydata.org/docs/getting_started/install.html#optional-dependencies
        'xlrd',
        'xlwt',
        'fastparquet',
        'lxml',
        'openpyxl',
        'xlsxwriter',
        'psycopg2-binary>=2.6.2',
        'sqlalchemy',
        'pyarrow',
        # 'tables',  # needed for hd5
    ],
    extras_require={},
    include_package_data=True,
    license='MIT',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
)
