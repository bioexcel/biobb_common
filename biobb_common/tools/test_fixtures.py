"""Boiler plate functions for testsys
"""
import os
from os.path import join as opj
import sys
import shutil
import hashlib
import Bio.PDB

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
    print("Removing: %s" % test_object.properties['path'])
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
    print("        File_A hash: "+str(file_a_hash))
    print("        File_B hash: "+str(file_b_hash))
    return file_a_hash == file_b_hash

def equal(file_a, file_b):
    """Check if two files are equal"""
    if file_a.endswith(".zip") and file_b.endswith(".zip"):
        return compare_zip(file_a, file_b)

    if file_a.endswith(".pdb") and file_b.endswith(".pdb"):
        return compare_pdb(file_a, file_b)

    if file_a.endswith(".top") and file_b.endswith(".top"):
        return compare_top_itp(file_a, file_b)

    if file_a.endswith(".itp") and file_b.endswith(".itp"):
        return compare_top_itp(file_a, file_b)

    if file_a.endswith(".gro") and file_b.endswith(".gro"):
        return compare_ignore_first(file_a, file_b)

    if file_a.endswith(".prmtop") and file_b.endswith(".prmtop"):
        return compare_ignore_first(file_a, file_b)

    if file_a.endswith(".inp") and file_b.endswith(".inp"):
        return compare_ignore_first(file_a, file_b)

    if file_a.endswith(".par") and file_b.endswith(".par"):
        return compare_ignore_first(file_a, file_b)

    return compare_hash(file_a, file_b)

def compare_zip(zip_a, zip_b):
    print("This is a ZIP comparison!")
    print("Unzipping:")
    print("Creating a unique_dir for: %s" % zip_a)
    zip_a_dir = fu.create_unique_dir()
    zip_a_list = fu.unzip_list(zip_a, dest_dir=zip_a_dir)
    print("Creating a unique_dir for: %s" % zip_b)
    zip_b_dir = fu.create_unique_dir()
    zip_b_list = fu.unzip_list(zip_b, dest_dir=zip_b_dir)

    if not len(zip_a_list) == len(zip_b_list):
        return False

    for uncompressed_zip_a in zip_a_list:
        uncompressed_zip_b = os.path.join(zip_b_dir, os.path.basename(uncompressed_zip_a))
        if not equal(uncompressed_zip_a, uncompressed_zip_b):
            return False

    return True

def compare_pdb(pdb_a, pdb_b, rmsd_cutoff=1, remove_hetatm=True, remove_hydrogen=True):
    print("Checking RMSD between:")
    print("     PDB_A: "+pdb_a)
    print("     PDB_B: "+pdb_b)
    pdb_parser = Bio.PDB.PDBParser(QUIET=True)
    st_a = pdb_parser.get_structure("st_a", pdb_a)[0]
    st_b = pdb_parser.get_structure("st_b", pdb_b)[0]

    if remove_hetatm:
        print("     Ignoring HETAMT in RMSD")
        residues_a = [list(res.get_atoms()) for res in st_a.get_residues() if not res.id[0].startswith('H_')]
        residues_b = [list(res.get_atoms()) for res in st_b.get_residues() if not res.id[0].startswith('H_')]
        atoms_a = [atom for residue in residues_a for atom in residue]
        atoms_b = [atom for residue in residues_b for atom in residue]
    else:
        atoms_a = st_a.get_atoms()
        atoms_b = st_b.get_atoms()

    if remove_hydrogen:
        print("     Ignoring Hydrogen atoms in RMSD")
        atoms_a = [atom for atom in atoms_a if not atom.get_name().startswith('H')]
        atoms_b = [atom for atom in atoms_b if not atom.get_name().startswith('H')]

    print("     Atoms ALIGNED in PDB_A: "+str(len(atoms_a)))
    print("     Atoms ALIGNED in PDB_B: "+str(len(atoms_b)))
    super_imposer = Bio.PDB.Superimposer()
    super_imposer.set_atoms(atoms_a, atoms_b)
    super_imposer.apply(atoms_b)
    print('     RMS: '+str(super_imposer.rms))
    print('     RMS_CUTOFF: '+str(rmsd_cutoff))
    return super_imposer.rms < rmsd_cutoff

def compare_top_itp(file_a, file_b):
    print("Comparing TOP/ITP:")
    print("     FILE_A: "+file_a)
    print("     FILE_B: "+file_b)
    with open(file_a, 'r') as f_a:
        with open(file_b, 'r') as f_b:
            return [line.strip() for line in f_a if not line.strip().startswith(';')] == [line.strip() for line in f_b if not line.strip().startswith(';')]

def compare_ignore_first(file_a, file_b):
    print("Comparing ignoring first line of both files:")
    print("     FILE_A: "+file_a)
    print("     FILE_B: "+file_b)
    with open(file_a, 'r') as f_a:
        next(f_a)
        with open(file_b, 'r') as f_b:
            next(f_b)
            return [line.strip() for line in f_a] == [line.strip() for line in f_b]
