"""Tools to work with files
"""
import os
import shutil
import glob
import zipfile
import logging
from os.path import join as opj

def create_dir(dir_path):
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    return dir_path

def get_workflow_path(dir_path):
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


def get_logs(path, prefix=None, step=None, console=False, level='INFO'):
    out_log_path = create_name(name='log.out', step=step, prefix=prefix, path=path)
    err_log_path = create_name(name='log.err', step=step, prefix=prefix, path=path)
    logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    out_Logger = logging.getLogger(out_log_path)
    out_Logger.setLevel(level)
    err_Logger = logging.getLogger(err_log_path)
    err_Logger.setLevel(level)

    #Creating and formating FileHandler
    out_fileHandler = logging.FileHandler(out_log_path, mode='a', encoding=None, delay=False)
    err_fileHandler = logging.FileHandler(err_log_path, mode='a', encoding=None, delay=False)
    out_fileHandler.setFormatter(logFormatter)
    err_fileHandler.setFormatter(logFormatter)

    #Asign FileHandler
    out_Logger.addHandler(out_fileHandler)
    err_Logger.addHandler(err_fileHandler)

    #Creating and formating consoleHandler
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)

    # Adding console aditional output
    if console:
        out_Logger.addHandler(consoleHandler)
        err_Logger.addHandler(consoleHandler)

    out_Logger.setLevel(10)
    err_Logger.setLevel(10)
    return out_Logger, err_Logger

def human_readable_time(time_ps):
    time_units = ['femto seconds','pico seconds','nano seconds','micro seconds','mili seconds']
    time = time_ps * 1000
    for tu in time_units:
        if time < 1000:
            return str(time)+' '+tu
        else:
            time = time/1000
    return str(time_ps)

def create_name(name=None, step=None, prefix=None, path=None):
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
