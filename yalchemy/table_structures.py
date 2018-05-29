"""Common table abstractions and utilities."""
# pylint: disable=arguments-differ,too-many-lines
import abc
import collections
import copy
import enum
import functools
import hashlib
import re

import sqlalchemy as sa
import sqlalchemy.sql.elements as sa_elements
import sqlalchemy.sql.functions as sa_func
import sqlalchemy.dialects.postgresql as sa_pg
import yaml

from yalchemy import col_utils, pretty_yaml, sqla_utils

# TODO: validation - duplicate names, invalid foreign keys, etc.


class Error(Exception):
    """The base exception class for this module."""


class MergeError(Error):
    """Raised when trying to merge two incompatible table abstractions."""


class NoDataType(Error):
    """ Raised when there is no data type given for a column """


class InvalidColumnDefault(Error):
    """ Raised when an invalid column default is specified """


class _ComparableMixin:
    """Mixin to provide common comparator functionality."""
    __slots__ = ()

    def _as_tuple(self):
        return tuple(getattr(self, attr) for attr in self.__slots__)

    def _comparable(self, other):
        return all(hasattr(other, attr) for attr in self.__slots__)

    def __eq__(self, other):
        if not self._comparable(other):  # pragma: no cover
            return NotImplemented
        else:
            return self._as_tuple() == other._as_tuple()

    def __ror__(self, other):
        """Implement reverse or to handle `None | object => object`."""
        if other is None:
            return self
        else:  # pragma: no cover
            return NotImplemented


try:
    DefaultYamlLoader = yaml.CSafeLoader
except AttributeError:  # pragma: no cover
    DefaultYamlLoader = yaml.SafeLoader


class Yalchemy(metaclass=abc.ABCMeta):
    """ The base yalchemy object that defines the interface for serialization """

    @abc.abstractmethod
    def _to_dict(self):
        """ Converts a yalchemy object to a dictionary """

    def to_dict(self):
        """ Converts a yalchemy object to a dictionary.

        .. note::

            Wrapper around _to_dict that will order the _to_dict
            returned dict by the __slots__ order in an OrderedDict.
            Please remember to override ``_to_dict`` and not ``to_dict``
            when subclassing yalchemy.
        """
        unordered_dict = self._to_dict()
        ordered_dict = collections.OrderedDict()
        for key in self.__slots__:
            if key in unordered_dict:
                ordered_dict[key] = unordered_dict.pop(key)
        assert not unordered_dict
        return ordered_dict

    @abc.abstractclassmethod
    def from_dict(cls, dict_obj):
        """ Constructs a yalchemy object from a dictionary """

    @abc.abstractmethod
    def to_sqla(self, **kwargs):
        """ Converts a yalchemy object to a sqlalchemy object

        Args:
            kwargs: Keyword arguments specific to the yalchemy object
                being created. Some objects need special parameters for their
                construction (e.g. sqlalchemy MetaData)
        """

    @abc.abstractclassmethod
    def from_sqla(cls, sqla_obj, **kwargs):
        """ Constructs a yalchemy object from a sqlalchemy object

        Args:
            sqla_obj: The sqlalchemy object
            kwargs: Keyword arguments specific to the yalchemy object
                being created. Some objects need special parameters for their
                construction (e.g. sqlalchemy MetaData)
        """

    def to_yaml(self):
        """ Converts a yalchemy object to a yaml string """
        return yaml.dump(self.to_dict(), Dumper=pretty_yaml.PrettyYalchemyDumper)

    @classmethod
    def from_yaml(cls, yaml_str, loader_factory=None):
        """ Loads a yalchemy object from a yaml string

        Args:
            yaml (str): The yaml string
            loader_factory (function(stream)): (optional) constructs a custom PyYaml loader.
                If not provided and libyaml is installed, it will default to CSafeLoader.
                If not provided and libyaml is not installed, it will default to SafeLoader.
        """
        loader_factory = loader_factory or DefaultYamlLoader
        loader = loader_factory(yaml_str)

        try:
            dict_obj = loader.get_single_data()
        finally:
            loader.dispose()

        if not isinstance(dict_obj, dict):  # pragma: no cover
            raise ValueError('from_yaml only supports loading yaml dictionaries')

        return cls.from_dict(dict_obj)

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for key in self.__slots__:
            setattr(result, key, copy.deepcopy(getattr(self, key), memo))
        return result


