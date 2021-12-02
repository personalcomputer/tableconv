import io
import os

from setuptools import find_packages, setup

NAME = 'tableconv'

here = os.path.abspath(os.path.dirname(__file__))
with io.open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = '\n' + f.read()
about = {}
project_slug = NAME.lower().replace("-", "_").replace(" ", "_")
with open(os.path.join(here, project_slug, '__version__.py')) as f:
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
    url='https://github.com/Ridecell/tableconv',
    packages=find_packages(exclude=["tests", "*.tests", "*.tests.*", "tests.*"]),
    entry_points={
        'console_scripts': ['tableconv=tableconv.__main__:main'],
    },
    install_requires=[
        'black',
        'boto3',
        'ciso8601',
        'duckdb',
        'fastparquet',
        'fsspec',
        'genson',
        'google-api-python-client',
        'httplib2',
        'marko',
        'oauth2client',
        'pandas',
        'psycopg2-binary>=2.6.2',
        'python-dateutil',
        'PyYAML',
        'sqlalchemy',
        'sumologic-sdk',
        'tabulate',
        'xlrd',
        'xlwt',
    ],
    extras_require={},
    include_package_data=True,
    license='MIT',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
)
