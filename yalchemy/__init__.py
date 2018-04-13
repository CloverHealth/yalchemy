"""The primary yalchemy interface

Consult the ``from_dict`` method of the yalchemy objects for information
on how they are constructed.
"""
# Geoalchemy must be imported for geography points to be
# reflected properly
import geoalchemy2

from yalchemy.pretty_yaml import PrettyYalchemyDumper
from yalchemy.table_structures import Column
from yalchemy.table_structures import Index
from yalchemy.table_structures import ForeignKey
from yalchemy.table_structures import UniqueConstraint
from yalchemy.table_structures import CheckConstraint
from yalchemy.table_structures import Table
from yalchemy.table_structures import TableSet
from yalchemy.version import __version__  # flake8: noqa


__all__ = [
    'Column',
    'Index',
    'ForeignKey',
    'UniqueConstraint',
    'CheckConstraint',
    'Table',
    'TableSet',
    'PrettyYalchemyDumper',
]
