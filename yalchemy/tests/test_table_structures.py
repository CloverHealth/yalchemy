"""Tests for clover.data_ingest.parsing.parsers.table_structures"""
# pylint: disable=too-many-lines
import copy

import pytest
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as sa_pg
import sqlalchemy.sql.elements as sa_elements
import sqlalchemy.sql.functions as sa_func

from yalchemy import table_structures


# COLUMN DEFAULTS

def test_column_default_from_dict():
    """ Test that we build this ColumnDefault object correctly from a dict """
    col_default = table_structures.ColumnDefault.from_dict(
        {'type': 'expression', 'value': 'foobar'}
    )
    assert col_default.type == table_structures.ColumnDefaultType.expression
    assert col_default.value == 'foobar'

    col_default = table_structures.ColumnDefault.from_dict(
        {'type': 'expression', 'value': 'NOW()'},
    )
    assert col_default.type == table_structures.ColumnDefaultType.expression
    assert col_default.value == 'NOW()'

    col_default = table_structures.ColumnDefault.from_dict(
        {'type': 'sequence', 'value': 'schema.id_seq'},
    )
    assert col_default.type == table_structures.ColumnDefaultType.sequence
    assert col_default.value == 'schema.id_seq'

    with pytest.raises(table_structures.InvalidColumnDefault) as exc:
        table_structures.ColumnDefault.from_dict(
            {'type': 'sequence', 'value': 'unqualified_seq'},
        )
    assert 'Schema must be specified for sequence types' in str(exc.value)


@pytest.mark.parametrize('sqla_server_default, expected_default_type, expected_value', [
    # unquoted string
    ('foobar',
     table_structures.ColumnDefaultType.expression, 'foobar'),
    # quoted strings
    ('"foobar"',
     table_structures.ColumnDefaultType.expression, 'foobar'),
    ("'foobar'",
     table_structures.ColumnDefaultType.expression, 'foobar'),
    # standard expression
    (sa.text('NOW()'),
     table_structures.ColumnDefaultType.expression, 'NOW()'),
    # plain Sequence
    (sa.Sequence('id_seq', schema='schema'),
     table_structures.ColumnDefaultType.sequence, 'schema.id_seq'),
    # sequences resulting from SQLAlchemy internals or table reflection
    (sa.text('nextval(\'"schema.primary_key_seq"\'::regclass)'),
     table_structures.ColumnDefaultType.sequence, 'schema.primary_key_seq'),
    (sa.text("nextval('schema.primary_key_seq'::regclass)"),
     table_structures.ColumnDefaultType.sequence, 'schema.primary_key_seq'),
    (sa.text("nextval('schema.primary_key_seq')"),
     table_structures.ColumnDefaultType.sequence, 'schema.primary_key_seq'),
    (sa_func.next_value(sa.Sequence('primary_key_seq', schema='schema')),
     table_structures.ColumnDefaultType.sequence, 'schema.primary_key_seq'),
])
def test_column_default_from_sqla(sqla_server_default, expected_default_type,
                                  expected_value):
    col_default = table_structures.ColumnDefault.from_sqla(sqla_server_default)
    assert col_default.type == expected_default_type
    assert col_default.value == expected_value


def test_column_default_from_invalid_sqla():
    with pytest.raises(TypeError) as exc:
        table_structures.ColumnDefault.from_sqla(1)
    assert 'must be a sequence, string or SQLAlchemy TextClause' in str(exc.value)

    with pytest.raises(table_structures.InvalidColumnDefault) as exc:
        table_structures.ColumnDefault.from_sqla(sa.text("nextval('primary_key_seq')"))
    assert 'Schema must be specified for sequence types' in str(exc.value)


@pytest.mark.parametrize('column ,expected_metadata', [
    (table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression, '1'),
     {'type': 'expression', 'value': '1'}),
    (table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression, "'foobar'"),
     {'type': 'expression', 'value': 'foobar'}),
    (table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression, 'NOW()'),
     {'type': 'expression', 'value': 'NOW()'}),
    (table_structures.ColumnDefault(table_structures.ColumnDefaultType.sequence,
                                    'schema.my_col_seq'),
     {'type': 'sequence', 'value': 'schema.my_col_seq'}),
])
def test_column_default_to_dict(column, expected_metadata):
    assert column.to_dict() == expected_metadata


def test_column_default_to_sqla():
    col_default = table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression,
                                                 'foobar')
    sa_obj = col_default.to_sqla()
    assert isinstance(sa_obj, sa_elements.TextClause)
    assert str(sa_obj) == 'foobar'

    col_default = table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression,
                                                 'NOW()')
    sa_obj = col_default.to_sqla()
    assert isinstance(sa_obj, sa_elements.TextClause)
    assert str(sa_obj) == 'NOW()'

    col_default = table_structures.ColumnDefault(
        table_structures.ColumnDefaultType.sequence,
        'schema.id_seq'
    )
    sa_obj = col_default.to_sqla()
    assert isinstance(sa_obj, sa.Sequence)
    assert sa_obj.name == 'id_seq'
    assert sa_obj.schema == 'schema'


@pytest.mark.parametrize('left, right, expected', [
    # same parameters
    (table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression, 'NOW()'),
     table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression, 'NOW()'),
     table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression, 'NOW()')),
    # different default types
    pytest.mark.xfail(
        (table_structures.ColumnDefault(table_structures.ColumnDefaultType.sequence,
                                        'myschema.my_seq'),
         table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression,
                                        'myschema.my_seq'),
         None),
        raises=table_structures.MergeError, strict=True),
    # different default expressions
    pytest.mark.xfail(
        (table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression, 'foo'),
         table_structures.ColumnDefault(table_structures.ColumnDefaultType.expression, 'bar'),
         None),
        raises=table_structures.MergeError, strict=True),
])
def test_column_default_or(left, right, expected):
    assert (left | right) == expected


def test_column_default_copy():
    column_default = table_structures.ColumnDefault(
        table_structures.ColumnDefaultType.expression, 'foobar'
    )
    copy1 = copy.copy(column_default)
    assert copy1 == column_default
    assert copy1 is not column_default


# COLUMNS


