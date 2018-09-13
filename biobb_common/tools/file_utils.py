"""Tools to work with files
"""
import os
import shutil
import zipfile
import logging
from os.path import join as opj

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

def get_workflow_path(workflow_path=None):
    """Return the directory **workflow_path** and create it if workflow_path
    does not exist. If **workflow_path** exists a consecutive numerical suffix
    is added to the end of the **workflow_path** and is returned.

    Args:
        workflow_path (str): Path to the workflow results.

    Returns:
        str: Path to the workflow results directory.
    """
    if not workflow_path:
        workflow_path = get_workflow_path(opj("/tmp","workflow"))

    if not os.path.exists(workflow_path):
        return workflow_path

    cont = 1
    while os.path.exists(workflow_path):
        workflow_path = workflow_path.rstrip('\\/0123456789_') + '_' + str(cont)
        cont += 1
    return workflow_path

def zip_list(zip_file, file_list, out_log=None):
    """ Compress all files listed in **file_list** into **zip_file** zip file.

    Args:
        zip_file (str): Output compressed zip file.
        file_list (:obj:`list` of :obj:`str`): Input list of files to be compressed.
    """
    with zipfile.ZipFile(zip_file, 'w') as zip_f:
        for f in file_list:
            zip_f.write(f, arcname=os.path.basename(f))
    if out_log:
        out_log.info("Adding:")
        out_log.info(str(file_list))
        out_log.info("to: "+ os.path.abspath(zip_file))

def unzip_list(zip_file, out_log=None):
    """ Extract all files in the zipball file and return a list containing the
        absolute path of the extracted files.

    Args:
        zip_file (str): Input compressed zip file.

    Returns:
        :obj:`list` of :obj:`str`: List of paths of the extracted files.
    """
    with zipfile.ZipFile(zip_file, 'r') as zip_f:
        zip_f.extractall()
        file_list = [os.path.abspath(f) for f in zip_f.namelist()]

    if out_log:
        out_log.info("Extracting: "+ os.path.abspath(zip_file))
        out_log.info("to:")
        out_log.info(str(file_list))

    return file_list

def zip_top(zip_file, out_log=None):
    """ Compress all *.itp and *.top files in the cwd into **zip_file** zip file.

    Args:
        zip_file (str): Output compressed zip file.
    """
    ext_list = [".itp", ".top"]
    file_list = [f for f in os.listdir(os.getcwd()) if os.path.isfile(f) and os.path.splitext(f)[1] in ext_list]
    zip_list(zip_file, file_list, out_log)

def unzip_top(zip_file, top_file, out_log=None):
    """ Extract all files in the zip_file and copy the file extracted ".top" file to top_file.

    Args:
        zip_file (str): Input topology zipball file path.
        top_file (str): Output ".top" file where the extracted ".top" file will be copied.

    Returns:
        :obj:`list` of :obj:`str`: List of extracted files paths.
    """
    top_list = unzip_list(zip_file, out_log)
    original_top = next(name for name in top_list if name.endswith(".top"))
    shutil.move(original_top, top_file)
    if out_log:
        out_log.info("Moving: "+ os.path.abspath(original_top) +' to: '+ os.path.abspath(top_file))

    return top_list


def get_logs_prefix():
    return 22*' '

def get_logs(path=None, prefix=None, step=None, console=False, level='INFO'):
    """ Get the error and and out Python Logger objects.

    Args:
        path (str): (current working directory) Path to the log file directory.
        prefix (str): Prefix added to the name of the log file.
        step (str):  String added between the **prefix** arg and the name of the log file.
        console (bool): (False) If True, show log in the execution terminal.
        level (str): ('INFO') Set Logging level. ['CRITICAL','ERROR','WARNING','INFO','DEBUG','NOTSET']

    Returns:
        :obj:`tuple` of :obj:`Logger` and :obj:`Logger`: Out and err Logger objects.
    """
    path = path if path else os.getcwd()
    out_log_path = create_name(path=path, prefix=prefix, step=step, name='log.out')
    err_log_path = create_name(path=path, prefix=prefix, step=step, name='log.err')

    # Create dir if it not exists
    create_dir(os.path.dirname(os.path.abspath(out_log_path)))

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

    Returns:
        str: Human readable time.
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
            name = opj(path, name)
        else:
            name = path
    return name

def write_failed_output(file_name):
    with open(file_name, 'w') as f:
        f.write('Error\n')
