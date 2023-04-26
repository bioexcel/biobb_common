"""Boiler plate functions for testsys
"""
import os
import typing
from pathlib import Path
import sys
import shutil
import hashlib
import Bio.PDB
import codecs
from biobb_common.configuration import settings
from biobb_common.tools import file_utils as fu
import numpy as np


def test_setup(test_object: object, dict_key: str = None, config: str = None):
    """Add the unitest_dir, test_dir, conf_file_path, system, properties and path as
    attributes to the **test_object** and create a directory to launch the unitest.

    Args:
        test_object (:obj:`test`): The test object.
        dict_key (str): Key of the test parameters in the yaml config file.
        config (str): Path to the configuration file.
    """
    test_object.testfile_dir = str(Path(Path(sys.modules[test_object.__module__].__file__).resolve()).parent)
    test_object.unitest_dir = str(Path(test_object.testfile_dir).parent)
    test_object.test_dir = str(Path(test_object.unitest_dir).parent)
    test_object.data_dir = str(Path(test_object.test_dir).joinpath('data'))
    test_object.reference_dir = str(Path(test_object.test_dir).joinpath('reference'))
    if config:
        test_object.conf_file_path = config
    else:
        test_object.conf_file_path = str(Path(test_object.test_dir).joinpath('conf.yml'))

    test_object.system = os.getenv('testsys')
    conf = settings.ConfReader(test_object.conf_file_path, test_object.system)

    if dict_key:
        test_object.properties = conf.get_prop_dic()[dict_key]
        test_object.paths = {k: v.replace('test_data_dir', test_object.data_dir, 1).replace('test_reference_dir', test_object.reference_dir, 1) for k, v in conf.get_paths_dic()[dict_key].items()}
    else:
        test_object.properties = conf.get_prop_dic()
        test_object.paths = {k: v.replace('test_data_dir', test_object.data_dir, 1).replace('test_reference_dir', test_object.reference_dir, 1) for k, v in conf.get_paths_dic().items()}

    fu.create_dir(test_object.properties['path'])
    os.chdir(test_object.properties['path'])


def test_teardown(test_object: object):
    """Remove the **test_object.properties['working_dir_path']**

    Args:
        test_object (:obj:`test`): The test object.
    """
    unitests_path = Path(test_object.properties['path']).resolve().parent
    print(f"\nRemoving: {unitests_path}")
    shutil.rmtree(unitests_path)


def exe_success(return_code: int) -> bool:
    """Check if **return_code** is 0

    Args:
        return_code (int): Return code of a process.

    Returns:
        bool: True if return code is equal to 0
    """
    return return_code == 0


def not_empty(file_path: str) -> bool:
    """Check if file exists and is not empty.

    Args:
        file_path (str): Path to the file.

    Returns:
        bool: True if **file_path** exists and is not empty.
    """
    print("Checking if empty file: "+file_path)
    return Path(file_path).is_file() and Path(file_path).stat().st_size > 0


def compare_hash(file_a: str, file_b: str) -> bool:
    """Compute and compare the hashes of two files"""
    print("Comparing: ")
    print("        File_A: "+file_a)
    print("        File_B: "+file_b)
    file_a_hash = hashlib.sha256(open(file_a, 'rb').read()).digest()
    file_b_hash = hashlib.sha256(open(file_b, 'rb').read()).digest()
    print("        File_A hash: "+str(file_a_hash))
    print("        File_B hash: "+str(file_b_hash))
    return file_a_hash == file_b_hash


def equal(file_a: str, file_b: str, ignore_list: typing.List[typing.Union[str, int]] = None, **kwargs) -> bool:
    """Check if two files are equal"""
    if ignore_list:
        # Line by line comparison
        return compare_line_by_line(file_a, file_b, ignore_list)

    if file_a.endswith(".zip") and file_b.endswith(".zip"):
        return compare_zip(file_a, file_b)

    if file_a.endswith(".pdb") and file_b.endswith(".pdb"):
        return compare_pdb(file_a, file_b, **kwargs)

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

    if file_a.endswith((".nc", ".netcdf", ".xtc")) and file_b.endswith((".nc", ".netcdf", ".xtc")):
        return compare_size(file_a, file_b, kwargs.get('percent_tolerance', 1.0))

    if file_a.endswith(".xvg") and file_b.endswith(".xvg"):
        return compare_xvg(file_a, file_b, kwargs.get('percent_tolerance', 1.0))

    image_extensions = ('.png', '.jfif', '.ppm', '.tiff', '.jpg', '.dib', '.pgm', '.bmp', '.jpeg', '.pbm', '.jpe', '.apng', '.pnm', '.gif', '.tif')
    if file_a.endswith(image_extensions) and file_b.endswith(image_extensions):
        return compare_images(file_a, file_b, kwargs.get('percent_tolerance', 1.0))

    return compare_hash(file_a, file_b)


