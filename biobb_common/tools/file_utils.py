"""Tools to work with files
"""
import difflib
import functools
import logging
import os
import pathlib
import re
import shutil
import uuid
import warnings
import zipfile
from sys import platform
from pathlib import Path
import typing


def create_dir(dir_path: str) -> str:
    """Returns the directory **dir_path** and create it if path does not exist.

    Args:
        dir_path (str): Path to the directory that will be created.

    Returns:
        str: Directory dir path.
    """
    if not Path(dir_path).exists():
        Path(dir_path).mkdir(exist_ok=True, parents=True)
    return str(Path(dir_path))


def create_unique_dir(path: str = '', prefix: str = '', number_attempts: int = 10, out_log: logging.Logger = None, ) -> str:
    """Create a directory with a prefix + computed unique name. If the
    computed name collides with an existing file name it attemps
    **number_attempts** times to create another unique id and create
    the directory with the new name.

    Args:
        path (str): ('') Parent path of the new directory.
        prefix (str): ('') String to be added before the computed unique dir name.
        number_attempts (int): (10) number of times creating the directory if there's a name conflict.
        out_log (logger): (None) Python logger object.

    Returns:
        str: Directory dir path.
    """
    new_dir = prefix + str(uuid.uuid4())
    if path:
        new_dir = str(Path(path).joinpath(new_dir))
    for i in range(number_attempts):
        try:
            oldumask = os.umask(0)
            Path(new_dir).mkdir(mode=0o777, parents=True, exist_ok=False)
            if out_log:
                out_log.info('%s directory successfully created' % new_dir)
            os.umask(oldumask)
            return new_dir
        except OSError:
            if out_log:
                out_log.info(new_dir + ' Already exists')
                out_log.info('Retrying %i times more' % (number_attempts - i))
            new_dir = prefix + str(uuid.uuid4())
            if path:
                new_dir = str(Path(path).joinpath(new_dir))
            if out_log:
                out_log.info('Trying with: ' + new_dir)
    raise FileExistsError


def get_working_dir_path(working_dir_path: str = None, restart: bool = False) -> str:
    """Return the directory **working_dir_path** and create it if working_dir_path
    does not exist. If **working_dir_path** exists a consecutive numerical suffix
    is added to the end of the **working_dir_path** and is returned.

    Args:
        working_dir_path (str): Path to the workflow results.
        restart (bool): If step result exists do not execute the step again.

    Returns:
        str: Path to the workflow results directory.
    """
    if not working_dir_path:
        return str(Path.cwd().resolve())

    working_dir_path = str(Path(working_dir_path).resolve())

    if (not Path(working_dir_path).exists()) or restart:
        return str(Path(working_dir_path))

    cont = 1
    while Path(working_dir_path).exists():
        working_dir_path = str(working_dir_path).rstrip('\\/0123456789_') + '_' + str(cont)
        cont += 1
    return str(working_dir_path)


def zip_list(zip_file: str, file_list: typing.Iterable[str], out_log: logging.Logger = None):
    """ Compress all files listed in **file_list** into **zip_file** zip file.

    Args:
        zip_file (str): Output compressed zip file.
        file_list (:obj:`list` of :obj:`str`): Input list of files to be compressed.
        out_log (:obj:`logging.Logger`): Input log object.
    """
    file_list.sort()
    with zipfile.ZipFile(zip_file, 'w') as zip_f:
        inserted = []
        for index, f in enumerate(file_list):
            base_name = Path(f).name
            if base_name in inserted:
                base_name = 'file_' + str(index) + '_' + base_name
            inserted.append(base_name)
            zip_f.write(f, arcname=base_name)
    if out_log:
        out_log.info("Adding:")
        out_log.info(str(file_list))
        out_log.info("to: " + str(Path(zip_file).resolve()))


def unzip_list(zip_file: str, dest_dir: str = None, out_log: logging.Logger = None) -> typing.List[str]:
    """ Extract all files in the zipball file and return a list containing the
        absolute path of the extracted files.

    Args:
        zip_file (str): Input compressed zip file.
        dest_dir (str): Path to directory where the files will be extracted.
        out_log (:obj:`logging.Logger`): Input log object.

    Returns:
        :obj:`list` of :obj:`str`: List of paths of the extracted files.
    """
    with zipfile.ZipFile(zip_file, 'r') as zip_f:
        zip_f.extractall(path=dest_dir)
        file_list = [str(Path(dest_dir).joinpath(f)) for f in zip_f.namelist()]

    if out_log:
        out_log.info("Extracting: " + str(Path(zip_file).resolve()))
        out_log.info("to:")
        out_log.info(str(file_list))

    return file_list


