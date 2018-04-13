""" Module to make the yaml dumps
of yalchemy dicts prettier than if we
do just a normal dump with yaml.safe_dump """

import collections

import yaml


class PrettyYalchemyDumper(yaml.SafeDumper):  # pylint: disable=too-many-ancestors
    """ Our custom yaml dumper to increase indents
    and to also handle OrderedDict and print it's keys
    out in order """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_representer(collections.OrderedDict, self.dict_representer)

    def increase_indent(self, flow=False, indentless=False):
        """ Increase the indent by forcing indentless to be False """
        return super().increase_indent(flow, False)

    @staticmethod
    def dict_representer(dumper, data):
        return dumper.represent_dict(data.items())
