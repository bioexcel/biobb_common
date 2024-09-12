# type: ignore
from biobb_common.tools import test_fixtures as fx
from biobb_common.configuration.settings import ConfReader


class TestConfReader():
    def setup_class(self):
        fx.test_setup(self, 'confreader')

    def teardown_class(self):
        # pass
        fx.test_teardown(self)

    def test_confreader_properties(self):
        print()  # Add a new line for better readability in the console
        for file_name in ['config_complete', 'config_empty', 'config_nostep', 'config_nostep_globals']:
            conf = ConfReader(self.paths[file_name])
            assert fx.compare_object_pickle(conf.get_prop_dic(), self.paths[f'ref_{file_name}_pkl'], ignore_keys=['path', 'working_dir_path', 'sandbox_path'])

    def test_confreader_paths(self):
        print()  # Add a new line for better readability in the console
        for file_name in ['config_complete', 'config_empty', 'config_nostep', 'config_nostep_globals']:
            conf = ConfReader(self.paths[file_name])
            assert fx.compare_object_pickle(conf.get_paths_dic(), self.paths[f'ref_{file_name}_paths_pkl'], ignore_keys=['working_dir_path', 'sandbox_path'], ignore_substring='/Users/pau/projects/biobb_common/')