class ColumnDefaultType(enum.Enum):
    sequence = 'sequence'
    expression = 'expression'


class ColumnDefault(Yalchemy, _ComparableMixin):
    __slots__ = ('type', 'value')
    REGEX_SEQUENCE_EXPRESSION = re.compile(
        r'^nextval\((?P<sequence>[\w\.\'\"\\]+)(?:::regclass)?\)$'
    )

    def __init__(self, type_, value):
        assert isinstance(type_, ColumnDefaultType)
        assert isinstance(value, str)

        if type_ == ColumnDefaultType.sequence and \
                not col_utils.is_schema_qualified(value):
            raise InvalidColumnDefault('Schema must be specified for sequence types')

        self.type = type_
        self.value = col_utils.unquote_sql_string(value)

    @classmethod
    def from_dict(cls, dict_obj):
        """ Creates a yalchemy ColumnDefault from a dictionary.

        This is for SQLAlchemy database (server) defaults
        http://docs.sqlalchemy.org/en/latest/core/metadata.html#sqlalchemy.schema.Column.params.server_default
        https://www.postgresql.org/docs/current/static/ddl-default.html

        The dictionary has the following specification::

        {
            # The type of the default (expression or sequence)
            'type': string(required),

            # DDL clause for default
            #
            # examples:
            #   'NOW()', 'UUID_GENERATE_V4()', ... for functions
            #   'schema.sequence_name' for sequences (must include schema)
            #   '1', 'foo' for quoted_string (includes numeric values)
            'value': str(required)
        }

        """
        return cls(ColumnDefaultType(dict_obj['type']), dict_obj['value'])

    @classmethod
    def from_sqla(cls, sqla_obj):
        # extract object from default clause
        if isinstance(sqla_obj, sa.DefaultClause):
            sqla_obj = sqla_obj.arg

        # extract sequence object from a next_value() clause
        if isinstance(sqla_obj, sa_func.next_value):
            sqla_obj = sqla_obj.sequence

        # convert SQLAlchemy object to appropriate ColumnDefaultType
        if isinstance(sqla_obj, sa.Sequence):
            default_type = ColumnDefaultType.sequence
            if not sqla_obj.schema:
                raise InvalidColumnDefault(
                    'Sequence {} must be qualified with a schema'.format(str(sqla_obj)),
                )
            value = '{}.{}'.format(sqla_obj.schema, str(sqla_obj.name))
        elif isinstance(sqla_obj, sa_elements.TextClause):
            # determine if the text clause is actually a sequence and extract it
            sequence_match = cls.REGEX_SEQUENCE_EXPRESSION.match(sqla_obj.text)
            if sequence_match:
                default_type = ColumnDefaultType.sequence
                value = col_utils.unquote_sql_string(sequence_match.group('sequence'))
            else:
                default_type = ColumnDefaultType.expression
                value = sqla_obj.text
        elif isinstance(sqla_obj, str):
            default_type = ColumnDefaultType.expression
            value = col_utils.unquote_sql_string(sqla_obj)
        else:
            raise TypeError(
                'Server default object must be a sequence, string or SQLAlchemy TextClause')

        return cls(default_type, value)

    def _to_dict(self):
        return {
            'type': self.type.value,
            'value': self.value,
        }

    def to_sqla(self):
        if self.type == ColumnDefaultType.sequence:
            sequence_schema, sequence_name = self.value.split('.')
            return sa.Sequence(sequence_name, schema=sequence_schema)
        else:
            return sa.text(self.value)

    def __or__(self, other):
        if not (self.type == other.type and
                self.value == other.value):
            raise MergeError(
                'Cannot merge ColumnDefaults: {0!r}, {1!r}'.format(self, other))
        return type(self)(self.type, self.value)

    def __copy__(self):
        return ColumnDefault(self.type, self.value)

    def __repr__(self):
        return ('ColumnDefault(type={s.type!r}, '
                'value={s.value!r})'.format(s=self))