def test_column_from_dict():
    """ Test that we build this Column object correctly from a dict """

    col = table_structures.Column.from_dict(
        {'name': 'col1', 'datatype': 'text', 'format': 'abc', 'required': True})

    assert col.name == 'col1'
    assert col.datatype == 'text'
    assert col.format == 'abc'
    assert col.required is True
    assert col.default is None

    col = table_structures.Column.from_dict(
        {'name': 'col1', 'datatype': 'text', 'required': False})

    assert col.name == 'col1'
    assert col.datatype == 'text'
    assert col.format is None
    assert col.required is False
    assert col.default is None

    col = table_structures.Column.from_dict(
        {'name': 'col1', 'datatype': 'text', 'required': True,
         'default': {'value': 'barfoo', 'type': 'expression'}},
    )

    assert col.name == 'col1'
    assert col.datatype == 'text'
    assert col.format is None
    assert col.required is True
    assert col.default == table_structures.ColumnDefault(
        table_structures.ColumnDefaultType.expression, 'barfoo')

    col = table_structures.Column.from_dict(
        {'name': 'col1', 'datatype': 'timestamptz', 'required': True,
         'default': {'value': 'NOW()', 'type': 'expression'}},
    )

    assert col.name == 'col1'
    assert col.datatype == 'timestamp_with_time_zone'
    assert col.format is None
    assert col.required is True
    assert isinstance(col.default, table_structures.ColumnDefault)
    assert col.default.type == table_structures.ColumnDefaultType.expression
    assert col.default.value == 'NOW()'

    col = table_structures.Column.from_dict(
        {'name': 'col1', 'datatype': 'bigint', 'required': True,
         'default': {'value': 'schema.primary_key_seq', 'type': 'sequence'}},
    )

    assert col.name == 'col1'
    assert col.datatype == 'bigint'
    assert col.format is None
    assert col.required is True
    assert isinstance(col.default, table_structures.ColumnDefault)
    assert col.default.type == table_structures.ColumnDefaultType.sequence
    assert col.default.value == 'schema.primary_key_seq'


def test_column_from_sqla():
    """ Test that we take a sqlalchemy.Column and make the yalchemy column """
    col = table_structures.Column.from_sqla(
        sa.Column('col1', sa.VARCHAR(255), primary_key=True, nullable=False))

    assert col.name == 'col1'
    assert col.datatype == 'varchar'
    assert col.format == [255]
    assert col.required is True
    assert col.default is None

    col = table_structures.Column.from_sqla(
        sa.Column('col1', sa.Integer, nullable=True))

    assert col.name == 'col1'
    assert col.datatype == 'integer'
    assert col.format is None
    assert col.required is False
    assert col.default is None

    col = table_structures.Column.from_sqla(
        sa.Column('col1', sa.Integer, nullable=False,
                  # SQLAlchemy requires all server-side default primitives to be strings
                  server_default='1'))

    assert col.name == 'col1'
    assert col.datatype == 'integer'
    assert col.format is None
    assert col.required is True
    assert col.default == table_structures.ColumnDefault(
        table_structures.ColumnDefaultType.expression, '1')

    col = table_structures.Column.from_sqla(
        sa.Column('col1', sa_pg.UUID(), nullable=False,
                  server_default=sa.text('uuid_generate_v4()')))

    assert col.name == 'col1'
    assert col.datatype == 'uuid'
    assert col.format is None
    assert col.required is True
    assert col.default == table_structures.ColumnDefault(
        table_structures.ColumnDefaultType.expression, 'uuid_generate_v4()')

    # pylint: disable=no-value-for-parameter
    test_sequence = sa.Sequence('primary_key_seq', schema='schema')
    col = table_structures.Column.from_sqla(
        sa.Column('col1', sa.BigInteger(),
                  test_sequence,
                  server_default=test_sequence.next_value(),
                  nullable=False))
    # pylint: enable=no-value-for-parameter

    assert col.name == 'col1'
    assert col.datatype == 'bigint'
    assert col.format is None
    assert col.required is True
    assert col.default == table_structures.ColumnDefault(
        table_structures.ColumnDefaultType.sequence, 'schema.primary_key_seq')

    # should fail without schema
    test_sequence = sa.Sequence('primary_key_seq')
    with pytest.raises(table_structures.InvalidColumnDefault) as exc:
        # pylint: disable=no-value-for-parameter
        table_structures.Column.from_sqla(
            sa.Column('col1', sa.BigInteger(),
                      test_sequence,
                      server_default=test_sequence.next_value(),
                      nullable=False))
        # pylint: enable=no-value-for-parameter
    assert 'must be qualified with a schema' in str(exc.value)


@pytest.mark.parametrize('column, expected_metadata', [
    (table_structures.Column(name='foo', datatype='string', doc='foo doc'),
     {'name': 'foo', 'datatype': 'string', 'required': False, 'doc': 'foo doc'}),
    (table_structures.Column(name='foo', datatype='string', required=True),
     {'name': 'foo', 'datatype': 'string', 'required': True}),
    (table_structures.Column(name='bar', datatype='boolean', format_='t|f'),
     {'name': 'bar', 'datatype': 'boolean', 'format': 't|f', 'required': False}),
    (table_structures.Column(name='zing', datatype='string', required=True,
                             default=table_structures.ColumnDefault(
                                 table_structures.ColumnDefaultType.expression,
                                 'zang')),
     {'name': 'zing', 'datatype': 'string', 'required': True,
      'default': {'value': 'zang', 'type': 'expression'}}),
    (table_structures.Column(name='zing', datatype='timetz', required=True,
                             default=table_structures.ColumnDefault(
                                 table_structures.ColumnDefaultType.expression,
                                 'current_time')),
     {'name': 'zing', 'datatype': 'time_with_time_zone', 'required': True,
      'default': {'value': 'current_time', 'type': 'expression'}}),

    (table_structures.Column(name='zang', datatype='bigint', required=True,
                             default=table_structures.ColumnDefault(
                                 table_structures.ColumnDefaultType.sequence,
                                 'schema.primary_key_seq')),
     {'name': 'zang', 'datatype': 'bigint', 'required': True,
      'default': {'value': 'schema.primary_key_seq', 'type': 'sequence'}}),
])
def test_column_to_dict(column, expected_metadata):
    assert column.to_dict() == expected_metadata


