"""Boiler plate functions for testsys
"""
import os
from os.path import join as opj
import sys
import shutil
import hashlib

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
    test_object.data_dir = opj(test_object.test_dir, 'data')
    test_object.reference_dir = opj(test_object.test_dir, 'reference')
    if config:
        test_object.conf_file_path = config
    else:
        test_object.conf_file_path = opj(test_object.test_dir, 'conf.yml')

    test_object.system = os.getenv('testsys')
    conf = settings.ConfReader(test_object.conf_file_path, test_object.system)

    if dict_key:
        test_object.properties = conf.get_prop_dic()[dict_key]
        test_object.paths = {k:v.replace('test_data_dir', test_object.data_dir, 1).replace('test_reference_dir', test_object.reference_dir, 1) for k, v in conf.get_paths_dic()[dict_key].items()}
    else:
        test_object.properties = conf.get_prop_dic()
        test_object.paths = {k:v.replace('test_data_dir', test_object.data_dir, 1).replace('test_reference_dir', test_object.reference_dir, 1) for k, v in conf.get_paths_dic().items()}

    fu.create_dir(test_object.properties['path'])
    os.chdir(test_object.properties['path'])

def test_teardown(test_object):
    """Remove the **test_object.properties['working_dir_path']**

    Args:
        test_object (:obj:`test`): The test object.
    """
    shutil.rmtree(test_object.properties['path'])

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
    print("Checking if empty file: "+file_path)
    return os.path.isfile(file_path) and os.path.getsize(file_path) > 0

def compare_hash(file_a, file_b):
    """Compute and compare the hashes of two files"""
    print("Comparing: ")
    print("        File_A: "+file_a)
    print("        File_B: "+file_b)
    file_a_hash = hashlib.sha256(open(file_a, 'rb').read()).digest()
    file_b_hash = hashlib.sha256(open(file_b, 'rb').read()).digest()
    return file_a_hash == file_b_hash

def equal(file_a, file_b):
    """Check if two files are equal"""
    if file_a.endswith(".zip") and file_b.endswith(".zip"):
        print("This is a ZIP comparison!")
        print("Unzipping:")
        print("Creating a unique_dir for: %s" % file_a)
        file_a_dir = fu.create_unique_dir()
        file_a_list = fu.unzip_list(file_a, dest_dir=file_a_dir)
        print("Creating a unique_dir for: %s" % file_b)
        file_b_dir = fu.create_unique_dir()
        file_b_list = fu.unzip_list(file_b, dest_dir=file_b_dir)
        if not len(file_a_list) == len(file_b_list):
            print("Uncompressed different number of files")
            return False
        for uncompressed_file_a in file_a_list:
            uncompressed_file_b = os.path.join(file_b_dir, os.path.basename(uncompressed_file_a))
            if not compare_hash(uncompressed_file_a, uncompressed_file_b):
                return False
        return True
    return compare_hash(file_a, file_b)