class Column(Yalchemy, _ComparableMixin):
    """ A yalchemy Column that can be converted to a sqlalchemy Column """
    __slots__ = ('name', 'datatype', 'format', 'required', 'default', 'doc')

    def __init__(self, name, datatype, format_=None, required=False, default=None, doc=None):
        self.name = str(name)
        self.datatype = col_utils.clean_datatype(datatype)
        self.format = format_
        self.required = required
        self.default = default

        # doc isn't read from sqlalchemy objects or written to them
        # since it's not supported yet (will be in version 1.2)
        self.doc = doc

    @classmethod
    def from_dict(cls, dict_obj):
        """ Creates a yalchemy Column from a dictionary.

        The dictionary has the following specification::

            {
                # The name of the column
                'name': str(required),

                # The datatype. Can be any of the postgres datatypes listed
                # at https://www.postgresql.org/docs/current/static/datatype.html#DATATYPE-TABLE
                'datatype': str(required),

                # The format of the datatype. This is an array of arguments that is passed
                # into the datatype. For example, a format of [255] for a varchar type would
                # create a varchar(255) column datatype
                'format': list(default=[]),

                # If the datatype is required. If False, it will be null
                'required': bool(default=False),

                # The database server-side default for the column. Column defaults follow the
                # specification provided in the `ColumnDefault.from_dict` documentation
                'default': dict(optional)
            }

        """
        dict_obj = copy.copy(dict_obj)
        if 'datatype' not in dict_obj:
            raise NoDataType('No datatype given for col: %s' % dict_obj.get('name'))
        dict_obj['format_'] = dict_obj.pop('format', None)
        if 'default' in dict_obj:
            dict_obj['default'] = ColumnDefault.from_dict(dict_obj['default'])
        else:
            dict_obj['default'] = None
        return cls(**dict_obj)

    @classmethod
    def from_sqla(cls, sqla_obj):
        """ Create a yalchemy Column using a sqlalchemy Column

        Args:
            sqla_obj (Column): The sqlalchemy column
        """
        col_type, col_format = cls._get_col_type(sqla_obj.type)
        # Column formats default to [] with sqlalchemy, however, yalchemy defaults them to None
        col_format = None if col_format == [] else col_format
        if sqla_obj.server_default:
            col_default = ColumnDefault.from_sqla(sqla_obj.server_default)
        else:
            col_default = None

        return cls(str(sqla_obj.name), col_type, col_format,
                   required=not sqla_obj.nullable, default=col_default)

    def _to_dict(self):
        """ Converts the yalchemy Column to a dictionary """

        metadata = {
            'name': self.name,
            'datatype': self.datatype,
            'required': self.required,
        }

        if self.doc:
            metadata['doc'] = self.doc
        if self.format:
            metadata['format'] = self.format
        if self.default:
            metadata['default'] = self.default.to_dict()

        return metadata

    def to_sqla(self, is_primary):  # pylint: disable=arguments-differ
        """ Converts the yalchemy Column to a sqlalchemy Column

        Args:
            is_primary (bool): ``True`` if the column is a primary key
        """
        sa_type = sqla_utils.sa_type_from_str(self.datatype, self.format)
        column_args = [self.name, sa_type]

        if self.default:
            default_sqla_obj = self.default.to_sqla()
            # sequences
            if isinstance(default_sqla_obj, sa.Sequence):
                column_args.append(default_sqla_obj)
                server_default = default_sqla_obj.next_value()
            else:
                server_default = default_sqla_obj
        else:
            server_default = None

        return sa.Column(
            *column_args, key=self.name, primary_key=is_primary,
            nullable=not self.required, server_default=server_default)

    @staticmethod
    def _get_col_type(sqlalchemy_type):
        """ Use the sqlalchemy type and compile it into
        it's ddl. We then lowercase it and make the spaces underscores
        because that looks prettier in the yaml. """
        clean_value = sqlalchemy_type.compile(sa_pg.dialect()).lower()
        # get's the raw type and any args it takes
        # for example it splits varchar(255) into varchar and 255
        matches = re.match(r'^([\w ]*)(\((.*)\))?(\[\])?$', clean_value)
        col_type = matches.group(1) + (matches.group(4) or '')
        if matches.group(3):
            col_format = [int(i) if i != 'point' else i for i in matches.group(3).split(',')]
        else:
            col_format = []
        return col_type.replace(' ', '_'), col_format

    def __or__(self, other):
        # TODO(d-felix): Support merging of unequal datatypes, e.g. date and datetime.
        if other is None:
            return self
        elif not self._comparable(other):  # pragma: no cover
            return NotImplemented

        if not (self.name == other.name and
                self.datatype == other.datatype and
                self.format == other.format and
                self.default == other.default and
                self.doc == other.doc):
            raise MergeError(
                'Cannot merge Columns: {0!r}, {1!r}'.format(self, other))

        return type(self)(
            name=self.name,
            datatype=self.datatype,
            format_=self.format,
            required=self.required and other.required,
            default=self.default,
            doc=self.doc)

    def __copy__(self):
        return Column(self.name, self.datatype,
                      format_=self.format, required=self.required,
                      default=self.default, doc=self.doc)

    def __repr__(self):
        return ('Column(name={s.name!r}, datatype={s.datatype!r}, '
                'format={s.format!r}, required={s.required!r}, doc={s.doc!r}, '
                'default={s.default!r})'.format(s=self))