@pytest.mark.parametrize(
    'yalchemy_col,sa_col,is_primary,default_sa_obj_cls,default_sa_expression', [
        (table_structures.Column(name='my_col', datatype='integer', required=False),
         sa.Column('my_col', sa.Integer, primary_key=False, nullable=True),
         False,
         None,
         None),
        (table_structures.Column(name='my_col', datatype='varchar', format_=[123], required=True),
         sa.Column('my_col', sa.VARCHAR(123), primary_key=True, nullable=False),
         True,
         None,
         None),
        (table_structures.Column(name='my_col', datatype='uuid', format_=[True], required=True,
                                 default=table_structures.ColumnDefault(
                                     table_structures.ColumnDefaultType.expression,
                                     'uuid_generate_v4()')),
         sa.Column('my_col', sa_pg.UUID(as_uuid=True), primary_key=False, nullable=False,
                   server_default=sa.text('uuid_generate_v4()')),
         False,
         sa_elements.TextClause,
         'uuid_generate_v4()'),
        (table_structures.Column(name='my_col', datatype='integer', required=True,
                                 default=table_structures.ColumnDefault(
                                     table_structures.ColumnDefaultType.expression,
                                     '1')),
         sa.Column('my_col', sa.Integer, primary_key=True, nullable=False, server_default='1'),
         True,
         sa_elements.TextClause,
         '1'),
        (table_structures.Column(name='my_col', datatype='integer', required=True,
                                 default=table_structures.ColumnDefault(
                                     table_structures.ColumnDefaultType.sequence,
                                     'schema.my_col_seq')),
         # pylint: disable=no-value-for-parameter
         sa.Column('my_col', sa.Integer, sa.Sequence('my_col_seq', schema='schema'),
                   primary_key=True, nullable=False,
                   server_default=sa.Sequence('my_col_seq', schema='schema').next_value()),
         # pylint: enable=no-value-for-parameter
         True,
         sa_func.next_value,
         'schema.my_col_seq'),
    ]
)
def test_column_to_sqla(yalchemy_col, sa_col, is_primary,
                        default_sa_obj_cls, default_sa_expression):
    """ Test that we turn a yalchemy column into a sqlalchemy column """

    generated_col = yalchemy_col.to_sqla(is_primary=is_primary)
    assert generated_col.name == sa_col.name
    assert generated_col.type.compile(sa_pg.dialect()) == \
        sa_col.type.compile(sa_pg.dialect())
    assert generated_col.nullable == sa_col.nullable
    assert generated_col.primary_key == is_primary
    if default_sa_obj_cls is not None:
        assert isinstance(generated_col.server_default, sa.DefaultClause)

        wrapped_server_default = generated_col.server_default.arg
        assert isinstance(wrapped_server_default, default_sa_obj_cls)

        if default_sa_obj_cls == sa_elements.TextClause:
            value = wrapped_server_default.text
        else:
            assert default_sa_obj_cls == sa_func.next_value
            value = '{}.{}'.format(
                wrapped_server_default.sequence.schema,
                wrapped_server_default.sequence.name,
            )
        assert value == default_sa_expression


@pytest.mark.parametrize('left, right, expected', [
    (table_structures.Column('foo', 'string'),
     table_structures.Column('foo', 'string'),
     table_structures.Column('foo', 'string')),
    (table_structures.Column('foo', 'string'),
     None,
     table_structures.Column('foo', 'string')),
    (None,
     table_structures.Column('foo', 'string'),
     table_structures.Column('foo', 'string')),
    pytest.mark.xfail(
        (table_structures.Column('foo', 'string'),
         table_structures.Column('bar', 'string'),
         table_structures.Column('foo', 'string')),
        raises=table_structures.MergeError, strict=True),
    pytest.mark.xfail(
        (table_structures.Column('foo', 'string'),
         table_structures.Column('foo', 'integer'),
         table_structures.Column('foo', 'string')),
        raises=table_structures.MergeError, strict=True),
    (table_structures.Column('foo', 'boolean', format_='t|f'),
     table_structures.Column('foo', 'boolean', format_='t|f'),
     table_structures.Column('foo', 'boolean', format_='t|f')),
    pytest.mark.xfail(
        (table_structures.Column('foo', 'boolean', format_='t|f'),
         table_structures.Column('foo', 'boolean', format_='1|0'),
         table_structures.Column('foo', 'boolean', format_='t|f')),
        raises=table_structures.MergeError, strict=True),
    (table_structures.Column(name='foo', datatype='string',
                             default={'value': 'foo', 'type': 'expression'}),
     table_structures.Column(name='foo', datatype='string',
                             default={'value': 'foo', 'type': 'expression'}),
     table_structures.Column(name='foo', datatype='string',
                             default={'value': 'foo', 'type': 'expression'})),
    # different default expressions
    pytest.mark.xfail(
        (table_structures.Column(name='foo', datatype='string',
                                 default={'value': 'foo', 'type': 'expression'}),
         table_structures.Column(name='foo', datatype='string',
                                 default={'value': 'bar', 'type': 'expression'}),
         table_structures.Column(name='foo', datatype='string',
                                 default={'value': 'NOTPOSSIBLE', 'type': 'expression'})),
        raises=table_structures.MergeError, strict=True),
    # # left - no default, right - has default
    pytest.mark.xfail(
        (table_structures.Column(name='foo', datatype='string'),
         table_structures.Column(name='foo', datatype='string',
                                 default={'value': 'foo', 'type': 'expression'}),
         table_structures.Column(name='foo', datatype='string',
                                 default={'value': 'NOTPOSSIBLE', 'type': 'expression'})),
        raises=table_structures.MergeError, strict=True),
], ids=str)
def test_column_or(left, right, expected):
    assert (left | right) == expected


def test_column_copy():
    column = table_structures.Column('foo', 'boolean', [], False)
    copy1 = copy.copy(column)
    assert copy1 == column
    assert copy1 is not column
    copy2 = copy.deepcopy(column)
    assert copy2 == column
    assert copy2 is not column
    assert copy2.format is not column.format


# FOREIGN KEYS


def test_foreign_key_from_dict():
    """ Test that we get a yalchemy foreign key from a dict correctly """

    fkey = table_structures.ForeignKey.from_dict(
        {'column': 'user_id', 'remote_table': 'user', 'remote_column': 'users'})

    assert fkey.column == 'user_id'
    assert fkey.remote_table == 'user'
    assert fkey.remote_column == 'users'


def test_foreign_key_from_sqla():
    """ Test that we take a sqlalchemy.ForeignKeyConstraints and
    make the yalchemy foreign key """

    fkey = table_structures.ForeignKey.from_sqla(
        sa.ForeignKeyConstraint(['test_col'], ['other_table.other_col']))

    assert fkey.column == 'test_col'
    assert fkey.remote_table == 'other_table'
    assert fkey.remote_column == 'other_col'


