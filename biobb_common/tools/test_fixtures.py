"""Boiler plate functions for testsys
"""
import os
import sys
import shutil
from os.path import join as opj
from biobb_common.configuration import settings
from biobb_common.tools import file_utils as fu

def test_setup(test_object, dict_key=None, config=None):
    """Add the unitest_dir, test_dir, conf_file_path, system, properties and path as
    attributes to the **test_object** and create a directory to launch the unitest.

    Args:
        test_object (:obj:`test`): The test object.
        dict_key (str): Key of the test parameters in the yaml config file.
    """
    test_object.testfile_dir = os.path.dirname(os.path.abspath(sys.modules[test_object.__class__.__module__].__file__))
    test_object.unitest_dir = os.path.dirname(test_object.testfile_dir)
    test_object.test_dir = os.path.dirname(test_object.unitest_dir)
    test_object.data_dir = opj(test_object.test_dir,'data')
    if config:
        test_object.conf_file_path= config
    else:
        test_object.conf_file_path= opj(test_object.test_dir, 'conf.yml')

    test_object.system=os.getenv('testsys')
    conf = settings.ConfReader(test_object.conf_file_path, test_object.system)

    if dict_key:
        test_object.properties = conf.get_prop_dic()[dict_key]
        test_object.paths = {k:v.replace('test_data_dir', test_object.data_dir, 1) for k, v in conf.get_paths_dic()[dict_key].items()}
    else:
        test_object.properties = conf.get_prop_dic()
        test_object.paths = {k:v.replace('test_data_dir', test_object.data_dir, 1) for k, v in conf.get_paths_dic().items()}

    fu.create_dir(test_object.properties['path'])
    os.chdir(test_object.properties['path'])

def test_teardown(test_object):
    """Remove the **test_object.properties['workflow_path']**

    Args:
        test_object (:obj:`test`): The test object.
    """
    shutil.rmtree(test_object.properties['workflow_path'])

def exe_success(return_code):
    """Check if **return_code** is 0

    Args:
        return_code (int): Return code of a process.

    Returns:
        bool: True if return code is equal to 0
    """
    return return_code == 0

def not_empty(file_path):
    """Check if file exists and is not empty.

    Args:
        file_path (str): Path to the file.

    Returns:
        bool: True if **file_path** exists and is not empty.
    """
    return ( os.path.isfile(file_path) and os.path.getsize(file_path) > 0 )
