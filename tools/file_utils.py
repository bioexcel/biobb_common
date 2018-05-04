"""Tools to work with files
"""
import os
import shutil
import glob
import zipfile
import logging
from os.path import join as opj

def create_dir(dir_path):
    """Returns the directory **dir_path** and create it if path does not exist.

    Args:
        dir_path (str): Path to the directory that will be created
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    return dir_path

def get_workflow_path(workflow_path):
    """Return the directory **workflow_path** and create it if workflow_path
    does not exist. If **workflow_path** exists a consecutive numerical suffix
    is added to the end of the **workflow_path** and is returned.

    Args:
        workflow_path (str): Path to the workflow results
    """
    if not os.path.exists(dir_path):
        return dir_path

    cont = 1
    while os.path.exists(dir_path):
        dir_path = dir_path.rstrip('\\/0123456789_') + '_' + str(cont)
        cont += 1
    return dir_path

def remove_temp_files(endswith_list, source_dir=None):
    removed_list = []
    source_dir = os.getcwd() if source_dir is None else os.path.abspath(source_dir)
    files = [f for f in os.listdir(source_dir) if os.path.isfile(os.path.join(source_dir, f))]
    for f in files:
        if f.endswith(tuple(endswith_list)):
            os.remove(f)
            removed_list.append(f)
    return removed_list

def zip_top(top_file, zip_file):
    top_dir = os.path.abspath(os.path.dirname(top_file))
    files = glob.iglob(os.path.join(top_dir, "*.itp"))
    if os.path.abspath(os.getcwd()) != top_dir:
        files = glob.iglob(os.path.join(os.getcwd(), "*.itp"))
    with zipfile.ZipFile(zip_file, 'w') as zip:
        for f in files:
            zip.write(f, arcname=os.path.basename(f))
        zip.write(top_file, arcname=os.path.basename(top_file))

def zip_list(zip_file, file_list):
    """ Compress all files listed in **file_list** into **zip_file** zip file.

    Args:
        zip_file: Output compressed zip file.
        file_list: Input list of files to be compressed.
    """
    with zipfile.ZipFile(zip_file, 'w') as zip:
        for f in file_list:
            zip.write(f, arcname=os.path.basename(f))

def unzip_top(zip_file, dest_dir=None, top_file=None):
    if dest_dir is None:
        dest_dir = os.getcwd()
    with zipfile.ZipFile(zip_file) as zip:
        zip_name = next(name for name in zip.namelist() if name.endswith(".top"))
        zip.extractall(path=dest_dir)
    if top_file is not None:
        shutil.copyfile(os.path.join(dest_dir, zip_name), os.path.basename(top_file))
        return top_file
    return zip_name


def get_logs(path=None, prefix=None, step=None, console=False, level='INFO'):
    """ Get the error and and out Python Logger objects.

    Args:
        path (str): (current working directory) Path to the log file directory.
        prefix (str): Prefix added to the name of the log file.
        step (str):  String added between the **prefix** arg and the name of the log file.
        console (bool): (False) If True, show log in the execution terminal.
        level (str): ('INFO') Set Logging level. ['CRITICAL','ERROR','WARNING','INFO','DEBUG','NOTSET']
    """
    path = path if path else os.getcwd()
    out_log_path = create_name(path=path, prefix=prefix, step=step, name='log.out')
    err_log_path = create_name(path=path, prefix=prefix, step=step, name='log.err')

    # Create logging format
    logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")

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
    out_Logger.addHandler(out_fileHandler)
    err_Logger.addHandler(err_fileHandler)

    # Create consoleHandler
    consoleHandler = logging.StreamHandler()
    # Asign format to consoleHandler
    consoleHandler.setFormatter(logFormatter)

    # Asign consoleHandler to logging objects as aditional output
    if console:
        out_Logger.addHandler(consoleHandler)
        err_Logger.addHandler(consoleHandler)

    # Set logging level level
    out_Logger.setLevel(level)
    err_Logger.setLevel(level)
    return out_Logger, err_Logger

def human_readable_time(time_ps):
    """Transform **time_ps** to a human readable string.

    Args:
        time_ps (int): Time in pico seconds.
    """
    time_units = ['femto seconds','pico seconds','nano seconds','micro seconds','mili seconds']
    time = time_ps * 1000
    for tu in time_units:
        if time < 1000:
            return str(time)+' '+tu
        else:
            time = time/1000
    return str(time_ps)

def create_name(path=None, prefix=None, step=None, name=None):
    """ Return file name.

    Args:
        path (str): Path to the file directory.
        prefix (str): Prefix added to the name of the file.
        step (str):  String added between the **prefix** arg and the **name** arg of the file.
        name (str): Name of the file.
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
            name = opj(path, name)
        else:
            name = path
    return name