@pytest.mark.parametrize('fkey, expected_metadata', [
    (table_structures.ForeignKey('other_foo', 'other', 'foo'),
     {'column': 'other_foo',
      'remote_table': 'other', 'remote_column': 'foo'}),
    (table_structures.ForeignKey(['other_foo', 'other_bar'], 'other', ['foo', 'bar']),
     {'column': ['other_foo', 'other_bar'],
      'remote_table': 'other', 'remote_column': ['foo', 'bar']}),
])
def test_foreign_key_to_dict(fkey, expected_metadata):
    assert fkey.to_dict() == expected_metadata


def test_foreign_key_to_sqla():
    """ Test that we make the ForeignKeyConstraint correctly in sqlalchemy """

    fkey_obj = table_structures.ForeignKey('test_col', 'other_table', 'other_col')
    fkey = fkey_obj.to_sqla()

    assert isinstance(fkey, sa.ForeignKeyConstraint)
    assert len(fkey.elements) == 1
    assert fkey.column_keys == ['test_col']
    assert fkey.elements[0].target_fullname == 'other_table.other_col'


def test_foreign_key_hasing():
    fkey1 = table_structures.ForeignKey('foo', 'bar', 'baz')
    fkey2 = table_structures.ForeignKey('foo', 'bar', 'baz')
    assert {fkey1: 1}[fkey2] == 1
    assert {fkey1} == {fkey2}
    assert {fkey1, fkey2} == {fkey1}


# INDEXES

@pytest.mark.parametrize('idx, expected_metadata', [
    (table_structures.Index(['col_1']),
     {'columns': ['col_1']}),
    (table_structures.Index(['col_2', 'col_1']),
     {'columns': ['col_1', 'col_2']}),
    (table_structures.Index(['col_1', 'col_2']),
     {'columns': ['col_1', 'col_2']}),
    (table_structures.Index(['col_1', 'col_1']),
     {'columns': ['col_1']}),
])
def test_index_to_dict(idx, expected_metadata):
    assert idx.to_dict() == expected_metadata


def test_index_from_dict():
    """ Test that we get a yalchemy Index from a dict correctly """

    index = table_structures.Index.from_dict(
        {'columns': ['col1', 'col2']})

    assert index.columns == {'col1', 'col2'}


def test_index_from_sqla():
    """ Test that we take a sqlalchemy.Index and make the yalchemy Index """

    index = table_structures.Index.from_sqla(
        sa.Index('some_index', 'a_col', 'another_col'))

    assert index.columns == {'a_col', 'another_col'}


def test_index_to_sqla_unnamed():
    """ Test that we make the sa.Index correctly from a yalchemy Index """

    index_obj = table_structures.Index(columns=['col1', 'col2'])
    index = index_obj.to_sqla(table_name='123')

    assert isinstance(index, sa.Index)
    # this is the correct hash for this table + column names
    assert index.name == 'ix__18122589__123'
    assert set(index.expressions) == {'col1', 'col2'}


def test_index_to_sqla_named():
    """ Test that we make the sa.Index correctly from a yalchemy Index """

    index_obj = table_structures.Index(columns=['col1', 'col2'], name='my_index')
    index = index_obj.to_sqla(table_name='123')

    assert isinstance(index, sa.Index)
    assert index.name == 'my_index'
    assert set(index.expressions) == {'col1', 'col2'}


def test_index_hashing():
    idx1 = table_structures.Index(['col_1', 'col_2'])
    idx2 = table_structures.Index(['col_2', 'col_1'])
    assert {idx1: 1}[idx2] == 1
    assert {idx1} == {idx2}
    assert {idx1, idx2} == {idx1}


def test_index_str_repr():
    idx1 = table_structures.Index(['col_1', 'col_2'])
    assert str(idx1) == "Index(columns={'col_1', 'col_2'})"

    idx2 = table_structures.Index(['col_1', 'col_2'], name='my_fixed_name')
    assert str(idx2) == "Index(columns={'col_1', 'col_2'}, name='my_fixed_name')"


# UNIQUE CONSTRAINTS

@pytest.mark.parametrize('constraint, expected_metadata', [
    (table_structures.UniqueConstraint(['col_1']),
     {'columns': ['col_1']}),
    (table_structures.UniqueConstraint(['col_2', 'col_1']),
     {'columns': ['col_1', 'col_2']}),
    (table_structures.UniqueConstraint(['col_1', 'col_1']),
     {'columns': ['col_1']}),
])
def test_unique_to_dict(constraint, expected_metadata):
    assert constraint.to_dict() == expected_metadata


def test_unique_from_dict():
    """ Test that we get a yalchemy UniqueConstraint from a dict correctly """

    constraint = table_structures.UniqueConstraint.from_dict(
        {'columns': ['col1', 'col2']})

    assert constraint.columns == {'col1', 'col2'}


def test_unique_from_sqla():
    """ Test that we take a sqlalchemy.UniqueConstraint and make the yalchemy UniqueConstraint """

    # unique constraint needs to be bound to a table
    sa_table = sa.Table(
        'test_table',
        sa.MetaData(),
        sa.Column('a_col', sa.Integer, primary_key=True),
        sa.Column('another_col', sa.Text),
        sa.UniqueConstraint('a_col', 'another_col', name='some_constraint'),
        schema='test_schema')
    unique_constraint = next(
        c for c in sa_table.constraints if isinstance(c, sa.UniqueConstraint)
    )  # pragma: no cover

    constraint = table_structures.UniqueConstraint.from_sqla(unique_constraint)

    assert constraint.columns == {'a_col', 'another_col'}


def test_unique_to_sqla_unnamed():
    """ Test that we make the sa.UniqueConstraint correctly from a yalchemy UniqueConstraint """
    constraint_obj = table_structures.UniqueConstraint(columns=['col1', 'col2'])
    constraint = constraint_obj.to_sqla(table_name='123')

    assert isinstance(constraint, sa.UniqueConstraint)
    # this is the correct hash for this table + column names
    assert constraint.name == 'uq__18122589__123'

    # must be bound to a table to verify the resulting columns
    sa_table = sa.Table(  # noqa: F841  # pylint: disable=unused-variable
        'test_table',
        sa.MetaData(),
        sa.Column('col1', sa.Integer),
        sa.Column('col2', sa.Integer),
        constraint,
        schema='test_schema')

    assert {c.name for c in constraint.columns} == {'col1', 'col2'}


