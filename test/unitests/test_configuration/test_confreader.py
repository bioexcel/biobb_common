# type: ignore
from biobb_common.tools import test_fixtures as fx
from biobb_common.configuration.settings import ConfReader


class TestConfReader():
    def setup_class(self):
        fx.test_setup(self, 'confreader')

    def teardown_class(self):
        # pass
        fx.test_teardown(self)

    def test_confreader(self):
        conf = ConfReader(self.paths['config'])
        assert fx.compare_object_pickle(conf.get_prop_dic(), self.paths['ref_properties_pkl_path'])
        assert fx.compare_object_pickle(conf.get_paths_dic(), self.paths['ref_paths_pkl_path'])
