yalchemy
========

yalchemy is a tool for converting YAML (or Python dictionaries) to SQLAlchemy objects.

Quick Start
-----------

yalchemy provides the following intermediate yalchemy objects:

1. `Table` - For converting `SQLAlchemy Tables <http://docs.sqlalchemy.org/en/latest/core/metadata.html#sqlalchemy.schema.Table>`_.
2. `Index` - For converting `SQLAlchemy Indexes <http://docs.sqlalchemy.org/en/latest/core/constraints.html#sqlalchemy.schema.Index>`_.
3. `ForeignKey` - For converting `SQLAlchemy ForeignKeys <http://docs.sqlalchemy.org/en/latest/core/constraints.html#sqlalchemy.schema.ForeignKey>`_.
4. `UniqueConstraint` - For converting `SQLAlchemy UniqueConstraints <http://docs.sqlalchemy.org/en/latest/core/constraints.html#sqlalchemy.schema.UniqueConstraint>`_.
5. `CheckConstraint` - For converting `SQLAlchemy CheckConstraints <http://docs.sqlalchemy.org/en/latest/core/constraints.html#sqlalchemy.schema.CheckConstraint>`_.
6. `Column` - For converting `SQLAlchemy Columns <http://docs.sqlalchemy.org/en/latest/core/metadata.html#sqlalchemy.schema.Column>`_
7. `TableSet` - A utility for representing a list of SQLAlchemy Tables.

Each of these objects implement the following yalchemy object interface:

.. autoclass:: yalchemy.table_structures.Yalchemy
    :members:

With this interface, it's possible to do the following types of conversions:

.. code-block:: python

    import yalchemy

    # Create a SQLAlchemy table from a dictionary
    table = yalchemy.Table.from_dict({
        'name': 'my_table',
        'schema': 'schema',
        'columns': [
            {'name': 'col1', 'datatype': 'varchar', 'format': [123], 'null': '^@'},
            {'name': 'col2', 'datatype': 'integer', 'required': True},
            {'name': 'col3', 'datatype': 'timestamptz', 'required': True,
             'default': {'type': 'function', 'value': 'NOW()'}}
        ],
        'foreign_keys': [
            {'column': 'col2', 'remote_table': 'other_table', 'remote_column': 'other_col'}
        ],
        'indexes': [{'columns': ['col1', 'col2']}],
        'unique_constraints': [{'columns': ['col3']}],
        'primary_keys': ['col2']
    }).to_sqla(...)

    # Columns, foreign keys, and indexes can also be created / converted in the same way
    column = yalchemy.Column.from_dict({
        'name': 'col2',
        'datatype': 'integer',
        'required': True
    }).to_sqla(...)

    fkey = yalchemy.ForeignKey.from_dict({
        'column': 'col2',
        'remote_table': 'other_table',
        'remote_column': 'other_col'
    }).to_sqla(...)

    index = yalchemy.Index.from_dict({'columns': ['col1', 'col2']}).to_sqla(...)

In yalchemy, the keys used in the dictionaries in the ``from_dict`` constructors are similar to
the constructor arguments. For example,

.. code-block:: python

    # Create a yalchemy column object directly
    column = yalchemy.Column(name='col2', remote_table='other_table', remote_column='other_col')

    # Create the yalchemy object from a dictionary
    column = yalchemy.Column.from_dict({'name': 'col2', 'remote_table': 'other_table', 'remote_column': 'other_col'})

    # Convert it to sqlalchemy
    column.to_sqla()

When instantiating more complex objects like a `Table`, the keys used in the dictionaries are also similar
to the constructor arguments, however, the values are sometimes other yalchemy objects. It is recommended to use
``from_dict`` constructor when instantiating a yalchemy object whenever possible.

Keep in mind that ``to_sqla`` methods sometimes require additional arguments for conversion. Please consult the
:ref:`interface` section for details on all of the ``to_sqla`` methods.

Next Steps
----------

For the full documentation on the interface and the spec used to create yalchemy object from dictionaries,
view the :ref:`interface` section.