def test_unique_to_sqla_named():
    """ Test that we make the sa.UniqueConstraint correctly from a yalchemy UniqueConstraint """
    constraint_obj = table_structures.UniqueConstraint(
        columns=['col1', 'col2'],
        name='my_constraint'
    )
    constraint = constraint_obj.to_sqla(table_name='123')

    assert isinstance(constraint, sa.UniqueConstraint)
    assert constraint.name == 'my_constraint'

    # must be bound to a table to verify the resulting columns
    sa_table = sa.Table(  # noqa: F841  # pylint: disable=unused-variable
        'test_table',
        sa.MetaData(),
        sa.Column('col1', sa.Integer),
        sa.Column('col2', sa.Integer),
        constraint,
        schema='test_schema')

    assert {c.name for c in constraint.columns} == {'col1', 'col2'}


def test_unique_hashing():
    unique1 = table_structures.UniqueConstraint(['col_1', 'col_2'])
    unique2 = table_structures.UniqueConstraint(['col_2', 'col_1'])
    assert {unique1: 1}[unique2] == 1
    assert {unique1} == {unique2}
    assert {unique1, unique2} == {unique1}


def test_unique_str_repr():
    idx1 = table_structures.UniqueConstraint(['col_1', 'col_2'])
    assert str(idx1) == "UniqueConstraint(columns={'col_1', 'col_2'})"

    idx2 = table_structures.UniqueConstraint(['col_1', 'col_2'], name='my_fixed_name')
    assert str(idx2) == "UniqueConstraint(columns={'col_1', 'col_2'}, name='my_fixed_name')"


# CheckConstraint


@pytest.mark.parametrize('constraint, expected_metadata', [
    (table_structures.CheckConstraint('check1', 'col1 > col2'),
     {'name': 'check1', 'check': 'col1 > col2'}),
    (table_structures.CheckConstraint('check2', '((col1 == col2))'),
     {'name': 'check2', 'check': '((col1 == col2))'}),
])
def test_constraint_to_dict(constraint, expected_metadata):
    """ Test that we convert a yalchemy CheckConstraint
    into the proper dict format """
    assert constraint.to_dict() == expected_metadata


def test_constraint_from_dict():
    """ Test that we get a yalchemy CheckConstraint from a dict correctly """

    constraint = table_structures.CheckConstraint.from_dict(
        {'name': 'check1', 'check': 'col1 > col2'})

    assert constraint.name == 'check1'
    assert constraint.check == 'col1 > col2'


def test_constraint_from_sqla(transacted_postgresql_db):
    """ Test that we take a sqlalchemy.Column and make the yalchemy CheckConstraint """

    constraint = table_structures.CheckConstraint.from_sqla(
        sa.CheckConstraint('col1 > col2', name='a_check'))

    assert constraint.name == 'a_check'
    assert constraint.check == 'col1 > col2'

    # test from one without a name
    constraint = table_structures.CheckConstraint.from_sqla(
        sa.CheckConstraint('col1 > col2'))

    assert constraint.name is None
    assert constraint.check == 'col1 > col2'

    # test when sql-alchemy reflection calls the name '_unnamed_'
    constraint = table_structures.CheckConstraint.from_sqla(
        sa.CheckConstraint(
            'col1 > col2',
            name=sa.sql.elements._defer_none_name(value='_unnamed_'),
        )
    )
    assert constraint.name is None
    assert constraint.check == 'col1 > col2'


def test_constraint_to_sqla():
    """ Test that we make the sa.CheckConstraint correctly from a yalchemy CheckConstraint """

    constraint_obj = table_structures.CheckConstraint(name='check1', check='col1 < col2')
    constraint = constraint_obj.to_sqla()

    assert isinstance(constraint, sa.CheckConstraint)
    assert constraint.name == 'check1'
    assert str(constraint.sqltext) == 'col1 < col2'


def test_constraint_hasing():
    con1 = table_structures.CheckConstraint('check1', 'col1 > col2')
    con2 = table_structures.CheckConstraint('check1', 'col1 > col2')
    assert {con1: 1}[con2] == 1
    assert {con1} == {con2}
    assert {con1, con2} == {con1}


# TABLES


def test_table_from_dict():
    """ Test that we build a yalchemy Table from a dict """

    table_dict = {
        'name': 'my_table',
        'schema': 'schema',
        'columns': [
            {'name': 'col1', 'datatype': 'varchar', 'format': [123], 'required': False},
            {'name': 'col2', 'datatype': 'integer', 'required': True},
            {'name': 'col3', 'datatype': 'integer', 'required': True,
             'default': {'value': '-1', 'type': 'expression'}},
        ],
        'foreign_keys': [
            {'column': 'col2', 'remote_table': 'other_table', 'remote_column': 'other_col'}
        ],
        'indexes': [{'columns': ['col1', 'col2']}],
        'unique_constraints': [{'columns': ['col3']}],
        'primary_keys': ['col2', 'col1']
    }
    table = table_structures.Table.from_dict(table_dict)

    assert table.name == 'my_table'
    assert table.schema == 'schema'
    assert table.columns == [
        table_structures.Column(name='col1', datatype='varchar', format_=[123], required=False),
        table_structures.Column(name='col2', datatype='integer', required=True),
        table_structures.Column(name='col3', datatype='integer', required=True,
                                default=table_structures.ColumnDefault(
                                    table_structures.ColumnDefaultType.expression,
                                    '-1')),
    ]
    assert table.foreign_keys == {
        table_structures.ForeignKey(
            column='col2', remote_table='other_table', remote_column='other_col'),
    }
    assert table.indexes == {
        table_structures.Index(columns={'col1', 'col2'})
    }
    assert table.unique_constraints == {
        table_structures.UniqueConstraint(['col3']),
    }
    assert table.primary_keys == {'col1', 'col2'}