@functools.total_ordering  # make ForeignKey sortable via __eq__ and __lt__
class ForeignKey(Yalchemy, _ComparableMixin):
    """ A yalchemy ForeignKey that can be converted to a sqlalchemy ForeignKeyIndex """
    __slots__ = ('column', 'remote_table', 'remote_column')

    def __init__(self, column, remote_table, remote_column):
        if isinstance(column, (list, tuple)):
            self.column = [str(col) for col in column]
        else:
            self.column = str(column)
        self.remote_table = remote_table
        self.remote_column = remote_column

    @classmethod
    def from_dict(cls, dict_obj):
        """ Creates a yalchemy ForeignKey from a dictionary.

        The dictionary has the following specification::

            {
                # The name of the column
                'column': str(required),

                # The name of the remote table
                'remote_table': str(required),

                # The name of the remote column
                'remote_column': str(required),
            }

        .. note:: The ``column`` and ``remote_column`` arguments can
            be list of strings in the case of creating foreign keys on
            combinations of columns.
        """
        return cls(**dict_obj)

    @classmethod
    def from_sqla(cls, sqla_obj):
        """ Create a yalchemy ForeignKey from a sqlalchemy ForeignKeyConstraint

        Arguments:
            sqla_obj: The sqlalchemy ForeignKeyConstraint object.
        """

        assert len(sqla_obj.column_keys) == 1
        assert len(sqla_obj.elements) == 1

        target_table, target_col = sqla_obj.elements[0].target_fullname.rsplit('.', 1)
        return cls(sqla_obj.column_keys[0], target_table, target_col)

    def _to_dict(self):
        """ Converts the yalchemy Foreignkey to a dictionary """
        return {
            'column': self.column,
            'remote_table': self.remote_table,
            'remote_column': self.remote_column,
        }

    def to_sqla(self):  # pylint: disable=arguments-differ
        """ Converts the yalchemy ForeignKey to a sqlalchemy ForeignKeyConstraint """

        to_column = self.remote_table + '.' + self.remote_column
        return sa.ForeignKeyConstraint(
            [self.column], [to_column], deferrable=True, initially='IMMEDIATE')

    def __lt__(self, other):  # pragma: no cover
        if not self._comparable(other):
            return NotImplemented
        return self._as_tuple() < other._as_tuple()  # pylint: disable=protected-access

    def __hash__(self):
        return hash(self._as_tuple())

    def __copy__(self):  # pragma: no cover
        return ForeignKey(self.column, self.remote_table, self.remote_column)

    def __repr__(self):  # pragma: no cover
        return ('ForeignKey(column={s.column!r}, remote_table={s.remote_table!r}, '
                'remote_column={s.remote_column!r})'.format(s=self))


