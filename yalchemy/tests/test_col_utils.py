""" Unit tests for column utilities """

import pytest

from yalchemy import col_utils


@pytest.mark.parametrize('datatype,expected', [
    ('int8', 'bigint'),
    ('integer []', 'integer[]'),
    ('date []', 'date[]'),
    ('float4', 'real'),
    ('timestamp with time zone', 'timestamp_with_time_zone', ),
    ('timestamp   with   time zone', 'timestamp_with_time_zone'),
    ('bool', 'boolean'),
    ])
def test_clean_datatype(expected, datatype):
    """ Test that datatypes that we recieve are cleaned and
    are not alias names in postgres """

    assert col_utils.clean_datatype(datatype) == expected


def test_is_schema_qualified():
    assert col_utils.is_schema_qualified('my_schema.my_sequence') is True
    assert col_utils.is_schema_qualified('my_sequence') is False


@pytest.mark.parametrize('input_string, expected_output', [
    # various quotes styles
    ("'test'", 'test'),
    ('"test"', 'test'),
    ('\'"test"\'', 'test'),
    # normal string
    ('test', 'test'),
])
def test_unquote_sql_string(input_string, expected_output):
    assert col_utils.unquote_sql_string(input_string) == expected_output
