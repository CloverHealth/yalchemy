"""
Copyright (c) 2005-2018 the SQLAlchemy authors and contributors <see AUTHORS file>.
SQLAlchemy is a trademark of Michael Bayer.

SQLAlchemy utility which have been modified for use with yalchemy
"""
import re
import sqlalchemy.dialects.postgresql as sa_pg


class UnknownColumnType(Exception):
    """ Raised when the type given for a column is
    not known to Sqlalchemy """


def sa_type_from_str(col_type, col_args=()):
    """Convert a str datatype into a sqlalchemy datatype.
    This is mostly a copy and paste from the _get_column_info
    located at sa_pg.dialect()._get_column_info() """

    dialect = sa_pg.dialect()

    # replace _ with spaces and uppercase
    col_type = col_type.replace('_', ' ').lower()

    # strip (*) from character varying(5), timestamp(5)
    # with time zone, geometry(POLYGON), etc.
    attype = re.sub(r'\(.*\)', '', col_type)

    # strip '[]' from integer[], etc.
    attype = attype.replace('[]', '')

    is_array = col_type.endswith('[]')
    attype, args, kwargs = _special_att_handling(attype, col_args)

    coltype = dialect.ischema_names.get(attype)
    if coltype:
        coltype = coltype(*args, **kwargs)
        if is_array:
            coltype = dialect.ischema_names['_array'](coltype)
    else:
        raise UnknownColumnType(
            "Did not recognize column type '%s'" % attype)
    return coltype


# pylint: disable=too-many-statements,too-many-branches
def _special_att_handling(attype, col_args):  # noqa: C901
    """ laundry list of special handling that sqlalchemy
    does to convert between a Postgres type and a Sqlalchemy type """

    kwargs = {}

    if attype == 'uuid':
        kwargs = {'as_uuid': True}
        args = ()
    elif attype == 'numeric':
        if col_args:
            prec, scale = col_args
            args = (int(prec), int(scale))
        else:
            args = ()
    elif attype == 'double precision':
        args = (53, )
    elif attype == 'integer':
        args = ()
    elif attype in ('timestamp with time zone',
                    'time with time zone',
                    'datetime with time zone'):
        attype = attype.replace('datetime', 'timestamp')
        kwargs['timezone'] = True
        args = ()
    elif attype in ('timestamp without time zone',
                    'time without time zone',
                    'datetime without time zone',
                    'datetime',
                    'time'):
        attype = attype.replace('datetime', 'timestamp')
        kwargs['timezone'] = False
        args = ()
    elif attype == 'bit varying':
        kwargs['varying'] = True
        if col_args:  # pragma: no cover
            assert len(col_args) == 1
            args = (col_args[0],)
        else:
            args = ()
    elif attype == 'varchar':
        attype = 'character varying'
        if col_args:
            assert len(col_args) == 1
            args = (col_args[0],)
        else:  # pragma: no cover
            args = ()
    elif attype == 'char':
        attype = 'character'
        args = col_args
    elif attype.startswith('interval'):
        field_match = re.match(r'interval (.+)', attype, re.I)
        if col_args:  # pragma: no cover
            assert len(col_args) == 1
            kwargs['precision'] = col_args[0]
        if field_match:  # pragma: no cover
            kwargs['fields'] = field_match.group(1)
        attype = "interval"
        args = ()
    else:
        args = col_args or ()
    return attype, args, kwargs
