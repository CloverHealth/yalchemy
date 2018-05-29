""" Test that we print yaml out in a pretty way
with the keys ordered by the __slots__ order """
import yaml

from yalchemy import table_structures


class CustomTestLoader(yaml.SafeLoader):  # pylint: disable=too-many-ancestors
    def __init__(self, stream):
        """
        :param stream: data stream
        """
        super().__init__(stream)
        self.add_constructor('!my_custom_tag', CustomTestLoader.custom_tag)

    def custom_tag(self, node):  # pylint: disable=no-self-use
        assert isinstance(node, yaml.ScalarNode)
        assert isinstance(node.value, str)

        return '--{}--'.format(node.value)


TEST_YAML_PRETTY = """
tables:
  - name: test_table
    schema: test_schema
    columns:
      - {name: my_col, datatype: text, required: false}
"""

REVERSE_TEST_YAML_PRETTY = """
tables:
  - columns:
      - {required: false, datatype: text, name: my_col}
    schema: test_schema
    name: test_table
"""

TEST_YAML_CUSTOM_TAG = """
tables:
  - name: test_table
    schema: test_schema
    columns:
      - {name: my_col, datatype: text, required: false}
    doc: !my_custom_tag 'My Description'
"""
REVERSE_TEST_YAML_CUSTOM_TAG = """
tables:
  - name: test_table
    schema: test_schema
    columns:
      - {name: my_col, datatype: text, required: false}
    doc: --My Description--
"""


def test_pretty_yaml_printing():
    """ Test a simple case that we correctly
    orders a table and column by it's slots  """
    col = table_structures.Column('my_col', 'text')
    table = table_structures.Table(name='test_table', schema='test_schema', columns=[col])
    table_set = table_structures.TableSet(tables=[table])
    assert table_set.to_yaml() == TEST_YAML_PRETTY.lstrip()

    # test with reversing the __slots__ order in the table and column
    table.__slots__ = table.__slots__[::-1]
    col.__slots__ = col.__slots__[::-1]
    assert table_set.to_yaml() == REVERSE_TEST_YAML_PRETTY.lstrip()


def test_custom_yaml_loader():
    """
    Test the ability to use a custom PyYAML loader
    """
    tables = table_structures.TableSet.from_yaml(
        TEST_YAML_CUSTOM_TAG.lstrip(),
        loader_factory=CustomTestLoader,
    )
    assert isinstance(tables, table_structures.TableSet)

    assert tables.to_yaml() == REVERSE_TEST_YAML_CUSTOM_TAG.lstrip()