@functools.total_ordering  # make sortable via __eq__ and __lt__
class _ColumnCollection(Yalchemy, _ComparableMixin):
    """ Base class for any Yalchemy object that comprises a column collection """
    __slots__ = ('name', 'columns',)
    HASHED_NAME_PREFIX = None

    def __init__(self, columns, name=None):
        self.columns = set(columns)
        self.name = name

    @classmethod
    def from_dict(cls, dict_obj):
        """ Creates a yalchemy column collection from a dictionary.

        The dictionary has the following specification::

            {
                # The list of column names. If multiple are
                # provided, a multidimensional index will be created
                'columns': list[str](required),

                # A fixed name for this object
                # (if not specified, will automatically generate a hashed name)
                'name': str(optional)
            }
        """
        return cls(dict_obj['columns'], name=dict_obj.get('name'))

    def _to_dict(self):
        """ Converts the column collection to a dictionary """

        result = {'columns': sorted(self.columns)}

        # include name only if it was explicitly set
        if self.name:
            result['name'] = self.name

        return result

    def to_sqla(self, table_name):  # pylint: disable=arguments-differ
        """ Converts the yalchemy column collection to a sqlalchemy object.

        Args:
            table_name (str): The name of the table to which the sqlalchemy object is applied
        """
        return self._make_sqla_object(
            self.name if self.name else self._create_hashed_name(table_name)
        )

    def _create_hashed_name(self, table_name):
        """ Create the hashed name of this collection object for the table given the list
        of columns and the table name """

        params_str = table_name + ':' + ','.join(sorted(self.columns))
        hash_value = hashlib.md5(params_str.encode('utf-8')).hexdigest()[0:8]

        return '{prefix}__{hash_value}__{table_name}'.format(
            prefix=self.HASHED_NAME_PREFIX,
            hash_value=hash_value,
            table_name=table_name
        )[0:63]

    @abc.abstractmethod
    def _make_sqla_object(self, name):
        """ Constructs the sqlalchemy object associated with this yalchemy object """

    def _as_tuple(self):
        """Convert to tuple for ease of comparison."""
        return tuple(sorted(self.columns))

    def __lt__(self, other):
        if not self._comparable(other):  # pragma: no cover
            return NotImplemented
        return self._as_tuple() < other._as_tuple()  # pylint: disable=protected-access

    def __hash__(self):
        return hash(self._as_tuple())

    def __copy__(self):  # pragma: no cover
        cls = self.__class__
        return cls(self.columns, name=self.name)

    def __repr__(self):
        name_detail = ', name={!r}'.format(self.name) if self.name else ''
        # force set display to be consistently sorted
        sorted_set_detail = '{' + ', '.join(sorted('{!r}'.format(c) for c in self.columns)) + '}'
        return '{}(columns={}{})'.format(self.__class__.__name__, sorted_set_detail, name_detail)


class Index(_ColumnCollection):
    """ A yalchemy Index that can be converted to a sqlalchemy Index """
    HASHED_NAME_PREFIX = 'ix'

    def _make_sqla_object(self, name):
        return sa.Index(name, *self.columns)

    @classmethod
    def from_sqla(cls, sqla_obj):
        """ Create a yalchemy Index from a sqlalchemy Index """
        return cls(
            columns=[str(c.name if isinstance(c, sa.Column) else str(c))
                     for c in sqla_obj.expressions])


class UniqueConstraint(_ColumnCollection):
    """ A yalchemy UniqueConstraint that can be converted to a sqlalchemy UniqueConstraint """
    HASHED_NAME_PREFIX = 'uq'

    @classmethod
    def from_sqla(cls, sqla_obj):
        """ Create a yalchemy UniqueConsraint from a sqlalchemy UniqueConstraint """
        return cls(
            columns=[str(c.name) for c in sqla_obj.columns])

    def _make_sqla_object(self, name):
        return sa.UniqueConstraint(*self.columns, name=name)


