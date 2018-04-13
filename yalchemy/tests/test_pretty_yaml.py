""" Test that we print yaml out in a pretty way
with the keys ordered by the __slots__ order """


from yalchemy import table_structures


TEST_YAML = """
tables:
  - name: test_table
    schema: test_schema
    columns:
      - {name: my_col, datatype: text, required: false}
"""

REVERSE_TEST_YAML = """
tables:
  - columns:
      - {required: false, datatype: text, name: my_col}
    schema: test_schema
    name: test_table
"""


def test_pretty_yaml_printing():
    """ Test a simple case that we correctly
    orders a table and column by it's slots  """

    col = table_structures.Column('my_col', 'text')
    table = table_structures.Table(name='test_table', schema='test_schema', columns=[col])
    table_set = table_structures.TableSet(tables=[table])
    assert table_set.to_yaml() == TEST_YAML.lstrip()

    # test with reversing the __slots__ order in the table and column
    table.__slots__ = table.__slots__[::-1]
    col.__slots__ = col.__slots__[::-1]
    assert table_set.to_yaml() == REVERSE_TEST_YAML.lstrip()