def search_topology_files(top_file: str, out_log: logging.Logger = None) -> typing.List[str]:
    """ Search the top and itp files to create a list of the topology files

    Args:
        top_file (str): Topology GROMACS top file.
        out_log (:obj:`logging.Logger`): Input log object.

    Returns:
        :obj:`list` of :obj:`str`: List of paths of the extracted files.
    """
    top_dir_name = str(Path(top_file).parent)
    file_list = []
    pattern = re.compile(r"#include\s+\"(.+)\"")
    if Path(top_file).exists():
        with open(top_file) as tf:
            for line in tf:
                include_file = pattern.match(line.strip())
                if include_file:
                    found_file = str(Path(top_dir_name).joinpath(include_file.group(1)))
                    file_list += search_topology_files(found_file, out_log)
    else:
        if out_log:
            out_log.info("Ignored file %s" % top_file)
        return file_list
    return file_list + [top_file]


def zip_top(zip_file: str, top_file: str, out_log: logging.Logger = None) -> typing.List[str]:
    """ Compress all *.itp and *.top files in the cwd into **zip_file** zip file.

    Args:
        zip_file (str): Output compressed zip file.
        top_file (str): Topology TOP GROMACS file.
        out_log (:obj:`logging.Logger`): Input log object.

    Returns:
        :obj:`list` of :obj:`str`: List of compressed paths.
    """

    file_list = search_topology_files(top_file, out_log)
    zip_list(zip_file, file_list, out_log)
    return file_list


