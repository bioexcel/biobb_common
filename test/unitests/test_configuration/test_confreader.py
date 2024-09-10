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
        conf = ConfReader(self.paths['config_complete'])
        assert fx.compare_object_pickle(conf.get_prop_dic(), self.paths['ref_config_complete_pkl'], ignore_keys=['path', 'working_dir_path', 'sandbox_path'])

        conf = ConfReader(self.paths['config_empty'])
        assert fx.compare_object_pickle(conf.get_prop_dic(), self.paths['ref_config_empty_pkl'], ignore_keys=['path', 'working_dir_path', 'sandbox_path'])

        conf = ConfReader(self.paths['config_nostep'])
        assert fx.compare_object_pickle(conf.get_prop_dic(), self.paths['ref_config_nostep_pkl'], ignore_keys=['path', 'working_dir_path', 'sandbox_path'])

        conf = ConfReader(self.paths['config_nostep_globals'])
        assert fx.compare_object_pickle(conf.get_prop_dic(), self.paths['ref_config_nostep_globals_pkl'], ignore_keys=['path', 'working_dir_path', 'sandbox_path'])
