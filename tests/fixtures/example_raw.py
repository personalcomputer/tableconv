import textwrap

EXAMPLE_CSV_RAW = textwrap.dedent(
    """
    id,name,date
    1,George,2023
    2,Steven,1950
    3,Rachel,1995
"""
).strip()
EXAMPLE_TSV_RAW = textwrap.dedent(
    """
    id\tname\tdate
    1\tGeorge\t2023
    2\tSteven\t1950
    3\tRachel\t1995
"""
).strip()
EXAMPLE_JSON_RAW = textwrap.dedent(
    """
    [
        {"id":1,"name":"George","date":2023},
        {"id":2,"name":"Steven","date":1950},
        {"id":3,"name":"Rachel","date":1995}
    ]
"""
).strip()
EXAMPLE_LIST_RAW = textwrap.dedent(
    """
    a
    b
    c
"""
).strip()
EXAMPLE_RECORDS = [
    {"id": 1, "name": "George", "date": 2023},
    {"id": 2, "name": "Steven", "date": 1950},
    {"id": 3, "name": "Rachel", "date": 1995},
]