def test_table_from_sqla():
    """ Test that we take a SQL Alchemy table and make a Table structure """

    sa_table = sa.Table(
        'test_table',
        sa.MetaData(),
        sa.Column('col1', sa.Integer, primary_key=True),
        sa.Column('col2', sa.Text),
        sa.Index('my_index', 'col1', 'col2'),
        sa.ForeignKeyConstraint(['col1'], ['other_table.other_col']),
        sa.UniqueConstraint('col2'),
        sa.CheckConstraint('col1::text != col2', name='check1'),
        schema='test_schema')

    table = table_structures.Table.from_sqla(sa_table)
    assert table.name == 'test_table'
    assert table.schema == 'test_schema'
    assert table.columns == [
        table_structures.Column(name='col1', datatype='integer', format_=None, required=True),
        table_structures.Column(name='col2', datatype='text', format_=None, required=False),
    ]
    assert table.foreign_keys == {
        table_structures.ForeignKey(
            column='col1', remote_table='other_table', remote_column='other_col'),
    }
    assert table.indexes == {
        table_structures.Index(columns={'col1', 'col2'})
    }
    assert table.primary_keys == {'col1'}
    assert table.unique_constraints == {
        table_structures.UniqueConstraint(['col2'])
    }
    assert table.check_constraints == {
        table_structures.CheckConstraint(
            'check1', 'col1::text != col2')
    }


def test_table_from_sqla_equality_from_to_yaml(transacted_postgresql_db):
    """
    Test that a Table structure made from a reflected SQLAlchemy table is equal to the original.
    Converts the table from and to yaml to ensure it can be serialized properly
    """
    metadata = sa.MetaData(bind=transacted_postgresql_db.connection)

    transacted_postgresql_db.connection.execute('''
        create schema schema;
        create table schema.other_table (
            other_col integer unique
        );
        create sequence schema.my_table_col6_seq increment by 1 no minvalue no maxvalue;
        create table schema.my_table (
            col1 varchar(123),
            col2 integer not null primary key references schema.other_table (other_col),
            col3 integer not null unique,
            col4 timestamp with time zone not null default now(),
            col5 varchar(1) not null default 'Y',
            -- fully defined default sequence
            col6 integer not null default nextval('schema.my_table_col6_seq'::regclass),
            -- default sequence shorthand
            col7 serial
            constraint check1 check ((col1 != 'value')),
            constraint check2 check ((col1 != 'value') and (col2 != 0))
        );
        create index idx ON schema.my_table (col1, col2);
    ''')

    table_dict = {
        'name': 'my_table',
        'schema': 'schema',
        'columns': [
            {'name': 'col1', 'datatype': 'varchar', 'format': [123], 'required': False},
            {'name': 'col2', 'datatype': 'integer', 'required': True},
            {'name': 'col3', 'datatype': 'integer', 'required': True},
            {'name': 'col4', 'datatype': 'timestamptz', 'required': True,
             'default': {'value': 'now()', 'type': 'expression'}},
            {'name': 'col5', 'datatype': 'varchar', 'format': [1], 'required': True,
             # SQLAlchemy includes explicit cast when reflecting plain string defaults
             'default': {'value': "'Y'::character varying", 'type': 'expression'}},
            {'name': 'col6', 'datatype': 'integer', 'required': True,
             'default': {'value': 'schema.my_table_col6_seq', 'type': 'sequence'}},
            {'name': 'col7', 'datatype': 'integer', 'required': True,
             'default': {'value': 'schema.my_table_col7_seq', 'type': 'sequence'}},
        ],
        'foreign_keys': [
            {'column': 'col2', 'remote_table': 'schema.other_table', 'remote_column': 'other_col'}
        ],
        'check_constraints': [
            {'name': 'check1', 'check': "(col1 != 'value')"},
            {'name': 'check2', 'check': "(col1 != 'value') and (col2 != 0)"}
        ],
        'indexes': [{'columns': ['col1', 'col2']}],
        'unique_constraints': [{'columns': ['col3']}],
        'primary_keys': ['col2']
    }
    orig_table = table_structures.Table.from_dict(table_dict)

    reflected_sa = sa.Table('my_table', metadata,
                            schema='schema',
                            autoload=True, autoload_with=transacted_postgresql_db.connection)
    reflected_table_yaml = table_structures.Table.from_sqla(reflected_sa).to_yaml()
    reflected_table = table_structures.Table.from_yaml(reflected_table_yaml)
    assert reflected_table == orig_table


def test_geography_reflection(transacted_postgresql_db):
    """
    Test that a geography column can be properly reflected
    """
    metadata = sa.MetaData(bind=transacted_postgresql_db.connection)

    transacted_postgresql_db.connection.execute('''
        create schema schema;
        create table schema.my_table (
            zip_geocode geography(Point,4326)
        );
    ''')

    table_dict = {
        'name': 'my_table',
        'schema': 'schema',
        'columns': [
            {'name': 'zip_geocode', 'datatype': 'geography', 'format': ['point', 4326]}
        ]
    }
    orig_table = table_structures.Table.from_dict(table_dict)

    reflected_sa = sa.Table('my_table', metadata,
                            schema='schema',
                            autoload=True, autoload_with=transacted_postgresql_db.connection)
    reflected_table_yaml = table_structures.Table.from_sqla(reflected_sa).to_yaml()
    reflected_table = table_structures.Table.from_yaml(reflected_table_yaml)
    assert reflected_table == orig_table


def test_create_geography_column(transacted_postgresql_db):
    """
    Test that a geograph column can be created in a table when converting a dict to sqlalchemy
    """
    metadata = sa.MetaData(bind=transacted_postgresql_db.connection)

    table_dict = {
        'name': 'my_table',
        'schema': 'schema',
        'columns': [
            {'name': 'zip_geocode', 'datatype': 'geography', 'format': ['point', 4326]}
        ]
    }
    table = table_structures.Table.from_dict(table_dict)
    sqla_table = table.to_sqla(metadata)
    transacted_postgresql_db.connection.execute('CREATE SCHEMA schema;')
    sqla_table.create()