def compare_line_by_line(file_a: str, file_b: str, ignore_list: typing.List[typing.Union[str, int]]) -> bool:
    with open(file_a) as fa, open(file_b) as fb:
        for index, (line_a, line_b) in enumerate(zip(fa, fb)):
            if index in ignore_list or any(word in line_a for word in ignore_list if isinstance(word, str)):
                continue
            elif line_a != line_b:
                return False
        return True


def equal_txt(file_a: str, file_b: str) -> bool:
    """Check if two text files are equal"""
    return compare_hash(file_a, file_b)


def compare_zip(zip_a: str, zip_b: str) -> bool:
    """ Compare zip files """
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
        uncompressed_zip_b = str(Path(zip_b_dir).joinpath(Path(uncompressed_zip_a).name))
        if not equal(uncompressed_zip_a, uncompressed_zip_b):
            return False

    return True


def compare_pdb(pdb_a: str, pdb_b: str, rmsd_cutoff: int = 1, remove_hetatm: bool = True, remove_hydrogen: bool = True, **kwargs):
    """ Compare pdb files """
    print("Checking RMSD between:")
    print("     PDB_A: "+pdb_a)
    print("     PDB_B: "+pdb_b)
    pdb_parser = Bio.PDB.PDBParser(PERMISSIVE=True, QUIET=True)
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


def compare_top_itp(file_a: str, file_b: str) -> bool:
    """ Compare top/itp files """
    print("Comparing TOP/ITP:")
    print("     FILE_A: "+file_a)
    print("     FILE_B: "+file_b)
    with codecs.open(file_a, 'r', encoding='utf-8', errors='ignore') as f_a:
        next(f_a)
        with codecs.open(file_b, 'r', encoding='utf-8', errors='ignore') as f_b:
            next(f_b)
            return [line.strip() for line in f_a if not line.strip().startswith(';')] == [line.strip() for line in f_b if not line.strip().startswith(';')]


def compare_ignore_first(file_a: str, file_b: str) -> bool:
    """ Compare two files ignoring the first line """
    print("Comparing ignoring first line of both files:")
    print("     FILE_A: "+file_a)
    print("     FILE_B: "+file_b)
    with open(file_a) as f_a:
        next(f_a)
        with open(file_b) as f_b:
            next(f_b)
            return [line.strip() for line in f_a] == [line.strip() for line in f_b]


def compare_size(file_a: str, file_b: str, percent_tolerance: float = 1.0) -> bool:
    """ Compare two files using size """
    print("Comparing size of both files:")
    print(f"     FILE_A: {file_a}")
    print(f"     FILE_B: {file_b}")
    size_a = Path(file_a).stat().st_size
    size_b = Path(file_b).stat().st_size
    average_size = (size_a + size_b) / 2
    tolerance = average_size * percent_tolerance / 100
    tolerance_low = average_size - tolerance
    tolerance_high = average_size + tolerance
    print(f"     SIZE_A: {size_a} bytes")
    print(f"     SIZE_B: {size_b} bytes")
    print(f"     TOLERANCE: {percent_tolerance}%, Low: {tolerance_low} bytes, High: {tolerance_high} bytes")
    return (tolerance_low <= size_a <= tolerance_high) and (tolerance_low <= size_b <= tolerance_high)


def compare_xvg(file_a: str, file_b: str, percent_tolerance: float = 1.0) -> bool:
    """ Compare two files using size """
    print("Comparing size of both files:")
    print(f"     FILE_A: {file_a}")
    print(f"     FILE_B: {file_b}")
    arrays_tuple_a = np.loadtxt(file_a, comments="@", unpack=True)
    arrays_tuple_b = np.loadtxt(file_b, comments="@", unpack=True)
    for array_a, array_b in zip(arrays_tuple_a, arrays_tuple_b):
        if not np.allclose(array_a, array_b, rtol=percent_tolerance / 100):
            return False
    return True


def compare_images(file_a: str, file_b: str, percent_tolerance: float = 1.0) -> bool:
    try:
        from PIL import Image
        import imagehash
    except ImportError:
        print("To compare images, please install the following packages: Pillow, imagehash")
        return False

    """ Compare two files using size """
    print("Comparing images of both files:")
    print(f"     IMAGE_A: {file_a}")
    print(f"     IMAGE_B: {file_b}")
    hash_a = imagehash.average_hash(Image.open(file_a))
    hash_b = imagehash.average_hash(Image.open(file_b))
    tolerance = (len(hash_a) + len(hash_b)) / 2 * percent_tolerance / 100
    if tolerance < 1:
        tolerance = 1
    difference = hash_a - hash_b
    print(f"     IMAGE_A HASH: {hash_a} SIZE: {len(hash_a)} bits")
    print(f"     IMAGE_B HASH: {hash_b} SIZE: {len(hash_b)} bits")
    print(f"     TOLERANCE: {percent_tolerance}%, ABS TOLERANCE: {tolerance} bits, DIFFERENCE: {difference} bits")
    if difference > tolerance:
        return False
    return True