def unzip_top(zip_file: str, out_log: logging.Logger = None) -> str:
    """ Extract all files in the zip_file and copy the file extracted ".top" file to top_file.

    Args:
        zip_file (str): Input topology zipball file path.
        out_log (:obj:`logging.Logger`): Input log object.

    Returns:
        str: Path to the extracted ".top" file.

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
    return 4 * ' '


def get_logs(path: str = None, prefix: str = None, step: str = None, can_write_console: bool = True, level: str = 'INFO', light_format: bool = False) -> typing.Tuple[logging.Logger, logging.Logger]:
    """ Get the error and and out Python Logger objects.

    Args:
        path (str): (current working directory) Path to the log file directory.
        prefix (str): Prefix added to the name of the log file.
        step (str):  String added between the **prefix** arg and the name of the log file.
        can_write_console (bool): (False) If True, show log in the execution terminal.
        level (str): ('INFO') Set Logging level. ['CRITICAL','ERROR','WARNING','INFO','DEBUG','NOTSET']
        light_format (bool): (False) Minimalist log format.

    Returns:
        :obj:`tuple` of :obj:`logging.Logger` and :obj:`logging.Logger`: Out and err Logger objects.
    """
    prefix = prefix if prefix else ''
    step = step if step else ''
    path = path if path else str(Path.cwd())

    out_log_path = create_name(path=path, prefix=prefix, step=step, name='log.out')
    err_log_path = create_name(path=path, prefix=prefix, step=step, name='log.err')

    # If logfile exists create a new one adding a number at the end
    if Path(out_log_path).exists():
        name = 'log.out'
        cont = 1
        while Path(out_log_path).exists():
            name = name.split('.')[0].rstrip('\\/0123456789_') + str(cont) + '.out'
            out_log_path = create_name(path=path, prefix=prefix, step=step, name=name)
            cont += 1
    if Path(err_log_path).exists():
        name = 'log.err'
        cont = 1
        while Path(err_log_path).exists():
            name = name.split('.')[0].rstrip('\\/0123456789_') + str(cont) + '.err'
            err_log_path = create_name(path=path, prefix=prefix, step=step, name=name)
            cont += 1

    # Create dir if it not exists
    create_dir(str(Path(out_log_path).resolve().parent))

    # Create logging format
    logFormatter = logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s")
    if light_format:
        logFormatter = logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S")
    # Create logging objects
    out_Logger = logging.getLogger(out_log_path)
    err_Logger = logging.getLogger(err_log_path)

    # Create FileHandler
    out_fileHandler = logging.FileHandler(out_log_path, mode='a', encoding=None, delay=False)
    err_fileHandler = logging.FileHandler(err_log_path, mode='a', encoding=None, delay=False)

    # Asign format to FileHandler
    out_fileHandler.setFormatter(logFormatter)
    err_fileHandler.setFormatter(logFormatter)

    # Assign FileHandler to logging object
    if not len(out_Logger.handlers):
        out_Logger.addHandler(out_fileHandler)
        err_Logger.addHandler(err_fileHandler)

    # Create consoleHandler
    consoleHandler = logging.StreamHandler()
    # Assign format to consoleHandler
    consoleHandler.setFormatter(logFormatter)

    # Assign consoleHandler to logging objects as aditional output
    if can_write_console and len(out_Logger.handlers) < 2:
        out_Logger.addHandler(consoleHandler)
        err_Logger.addHandler(consoleHandler)

    # Set logging level level
    out_Logger.setLevel(level)
    err_Logger.setLevel(level)
    return out_Logger, err_Logger


def launchlogger(func):
    @functools.wraps(func)
    def wrapper_log(*args, **kwargs):
        args[0].out_log, args[0].err_log = get_logs(path=args[0].path, prefix=args[0].prefix, step=args[0].step,
                                                    can_write_console=args[0].can_write_console_log)
        value = func(*args, **kwargs)
        handlers = args[0].out_log.handlers[:]  # Create a copy [:] of the handler list to be able to modify it while we are iterating
        for handler in handlers:
            handler.close()
            args[0].out_log.removeHandler(handler)
        handlers = args[0].err_log.handlers[:]  # Create a copy [:] of the handler list to be able to modify it while we are iterating
        for handler in handlers:
            handler.close()
            args[0].err_log.removeHandler(handler)
        return value

    return wrapper_log


def log(string: str, local_log: logging.Logger = None, global_log: logging.Logger = None):
    """Checks if log exists

    Args:
        string (str): Message to log.
        local_log (:obj:`logging.Logger`): local log object.
        global_log (:obj:`logging.Logger`): global log object.

    """
    if local_log:
        local_log.info(string)
    if global_log:
        global_log.info(get_logs_prefix() + string)


def human_readable_time(time_ps: int) -> str:
    """Transform **time_ps** to a human readable string.

    Args:
        time_ps (int): Time in pico seconds.

    Returns:
        str: Human readable time.
    """
    time_units = ['femto seconds', 'pico seconds', 'nano seconds', 'micro seconds', 'mili seconds']
    t = time_ps * 1000
    for tu in time_units:
        if t < 1000:
            return str(t) + ' ' + tu

        t /= 1000
    return str(time_ps)


def check_properties(obj: object, properties: dict, reserved_properties: dict = None):
    if not reserved_properties:
        reserved_properties = []
    reserved_properties = set(["system", "working_dir_path"] + reserved_properties)
    error_properties = set([prop for prop in properties.keys() if prop not in obj.__dict__.keys()])
    error_properties -= reserved_properties
    for error_property in error_properties:
        close_property = difflib.get_close_matches(error_property, obj.__dict__.keys(), n=1, cutoff=0.01)
        close_property = close_property[0] if close_property else ""
        warnings.warn("Warning: %s is not a recognized property. The most similar property is: %s" % (
            error_property, close_property))


def create_name(path: str = None, prefix: str = None, step: str = None, name: str = None) -> str:
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
            name = step + '_' + name
        else:
            name = step
    if prefix:
        prefix = prefix.replace("/", "_")
        if name:
            name = prefix + '_' + name
        else:
            name = prefix
    if path:
        if name:
            name = str(Path(path).joinpath(name))
        else:
            name = path
    return name


def write_failed_output(file_name: str):
    with open(file_name, 'w') as f:
        f.write('Error\n')


def rm(file_name: str) -> str:
    try:
        file_path = pathlib.Path(file_name)
        if file_path.exists():
            if file_path.is_dir():
                shutil.rmtree(file_name)
                return file_name
            if file_path.is_file():
                Path(file_name).unlink()
                return file_name
    except:
        pass
    return None


def rm_file_list(file_list: typing.Iterable[str], out_log: logging.Logger = None) -> typing.List[str]:
    removed_files = [f for f in file_list if rm(f)]
    if out_log:
        log('Removed: %s' % str(removed_files), out_log)
    return removed_files


def check_complete_files(output_file_list: typing.Iterable[str]) -> bool:
    for output_file in filter(None, output_file_list):
        if not (Path(output_file).is_file() and Path(output_file).stat().st_size > 0):
            return False
    return True


def copy_to_container(container_path: str, container_volume_path: str, io_dict: dict) -> dict:
    if not container_path:
        return io_dict

    unique_dir = str(Path(create_unique_dir()).resolve())
    container_io_dict = {"in": {}, "out": {}, "unique_dir": unique_dir}

    # IN files COPY and assign INTERNAL PATH
    for file_ref, file_path in io_dict["in"].items():
        if file_path:
            shutil.copy2(file_path, unique_dir)
            container_io_dict["in"][file_ref] = str(Path(container_volume_path).joinpath(Path(file_path).name))

    # OUT files assign INTERNAL PATH
    for file_ref, file_path in io_dict["out"].items():
        if file_path:
            container_io_dict["out"][file_ref] = str(Path(container_volume_path).joinpath(Path(file_path).name))

    return container_io_dict


def copy_to_host(container_path: str, container_io_dict: dict, io_dict: dict):
    if not container_path:
        return

    # OUT files COPY
    for file_ref, file_path in container_io_dict["out"].items():
        if file_path:
            container_file_path = str(Path(container_io_dict["unique_dir"]).joinpath(Path(file_path).name))
            if Path(container_file_path).exists():
                shutil.copy2(container_file_path, io_dict["out"][file_ref])


def create_cmd_line(cmd: typing.Iterable[str], container_path: str = '', host_volume: str = None,
                    container_volume: str = None, container_working_dir: str = None,
                    container_user_uid: str = None, container_shell_path: str = None,
                    container_image: str = None, out_log: logging.Logger = None,
                    global_log: logging.Logger = None) -> typing.List[str]:
    container_path = container_path or ''
    if container_path.endswith('singularity'):
        log('Using Singularity image %s' % container_image, out_log, global_log)
        if not Path(container_image).exists():
            log(f"{container_image} does not exist trying to pull it")
            container_image_name = str(Path(container_image).with_suffix('.sif').name)
            singularity_pull_cmd = [container_path, 'pull', '--name', container_image_name, container_image]
            try:
                from biobb_common.command_wrapper import cmd_wrapper
                cmd_wrapper.CmdWrapper(singularity_pull_cmd, out_log).launch()
                if Path(container_image_name).exists():
                    container_image = container_image_name
                else:
                    raise
            except:
                log(f"{' '.join(singularity_pull_cmd)} not found")
                raise
        singularity_cmd = [container_path, 'exec', '-e', '--bind', host_volume + ':' + container_volume, container_image]
        # If we are working on a mac remove -e option because is still no available
        if platform == "darwin":
            if '-e' in singularity_cmd:
                singularity_cmd.remove('-e')

        cmd = ['"' + " ".join(cmd) + '"']
        singularity_cmd.extend([container_shell_path, '-c'])
        return singularity_cmd + cmd

    elif container_path.endswith('docker'):
        log('Using Docker image %s' % container_image, out_log, global_log)
        docker_cmd = [container_path, 'run']
        if container_working_dir:
            docker_cmd.append('-w')
            docker_cmd.append(container_working_dir)
        if container_volume:
            docker_cmd.append('-v')
            docker_cmd.append(host_volume + ':' + container_volume)
        if container_user_uid:
            docker_cmd.append('--user')
            docker_cmd.append(container_user_uid)

        docker_cmd.append(container_image)

        cmd = ['"' + " ".join(cmd) + '"']
        docker_cmd.extend([container_shell_path, '-c'])
        return docker_cmd + cmd

    elif container_path.endswith('pcocc'):
        # pcocc run -I racov56:pmx cli.py mutate -h
        log('Using pcocc image %s' % container_image, out_log, global_log)
        pcocc_cmd = [container_path, 'run', '-I', container_image]
        if container_working_dir:
            pcocc_cmd.append('--cwd')
            pcocc_cmd.append(container_working_dir)
        if container_volume:
            pcocc_cmd.append('--mount')
            pcocc_cmd.append(host_volume + ':' + container_volume)
        if container_user_uid:
            pcocc_cmd.append('--user')
            pcocc_cmd.append(container_user_uid)

        cmd = ['\\"' + " ".join(cmd) + '\\"']
        pcocc_cmd.extend([container_shell_path, '-c'])
        return pcocc_cmd + cmd

    else:
        log('Not using any container', out_log, global_log)
        return cmd
