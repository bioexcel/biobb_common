# type: ignore
from biobb_common.tools import test_fixtures as fx
from biobb_common.generic.folder_test import folder_test


class TestFolderTest():
    def setup_class(self):
        fx.test_setup(self, 'folder_test')

    def teardown_class(self):
        fx.test_teardown(self)

    def test_folder_test(self):
        folder_test(properties=self.properties, **self.paths)
        assert fx.not_empty(self.paths['output_folder'])