def test_table_to_dict():
    """ Test that the whole table dict structure gets
    created successfully """

    table = table_structures.Table(
        name='foo',
        schema='test',
        doc='my doc',
        columns=[
            table_structures.Column(name='id', datatype='integer', required=True, doc='id doc'),
            table_structures.Column(name='other_id', datatype='integer'),
            table_structures.Column(name='another_id', datatype='integer'),
            table_structures.Column(name='source', datatype='uuid', required=True,
                                    default=table_structures.ColumnDefault(
                                        table_structures.ColumnDefaultType.expression,
                                        'uuid_generate_v4()')),
        ],
        primary_keys=['id', 'another_id', 'other_id'],
        foreign_keys=[
            table_structures.ForeignKey('other_id', 'other', 'id'),
        ],
        indexes=[
            table_structures.Index(['other_id']),
            table_structures.Index(['other_id', 'id']),
        ],
        unique_constraints=[
            table_structures.UniqueConstraint(['another_id'], name='unique1'),
        ],
        check_constraints=[
            table_structures.CheckConstraint('check1', 'id != other_id')
        ])
    assert table.to_dict() == {
        'name': 'foo',
        'schema': 'test',
        'doc': 'my doc',
        'columns': [
            {'name': 'id', 'datatype': 'integer', 'required': True, 'doc': 'id doc'},
            {'name': 'other_id', 'datatype': 'integer', 'required': False},
            {'name': 'another_id', 'datatype': 'integer', 'required': False},
            {'name': 'source', 'datatype': 'uuid', 'required': True,
             'default': {'value': 'uuid_generate_v4()', 'type': 'expression'}},
        ],
        'foreign_keys': [
            {'column': 'other_id', 'remote_table': 'other', 'remote_column': 'id'},
        ],
        'indexes': [
            {'columns': ['id', 'other_id']},
            {'columns': ['other_id']},
        ],
        'unique_constraints': [
            {'columns': ['another_id'], 'name': 'unique1'}
        ],
        'primary_keys': ['another_id', 'id', 'other_id'],
        'check_constraints': [{'name': 'check1', 'check': 'id != other_id'}]
    }


def test_table_to_sqla():
    """ Test that we tae a full table_structures.Table """

    table_obj = table_structures.Table(
        name='a_table',
        schema='a_schema',
        columns=[
            table_structures.Column(name='col1', datatype='varchar', format_=[123],
                                    required=False),
            table_structures.Column(name='col2', datatype='integer', required=True),
            table_structures.Column(name='col3', datatype='integer'),
            table_structures.Column(name='col4', datatype='timestamptz', required=True,
                                    default=table_structures.ColumnDefault(
                                        table_structures.ColumnDefaultType.expression,
                                        'now()')),
            table_structures.Column(name='col5', datatype='bigint', required=True,
                                    default=table_structures.ColumnDefault(
                                        table_structures.ColumnDefaultType.sequence,
                                        'a_schema.a_table_col5_seq')),
        ],
        foreign_keys=[table_structures.ForeignKey('col2', 'other_table', 'other_col')],
        indexes=[table_structures.Index(['col1'])],
        primary_keys=['col2'],
        unique_constraints=[table_structures.UniqueConstraint(['col3'], name='uq_col3')],
        check_constraints=[table_structures.CheckConstraint('check1', 'col1::text != col2')])

    meta = sa.MetaData()
    sa_table = table_obj.to_sqla(metadata=meta)

    assert sa_table.name == 'a_table'
    assert sa_table.schema == 'a_schema'
    assert {col.name for col in sa_table.c} == {'col1', 'col2', 'col3', 'col4', 'col5'}
    assert [i.constraint.columns.keys() for i in sa_table.foreign_keys] == [['col2']]
    assert [j.name for i in sa_table.indexes for j in i.expressions] == ['col1']
    assert [(c.name, c.sqltext) for c in sa_table.constraints if isinstance(c, sa.CheckConstraint)]
    assert [(c.name, [col.name for col in c.columns])
            for c in sa_table.constraints if isinstance(c, sa.UniqueConstraint)] == \
           [('uq_col3', ['col3'])]
    assert sa_table.c.col2.primary_key
    assert sa_table.c.col4.server_default
    assert str(sa_table.c.col4.server_default.arg) == 'now()'
    assert sa_table.c.col5.server_default
    assert isinstance(sa_table.c.col5.server_default, sa.DefaultClause)
    assert isinstance(sa_table.c.col5.server_default.arg, sa_func.next_value)
    assert sa_table.c.col5.server_default.arg.sequence.name == 'a_table_col5_seq'
    assert sa_table.c.col5.server_default.arg.sequence.schema == 'a_schema'
    assert sa_table.metadata == meta  # assert it's the meta I gave it

    # test without indexes
    sa_table_no_indexes = table_obj.to_sqla(metadata=sa.MetaData(), include_indexes=False)
    assert [j.name for i in sa_table_no_indexes.indexes for j in i.expressions] == []


# pylint: disable=pointless-statement,expression-not-assigned
def test_table_or():
    table = table_structures.Table(
        name='foo',
        schema='test',
        columns=[
            table_structures.Column(name='id', datatype='integer', required=True),
            table_structures.Column(name='other_id', datatype='integer'),
            table_structures.Column(name='another_id', datatype='integer'),
        ],
        primary_keys=['id'],
        foreign_keys=[
            table_structures.ForeignKey('other_id', 'other', 'id'),
        ],
        indexes=[
            table_structures.Index(['other_id']),
        ],
        unique_constraints=[
            table_structures.UniqueConstraint('other_id'),
        ],
        check_constraints=[
            table_structures.CheckConstraint('check1', 'id != other_id'),
        ])
    assert (table | None) == table
    assert (None | table) == table

    other = copy.deepcopy(table)
    other.columns = other.columns[:-1] + [
        table_structures.Column(name='creation_date', datatype='date')]
    merged = table | other
    merged_columns = {col.name for col in merged.columns}
    assert merged_columns == {'id', 'other_id', 'another_id', 'creation_date'}

    other = copy.deepcopy(table)
    other.indexes = set()
    merged = table | other
    assert merged.indexes == table.indexes

    other = copy.deepcopy(table)
    other.foreign_keys = set()
    merged = table | other
    assert not merged.foreign_keys

    other = copy.deepcopy(table)
    other.foreign_keys = {table_structures.ForeignKey('other_id', 'some_other_table', 'id')}
    merged = table | other
    assert not merged.foreign_keys

    other = copy.deepcopy(table)
    other.unique_constraints = {table_structures.UniqueConstraint('another_id')}
    merged = table | other
    assert not merged.unique_constraints

    other = copy.deepcopy(table)
    other.check_constraints = {table_structures.CheckConstraint('check2', 'other_id != 1')}
    merged = table | other
    assert not merged.check_constraints

    other = copy.deepcopy(table)
    other.columns[0].datatype = 'float'
    with pytest.raises(table_structures.MergeError):
        table | other

    other = copy.deepcopy(table)
    other.primary_keys = ['other_id']
    with pytest.raises(table_structures.MergeError):
        table | other

    other = copy.deepcopy(table)
    other.name = 'bar'
    with pytest.raises(table_structures.MergeError):
        table | other

    with pytest.raises(TypeError):
        table | object()