@functools.total_ordering  # make Check constraint sortable via __eq__ and __lt__
class CheckConstraint(Yalchemy, _ComparableMixin):
    """ A yalchemy CheckConstraint that can be converted to a sqlalchemy CheckConstraint

    .. note::

        While other yalchemy objects perform equality comparisons on all attributes
        of their classes, CheckConstraint does not do comparison on the 'check' attribute.
        This is because Postgres may format the check value when storing it.
    """
    __slots__ = ('name', 'check')

    def __init__(self, name, check):
        self.name = name
        self.check = check

    @classmethod
    def from_dict(cls, dict_obj):
        """ Creates a yalchemy CheckConstraint from a dictionary.

        The dictionary has the following specification::

            {
                # The check is the string of the check we want to
                # have on the constraint. It should be verbatium
                # what the check would be in SQL
                'name': str(required),
                'check': str(required),
            }
        """
        return cls(name=dict_obj['name'], check=dict_obj['check'])

    @classmethod
    def from_sqla(cls, sqla_obj):
        """ Create a yalchemy CheckConstraint from a sqlalchemy CheckConstraint """

        # handles a weird case where sqlalchemy names check constraints
        # without a name with this name instead of having it be None
        if sqla_obj.name is None or str(sqla_obj.name) == '_unnamed_':
            name = None
        else:
            name = str(sqla_obj.name)
        return cls(name, str(sqla_obj.sqltext))

    def _to_dict(self):
        """ Converts the yalchemy CheckConstraint to a dictionary """
        return {'name': self.name, 'check': self.check}

    def to_sqla(self):  # pylint: disable=arguments-differ
        """ Converts the yalchemy CheckConstraint to a sqlalchemy CheckConstraint. """

        return sa.CheckConstraint(self.check, name=self.name)

    def _as_tuple(self):
        """Convert to tuple for ease of comparison.

        .. note::

            The "check" parameter has been removed from comparison since it can be
            reflected differently from postgres once it is stored. In other words, if
            check constraints have the same name, they are considered identical.
        """
        return (self.name,)

    def __lt__(self, other):  # pragma: no cover
        if not self._comparable(other):
            return NotImplemented
        return self._as_tuple() < other._as_tuple()  # pylint: disable=protected-access

    def __hash__(self):
        return hash(self._as_tuple())

    def __copy__(self):  # pragma: no cover
        return CheckConstraint(self.name, self.check)

    def __repr__(self):  # pragma: no cover
        return 'CheckConstraint(name={s.name!r}, check={s.check!r})'.format(s=self)


