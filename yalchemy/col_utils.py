""" Helper utilities for converting to a sqlalchemy type
from a string """
# pylint: disable=arguments-differ

import re

POSTGRES_ALIASES = {
    'int8': 'bigint',
    'bool': 'boolean',
    'decimal': 'numeric',
    'float4': 'real',
    'float8': 'double precision',
    'int2': 'smallint',
    'int4': 'integer',
    'int': 'integer',
    'serial2': 'smallserial',
    'serial4': 'serial',
    'timetz': 'time with time zone',
    'timestamptz': 'timestamp with time zone'
}


REGEX_SCHEMA_QUALIFIED = re.compile(r'^\w+\.\w+$')


def clean_datatype(datatype):
    """ Datatypes can have aliases (such as int for integer). This cleans
    the datatypes so there is always one consistent datatype used for the
    Column.datatype module """

    raw_datatype = str(datatype).strip()

    is_array = datatype.endswith('[]')
    if is_array:
        raw_datatype = raw_datatype[:-2].strip()  # remove array and whitespace before array

    raw_datatype = POSTGRES_ALIASES.get(raw_datatype, raw_datatype)
    clean_datatype = re.sub(r'\W+', '_', raw_datatype)
    if is_array:
        return clean_datatype + '[]'
    else:
        return clean_datatype


def is_schema_qualified(expression):
    return REGEX_SCHEMA_QUALIFIED.fullmatch(expression) is not None


def unquote_sql_string(expression):
    return expression.strip("'\"")
