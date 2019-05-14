"""Tools to work with files
"""
import os
import re
import time
import pathlib
import shutil
import zipfile
import logging
import uuid
import difflib
import warnings
from biobb_common.command_wrapper import cmd_wrapper

def create_dir(dir_path):
    """Returns the directory **dir_path** and create it if path does not exist.

    Args:
        dir_path (str): Path to the directory that will be created.

    Returns:
        str: Directory dir path.
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    return dir_path

def create_unique_dir(prefix='', number_attempts=10, out_log=None):
    """Create a directory with a prefix + computed unique name. If the
    computed name collides with an existing file name it attemps
    **number_attempts** times to create another unique id and create
    the directory with the new name.

    Args:
        prefix (str): ('') String to be added before the computed unique dir name.
        number_attempts (int): (10) number of times creating the directory if there's a name conflict.
        out_log (logger): (None) Python logger object.

    Returns:
        str: Directory dir path.
    """
    name = prefix + str(uuid.uuid4())
    for i in range(number_attempts):
        try:
            os.mkdir(name)
            if out_log:
                out_log.info('%s directory successfully created' %(name))
            return name
        except FileExistsError:
            if out_log:
                out_log.info(name + ' Already exists')
                out_log.info('Retrying %i times more' %(number_attempts-i))
            name = prefix + str(uuid.uuid4())
            if out_log:
                out_log.info('Trying with: ' + name)
    raise FileExistsError

def get_working_dir_path(working_dir_path=None):
    """Return the directory **working_dir_path** and create it if working_dir_path
    does not exist. If **working_dir_path** exists a consecutive numerical suffix
    is added to the end of the **working_dir_path** and is returned.

    Args:
        working_dir_path (str): Path to the workflow results.

    Returns:
        str: Path to the workflow results directory.
    """
    if not working_dir_path:
        return os.path.abspath(os.getcwd())

    working_dir_path = os.path.abspath(working_dir_path)

    if not os.path.exists(working_dir_path):
        return working_dir_path

    cont = 1
    while os.path.exists(working_dir_path):
        working_dir_path = working_dir_path.rstrip('\\/0123456789_') + '_' + str(cont)
        cont += 1
    return working_dir_path

def zip_list(zip_file, file_list, out_log=None):
    """ Compress all files listed in **file_list** into **zip_file** zip file.

    Args:
        zip_file (str): Output compressed zip file.
        file_list (:obj:`list` of :obj:`str`): Input list of files to be compressed.
    """
    file_list.sort()
    with zipfile.ZipFile(zip_file, 'w') as zip_f:
        for f in file_list:
            zip_f.write(f, arcname=os.path.basename(f))
    if out_log:
        out_log.info("Adding:")
        out_log.info(str(file_list))
        out_log.info("to: "+ os.path.abspath(zip_file))

def unzip_list(zip_file, dest_dir=None, out_log=None):
    """ Extract all files in the zipball file and return a list containing the
        absolute path of the extracted files.

    Args:
        zip_file (str): Input compressed zip file.
        dest_dir (str): Path to directory where the files will be extracted.

    Returns:
        :obj:`list` of :obj:`str`: List of paths of the extracted files.
    """
    with zipfile.ZipFile(zip_file, 'r') as zip_f:
        zip_f.extractall(path=dest_dir)
        file_list = [os.path.join(dest_dir,f) for f in zip_f.namelist()]

    if out_log:
        out_log.info("Extracting: "+ os.path.abspath(zip_file))
        out_log.info("to:")
        out_log.info(str(file_list))

    return file_list

def search_topology_files(top_file, out_log=None):
    """ Search the top and itp files to create a list of the topology files"""
    top_dir_name = os.path.dirname(top_file)
    file_list = []
    pattern = re.compile(r"#include\s+\"(.+)\"")
    if os.path.exists(top_file):
        with open(top_file, 'r') as tf:
            for line in tf:
                include_file = pattern.match(line.strip())
                if include_file:
                    found_file = os.path.join(top_dir_name, include_file.group(1))
                    file_list += search_topology_files(found_file, out_log)
    else:
        if out_log:
            out_log.info("Ignored file %s" % top_file)
        return file_list
    return file_list + [top_file]

def zip_top(zip_file, top_file, out_log=None):
    """ Compress all *.itp and *.top files in the cwd into **zip_file** zip file.

    Args:
        zip_file (str): Output compressed zip file.
    """

    file_list = search_topology_files(top_file, out_log)
    zip_list(zip_file, file_list, out_log)

def unzip_top(zip_file, out_log=None):
    """ Extract all files in the zip_file and copy the file extracted ".top" file to top_file.

    Args:
        zip_file (str): Input topology zipball file path.
        top_file (str): Output ".top" file where the extracted ".top" file will be copied.

    Returns:
        :obj:`list` of :obj:`str`: List of extracted files paths.
    """
    top_list = unzip_list(zip_file, create_unique_dir(), out_log)
    top_file = next(name for name in top_list if name.endswith(".top"))
    if out_log:
        out_log.info('Unzipping: ')
        out_log.info(zip_file)
        out_log.info('To: ')
        for file_name in top_list:
            out_log.info(file_name)
    return top_file


def get_logs_prefix():
    return 4*' '

def get_logs(path=None, prefix=None, step=None, can_write_console=True, level='INFO', light_format=False):
    """ Get the error and and out Python Logger objects.

    Args:
        path (str): (current working directory) Path to the log file directory.
        prefix (str): Prefix added to the name of the log file.
        step (str):  String added between the **prefix** arg and the name of the log file.
        can_write_console (bool): (False) If True, show log in the execution terminal.
        level (str): ('INFO') Set Logging level. ['CRITICAL','ERROR','WARNING','INFO','DEBUG','NOTSET']

    Returns:
        :obj:`tuple` of :obj:`Logger` and :obj:`Logger`: Out and err Logger objects.
    """
    prefix = prefix if prefix else ''
    step = step if step else ''
    path = path if path else os.getcwd()

    out_log_path = create_name(path=path, step=step, name='log.out')
    err_log_path = create_name(path=path, step=step, name='log.err')
    # Create dir if it not exists
    create_dir(os.path.dirname(os.path.abspath(out_log_path)))

    # Create logging format
    logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    if light_format:
        logFormatter = logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S")
    # Create logging objects
    out_Logger = logging.getLogger(out_log_path)
    err_Logger = logging.getLogger(err_log_path)


    #Create FileHandler
    out_fileHandler = logging.FileHandler(out_log_path, mode='a', encoding=None, delay=False)
    err_fileHandler = logging.FileHandler(err_log_path, mode='a', encoding=None, delay=False)

    # Asign format to FileHandler
    out_fileHandler.setFormatter(logFormatter)
    err_fileHandler.setFormatter(logFormatter)

    #Asign FileHandler to logging object
    if not len(out_Logger.handlers):
        out_Logger.addHandler(out_fileHandler)
        err_Logger.addHandler(err_fileHandler)

    # Create consoleHandler
    consoleHandler = logging.StreamHandler()
    # Asign format to consoleHandler
    consoleHandler.setFormatter(logFormatter)

    # Asign consoleHandler to logging objects as aditional output
    if can_write_console and len(out_Logger.handlers) < 2:
        out_Logger.addHandler(consoleHandler)
        err_Logger.addHandler(consoleHandler)

    # Set logging level level
    out_Logger.setLevel(level)
    err_Logger.setLevel(level)
    return out_Logger, err_Logger

def log(string, local_log=None, global_log=None):
    """Checks if log exists"""
    if local_log:
        local_log.info(string)
    if global_log:
        global_log.info(get_logs_prefix()+string)

def human_readable_time(time_ps):
    """Transform **time_ps** to a human readable string.

    Args:
        time_ps (int): Time in pico seconds.

    Returns:
        str: Human readable time.
    """
    time_units = ['femto seconds', 'pico seconds', 'nano seconds', 'micro seconds', 'mili seconds']
    time = time_ps * 1000
    for tu in time_units:
        if time < 1000:
            return str(time)+' '+tu

        time = time/1000
    return str(time_ps)

def check_properties(obj, properties, reserved_properties=None):
    if not reserved_properties:
        reserved_properties = []
    reserved_properties = set(["system", "working_dir_path"]+reserved_properties)
    error_properties = set([property for property in properties.keys() if property not in obj.__dict__.keys()])
    error_properties -= reserved_properties
    for error_property in error_properties:
        close_property = difflib.get_close_matches(error_property, obj.__dict__.keys(), n=1)
        close_property = close_property[0] if close_property else ""
        warnings.warn("Warning: %s is not a recognized property. The most similar property is: %s" % (error_property, close_property))

def create_name(path=None, prefix=None, step=None, name=None):
    """ Return file name.

    Args:
        path (str): Path to the file directory.
        prefix (str): Prefix added to the name of the file.
        step (str):  String added between the **prefix** arg and the **name** arg of the file.
        name (str): Name of the file.

    Returns:
        str: Composed file name.
    """
    name = '' if name is None else name.strip()
    if step:
        if name:
            name = step+'_'+name
        else:
            name = step
    if prefix:
        if name:
            name = prefix+'_'+name
        else:
            name = prefix
    if path:
        if name:
            name = os.path.join(path, name)
        else:
            name = path
    return name

def write_failed_output(file_name):
    with open(file_name, 'w') as f:
        f.write('Error\n')

def rm(file_name):
    file_path = pathlib.Path(file_name)
    try:
        if file_path.exists():
            if file_path.is_dir():
                shutil.rmtree(file_name)
                return file_name
            if file_path.is_file():
                os.remove(file_name)
                return file_name
    except:
        # Giving the file system some time to consolidate
        time.sleep(2)
        if file_path.exists():
            if file_path.is_dir():
                shutil.rmtree(file_name)
                return file_name
            if file_path.is_file():
                os.remove(file_name)
                return file_name
    return None