class Table(Yalchemy, _ComparableMixin):  # pylint: disable=too-many-instance-attributes
    """ A yalchemy Table that can be converted to a sqlalchemy Table """
    __slots__ = ('name', 'schema', 'columns', 'primary_keys', 'foreign_keys', 'indexes',
                 'unique_constraints', 'check_constraints', 'doc')

    def __init__(self, name, schema, columns=None, foreign_keys=None,
                 primary_keys=None, indexes=None, check_constraints=None, unique_constraints=None,
                 doc=None):
        self.name = str(name)
        self.schema = str(schema)
        self.columns = columns or ()
        self.foreign_keys = set(foreign_keys or ())
        self.indexes = set(indexes or ())
        self.primary_keys = {str(key) for key in primary_keys or ()}
        self.check_constraints = set(check_constraints or ())
        self.unique_constraints = set(unique_constraints or ())
        self.doc = doc

    @property
    def full_name(self):
        """ Get the full name of the table along with the schema name """
        return self.schema + '.' + self.name

    @classmethod
    def from_dict(cls, dict_obj):
        """ Creates a yalchemy Table from a dictionary.

        The dictionary has the following specification::

            {
                # The table name
                'name': str(required),

                # The schema
                'schema': str(required),

                # The list of table column dictioniaries. Column dictionaries
                # follow the specification provided in the `Column.from_dict` documentation
                'columns': list[dict](optional),

                # The list of column foreign key dictionaries. Foreign keys follow the
                # specification provided in the `ForeignKey.from_dict` documentation
                'foreign_keys': list[dict](optional),

                # The list of index dictionaries. Indexes follow the
                # specification provided in the `Index.from_dict` documentation
                'indexes': list[dict](optional),

                # The list of column names (as strings) that are primary keys
                'primary_keys': list[str](optional),

                # The list of unique constraints.  Unique constraints follow the
                # specification provided in the `UniqueConstraint.from_dict` documentation

                # The list of check constraints.  Check constraints follow the
                # specification provided in the `CheckConstraint.from_dict` documentation
                'check_constraints': list[dict](optional)

                # Documentation for the table. Not read from sqlalchemy objs
                # or written to them until SA version 1.2
                'doc': str(optional)
            }

        A full example of a table looks like this::

            {
                'name': 'my_table',
                'schema': 'schema',
                'doc': 'Some document string'
                'columns': [
                    {'name': 'col1', 'datatype': 'varchar', 'format': [123], 'required': False},
                    {'name': 'col2', 'datatype': 'integer', 'required': True,
                     'doc': 'col2 is a good column'},
                ],
                'foreign_keys': [
                    {'column': 'col2', 'remote_table': 'other_table', 'remote_column': 'other_col'}
                ],
                'indexes': [{'columns': ['col1', 'col2']}],
                'unique_constraints': [{'name': 'my_unique_constraint', 'columns': ['col2']}],
                'check_constraints': [{'name': 'my_check', 'check': 'char_length(col1) = col2'}]
                'primary_keys': ['col2']
            }
        """
        dict_obj = copy.copy(dict_obj)
        dict_obj['columns'] = [
            Column.from_dict(c) for c in dict_obj.get('columns', [])
        ]
        dict_obj['foreign_keys'] = [
            ForeignKey.from_dict(f) for f in dict_obj.get('foreign_keys', [])
        ]
        dict_obj['indexes'] = [
            Index.from_dict(i) for i in dict_obj.get('indexes', [])
        ]
        dict_obj['unique_constraints'] = [
            UniqueConstraint.from_dict(i) for i in dict_obj.get('unique_constraints', [])
        ]
        dict_obj['check_constraints'] = [
            CheckConstraint.from_dict(i) for i in dict_obj.get('check_constraints', [])
        ]

        return cls(**dict_obj)

    @classmethod
    def from_sqla(cls, sqla_obj):
        """ Create a yalchemy Table from a sqlalchemy Table.

        Arguments:
            sqla_obj: The sqlalchemy Table object
        """

        columns = [Column.from_sqla(col) for col in sqla_obj.c]
        foreign_keys = [ForeignKey.from_sqla(fkey.constraint) for col in sqla_obj.c
                        for fkey in col.foreign_keys]
        primary_keys = [col.name for col in sqla_obj.c if col.primary_key]
        indexes = [Index.from_sqla(i) for i in sqla_obj.indexes]

        check_constraints = [CheckConstraint.from_sqla(c) for c in sqla_obj.constraints
                             if isinstance(c, sa.CheckConstraint)]
        unique_constraints = [UniqueConstraint.from_sqla(c) for c in sqla_obj.constraints
                              if isinstance(c, sa.UniqueConstraint)]
        return cls(
            sqla_obj.name, schema=sqla_obj.schema, columns=columns, foreign_keys=foreign_keys,
            primary_keys=primary_keys, indexes=indexes, check_constraints=check_constraints,
            unique_constraints=unique_constraints)

    def _to_dict(self):
        """ Converts the yalchemy Table to a dictionary """
        columns = [c.to_dict() for c in self.columns]

        table_metadata = {
            'name': self.name,
            'schema': self.schema,
            'columns': columns,
        }
        if self.doc:
            table_metadata['doc'] = self.doc
        if self.primary_keys:
            table_metadata['primary_keys'] = sorted(list(self.primary_keys))
        if self.foreign_keys:
            table_metadata['foreign_keys'] = [fk.to_dict() for fk in sorted(self.foreign_keys)]
        if self.indexes:
            table_metadata['indexes'] = [ix.to_dict() for ix in sorted(self.indexes)]
        if self.unique_constraints:
            table_metadata['unique_constraints'] = [c.to_dict() for c in self.unique_constraints]
        if self.check_constraints:
            table_metadata['check_constraints'] = [c.to_dict() for c in self.check_constraints]
        return table_metadata

    def to_sqla(self, metadata=None, include_indexes=True):  # pylint: disable=arguments-differ
        """ Converts the yalchemy Table to a sqlalchemy Table.

        Args:
            metadata (MetaData): The sqlalchemy metdata object. If ``None``, creates a new
                sqlalchemy MetaData instance.
            include_indexes (bool, default=True): Include indexes when creating the
                sqlalchemy Table object
        """
        metadata = metadata or sa.MetaData()
        indexes = []
        unique_constraints = []
        if include_indexes:
            indexes = [i.to_sqla(table_name=self.name) for i in self.indexes]
            unique_constraints = [c.to_sqla(table_name=self.name) for c in self.unique_constraints]
        check_constraints = [c.to_sqla() for c in self.check_constraints]
        columns = [c.to_sqla(is_primary=c.name in self.primary_keys) for c in self.columns]
        table_elements = columns + indexes + unique_constraints + check_constraints

        table = sa.Table(
            self.name,
            metadata,
            schema=self.schema,
            *table_elements)
        for fkey_obj in self.foreign_keys:
            fkey = fkey_obj.to_sqla()
            table.append_constraint(fkey)
        return table

    def __or__(self, other):
        if other is None:
            return self
        if not self._comparable(other):
            return NotImplemented

        if not (self.name == other.name and self.primary_keys == other.primary_keys):
            raise MergeError(
                'Cannot merge Tables: {0!r}, {1!r}'.format(self, other))

        name_to_column = collections.OrderedDict((c.name, c) for c in self.columns)
        for column in other.columns:
            column_name = column.name
            name_to_column[column_name] = name_to_column.get(column_name) | column

        return type(self)(
            name=self.name,
            schema=self.schema,
            columns=list(name_to_column.values()),
            foreign_keys=self.foreign_keys & other.foreign_keys,
            indexes=self.indexes | other.indexes,
            primary_keys=self.primary_keys,
            unique_constraints=self.unique_constraints & other.unique_constraints,
            check_constraints=self.check_constraints & other.check_constraints,
            doc=self.doc)

    def __copy__(self):  # pragma: no cover
        return Table(
            self.name,
            self.schema,
            columns=self.columns,
            foreign_keys=self.foreign_keys,
            primary_keys=self.primary_keys,
            indexes=self.indexes,
            unique_constraints=self.unique_constraints,
            check_constraints=self.check_constraints,
            doc=self.doc)

    def __repr__(self):
        return 'Table(name={s.name!r}, primary_keys={s.primary_keys!r})'.format(s=self)