def test_no_column_given():
    """ Test that we raise a NoDataType when no data type
    is given in the spec. """

    table_metadata = {
        'name': 'pktable',
        'schema': 'test_schema',
        'columns': [
            {'name': 'id'},  # missing datatype
            {'name': 'somestr', 'datatype': 'text'},
        ],
        'primary_keys': 'id',
    }
    with pytest.raises(table_structures.NoDataType):
        table_structures.Table.from_dict(table_metadata)


def test_create_table_primary_key(transacted_postgresql_db):
    """ Test that we create the primary keys correctly """

    table_metadata = {
        'name': 'pktable',
        'schema': 'test_schema',
        'columns': [
            {'name': 'id', 'datatype': 'integer'},
            {'name': 'somestr', 'datatype': 'text'},
        ],
        'primary_keys': ['id'],
    }
    sa_meta = sa.MetaData()
    table = table_structures.Table.from_dict(table_metadata)
    transacted_postgresql_db.connection.execute('CREATE SCHEMA test_schema')
    sa_table = table.to_sqla(metadata=sa_meta)
    sa_table.create(transacted_postgresql_db.connection)
    assert sa_table.c.id.primary_key


def test_create_table_primary_key_multiple(transacted_postgresql_db):
    table_metadata = {
        'name': 'pktable',
        'schema': 'test_schema',
        'columns': [
            {'name': 'composite_key_1', 'datatype': 'text'},
            {'name': 'composite_key_2', 'datatype': 'text'},
        ],
        'primary_keys': ['composite_key_1', 'composite_key_2'],
    }
    sa_meta = sa.MetaData()
    table = table_structures.Table.from_dict(table_metadata)
    transacted_postgresql_db.connection.execute('CREATE SCHEMA test_schema')
    sa_table = table.to_sqla(metadata=sa_meta)
    sa_table.create(transacted_postgresql_db.connection)
    assert sa_table.c.composite_key_1.primary_key
    assert sa_table.c.composite_key_2.primary_key


def test_create_table_required_column(transacted_postgresql_db):
    table_metadata = {
        'name': 'reqcoltable',
        'schema': 'test_schema',
        'columns': [
            {'name': 'required', 'datatype': 'text', 'required': True},
            {'name': 'optional', 'datatype': 'text', 'required': False},
            {'name': 'other', 'datatype': 'text'},
        ],
    }
    sa_meta = sa.MetaData()
    table = table_structures.Table.from_dict(table_metadata)
    transacted_postgresql_db.connection.execute('CREATE SCHEMA test_schema')
    sa_table = table.to_sqla(metadata=sa_meta)
    sa_table.create(transacted_postgresql_db.connection)
    assert not sa_table.c.required.nullable
    assert sa_table.c.optional.nullable
    assert sa_table.c.other.nullable


# TABLE SET

def test_tableset_from_dict():
    """ Test that we pull up a tableset correctly """

    test_dict = {
        'tables': [
            {'name': 'foo', 'schema': 'test', 'columns': []},
            {'name': 'bar', 'schema': 'test', 'columns': []},
        ],
    }
    table_set = table_structures.TableSet.from_dict(test_dict)
    assert len(table_set.tables) == 2
    assert {t.name for t in table_set.tables} == {'foo', 'bar'}


def test_tableset_from_sqla():
    """ Test that we can take a list of sqlalchemy tables and
    return a table set containing table_structures.Table for
    each table """

    table_1 = sa.Table('my_table1', sa.MetaData(), schema='test')
    table_2 = sa.Table('my_table2', sa.MetaData(), schema='test')
    table_set = table_structures.TableSet.from_sqla([table_1, table_2])
    assert table_set.to_dict() == {
        'tables': [
            {'name': 'my_table1', 'schema': 'test', 'columns': []},
            {'name': 'my_table2', 'schema': 'test', 'columns': []},
        ],
    }


def test_tableset_to_dict():
    """ Test that we create the dict for thet tableset """

    table_set = table_structures.TableSet(tables=[
        table_structures.Table(name='foo', schema='test'),
        table_structures.Table(name='bar', schema='test'),
    ])
    assert table_set.to_dict() == {
        'tables': [
            {'name': 'foo', 'schema': 'test', 'columns': []},
            {'name': 'bar', 'schema': 'test', 'columns': []},
        ],
    }
    assert (table_set | None) == table_set
    assert (None | table_set) == table_set
    assert (table_set | table_set) == table_set


def test_tableset_to_sqla():
    """ Test that we take a tableset and return a list of sqlalchemy tables """

    table_set = table_structures.TableSet(tables=[
        table_structures.Table(name='foo', schema='test'),
        table_structures.Table(name='bar', schema='test'),
    ])
    sa_tables = table_set.to_sqla()

    assert all(isinstance(t, sa.Table) for t in sa_tables)
    assert {t.name for t in sa_tables} == {'foo', 'bar'}


def test_tableset_unique_constraints():
    """ Test that we properly add unique constraints to foreign
    key targets when calling to_sqla() """

    table_set = table_structures.TableSet.from_dict(
        {
            'tables': [{
                'name': 'one',
                'schema': 'test_schema',
                'columns': [
                    {'name': 'id', 'datatype': 'integer'},
                    {'name': 'somestr', 'datatype': 'text'},
                ],
            }, {
                'name': 'two',
                'schema': 'test_schema',
                'columns': [
                    {'name': 'one_id', 'datatype': 'integer'},
                    {'name': 'otherstr', 'datatype': 'text'},
                ],
                'foreign_keys': [{
                    'column': 'one_id',
                    'remote_table': 'test_schema.one',
                    'remote_column': 'id',
                }],
                'indexes': [{'columns': ['one_id']}],
            }],
        }
    )
    # make sure it's not there if we don't want it
    tables = table_set.to_sqla(add_unique_constraints=False)
    table_one = [i for i in tables if i.name == 'one'][0]
    assert [i for i in table_one.constraints
            if isinstance(i, sa.UniqueConstraint)] == []

    # make sure unique constraint is there by default
    tables = table_set.to_sqla(metadata=sa.MetaData())
    table_one = [i for i in tables if i.name == 'one'][0]
    table_one_unique_constraint = [
        i for i in table_one.constraints if isinstance(i, sa.UniqueConstraint)
    ][0]
    assert table_one_unique_constraint.columns.keys() == ['id']
