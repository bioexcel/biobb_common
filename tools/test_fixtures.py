"""Boiler plate functions for testsys
"""
import os
import sys
import shutil
from os.path import join as opj
from configuration import settings
from tools import file_utils as fu

def test_setup(test_object, dict_key):
    test_object.unitest_dir = os.path.dirname(os.path.abspath(sys.modules[test_object.__name__].__file__))
    test_object.test_dir = os.path.dirname(test_object.unitest_dir)
    test_object.data_dir = opj(test_object.test_dir,'data')
    test_object.yaml_path= opj(test_object.test_dir, 'conf.yaml')
    test_object.system=os.getenv('testsys')
    if test_object.system is None:
        print 'WARNING: "testsys" env variable should be set, "linux" will be used by default value.'
        print '     Please, try: "export testsys=linux"'
        test_object.system='linux'
    conf = settings.YamlReader(test_object.yaml_path, test_object.system)
    test_object.properties = conf.get_prop_dic()[dict_key]
    test_object.paths = conf.get_paths_dic()[dict_key]
    fu.create_dir(test_object.properties['path'])
    os.chdir(test_object.properties['path'])

def test_teardown(test_object):
    shutil.rmtree(test_object.properties['workflow_path'])

def exe_success(return_code):
    return return_code == 0

def not_empty(file_path):
    return ( os.path.isfile(file_path) and os.path.getsize(file_path) > 0 )