class TableSet(Yalchemy, _ComparableMixin):
    """ A yalchemy TableSet that can be converted to a list of sqlalchemy Tables """
    __slots__ = ('tables',)

    def __init__(self, tables=None):
        self.tables = tables or []

    @classmethod
    def from_dict(cls, dict_obj):
        """ Creates a yalchemy TableSet from a dictionary.

        The dictionary has the following specification::

            {
                # The list of table dictionaries. The specification for a table
                # dictionary can be found in the `Table.from_dict` documentation.
                'tables': list[dict](optional)
            }
        """
        return cls([Table.from_dict(t) for t in dict_obj['tables']])

    @classmethod
    def from_sqla(cls, sqla_objs):  # pylint: disable=arguments-differ
        """ Create a yalchemy TableSet from a list of sqlalchemy Tables.

        Arguments:
            sqla_objs (list[Table]): A list of sqlalchemy tables
        """

        return cls(tables=[Table.from_sqla(t) for t in sqla_objs])

    def _to_dict(self):
        """ Converts the yalchemy TableSet to a dictionary """
        return {
            'tables': [t.to_dict() for t in self.tables],
        }

    # pylint: disable=arguments-differ
    def to_sqla(self, metadata=None, include_indexes=True,
                add_unique_constraints=True):
        """ Converts the yalchemy TableSet to a list of sqlalchemy Tables.

        Arguments:
            include_indexes (bool, default=True): Include the indexes in the
                returned sqlalchemy tables.
            add_unique_constraints (bool, default=True):  Add unique constraints
                to the targets of foreign keys. Requires the target tables of foreign
                keys to be in this table set.
        """

        if not metadata:
            metadata = sa.MetaData()

        tables = {}
        table_to_unique_columns = collections.defaultdict(set)
        for table in self.tables:
            sqla_table = table.to_sqla(
                metadata=metadata, include_indexes=include_indexes)
            tables[table.full_name] = sqla_table
            for foreign_key in table.foreign_keys:
                table_to_unique_columns[foreign_key.remote_table].add(
                    foreign_key.remote_column)

        if add_unique_constraints:
            for remote_table, constrains in table_to_unique_columns.items():
                for constraint in constrains:
                    tables[remote_table].append_constraint(
                        sa.UniqueConstraint(constraint))

        return list(tables.values())

    def __or__(self, other):
        if other is None:
            return self
        elif not self._comparable(other):  # pragma: no cover
            return NotImplemented

        name_to_table = collections.OrderedDict((t.name, t) for t in self.tables)
        for table in other.tables:
            table_name = table.name
            name_to_table[table_name] = name_to_table.get(table_name) | table

        return type(self)(tables=list(name_to_table.values()))

    def __copy__(self):  # pragma: no cover
        return TableSet(self.tables)
