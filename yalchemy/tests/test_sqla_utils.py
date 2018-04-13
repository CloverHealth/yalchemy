"""
Unit tests for SQLAlchemy utilities to ensure that we convert a str representation of a data type
to the correct sqlalchemy type
"""
import geoalchemy2
import pytest
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as sa_pg

from yalchemy import sqla_utils


@pytest.mark.parametrize('expected,col_type,col_args', [
    (sa.String(255), 'varchar', [255]),
    (sa.String(10), 'varchar', [10]),
    (sa.Text(), 'text', []),
    (sa.CHAR(), 'char', []),
    (sa_pg.BYTEA(), 'bytea', []),
    (sa_pg.BIT(varying=True), 'bit varying', []),
    (sa.Date(), 'date', []),
    (sa.TIMESTAMP(), 'datetime', []),
    (sa.TIMESTAMP(), 'datetime_without_time_zone', []),
    (sa.TIMESTAMP(timezone=True), 'datetime_with_time_zone', []),
    (sa.TIMESTAMP(), 'timestamp', []),
    (sa.TIMESTAMP(), 'timestamp_without_time_zone', []),
    (sa.TIMESTAMP(timezone=True), 'timestamp_with_time_zone', []),
    (sa.Time(), 'time', []),
    (sa.Time(), 'time', []),
    (sa.Time(timezone=True), 'time_with_time_zone', []),
    (sa.Boolean(), 'boolean', []),
    (sa.Integer(), 'integer', []),
    (sa.BigInteger(), 'bigint', []),
    (sa.SmallInteger(), 'smallint', []),
    (sa_pg.UUID(), 'uuid', []),
    (sa_pg.UUID(as_uuid=True), 'uuid', []),
    (sa_pg.JSON(), 'json', []),
    (sa_pg.JSONB(), 'jsonb', []),
    (sa.Numeric(10, 2), 'numeric', [10, 2]),
    (sa.Numeric(), 'numeric', []),
    (sa.REAL(), 'real', []),
    (sa_pg.DOUBLE_PRECISION(), 'double_precision', []),
    (sa_pg.INTERVAL(), 'interval', []),
    (sa_pg.TSTZRANGE(), 'tstzrange', []),
    (sa_pg.INT4RANGE(), 'int4range', []),
    (sa_pg.DATERANGE(), 'daterange', []),
    (geoalchemy2.Geography('point', 4326), 'geography', ['Point', 4326]),
    # arrays
    (sa_pg.ARRAY(sa.Integer), 'integer[]', []),
    # errors
    pytest.mark.xfail((sa.types.NullType(), 'N/A', []),
                      raises=sqla_utils.UnknownColumnType, strict=True),
    ], ids=str)
def test_sa_type_from_str(expected, col_type, col_args):
    sa_type = sqla_utils.sa_type_from_str(col_type, col_args)
    assert sa_type.compile(sa_pg.dialect()) == expected.compile(sa_pg.dialect())


def test_sa_type_arrays():
    """ Test that we handle arrays properly with sa types """

    sa_type = sqla_utils.sa_type_from_str('text[]')
    assert isinstance(sa_type, sa_pg.ARRAY)
    assert isinstance(sa_type.item_type, sa.Text)


def test_invalid_type():
    """ Test that we raise an UnknownType error when we
    put in some weird postgres type """

    with pytest.raises(sqla_utils.UnknownColumnType):
        sqla_utils.sa_type_from_str('unknown_type')
