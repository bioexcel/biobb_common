"""Module containing the BiobbObject generic parent class."""
import importlib
import difflib
import typing
import warnings
from pathlib import Path
from sys import platform
import shutil
from biobb_common.tools import file_utils as fu
from biobb_common.command_wrapper import cmd_wrapper


class BiobbObject:
    """
    | biobb_common BiobbObject
    | Generic parent class for the rest of the Biobb clases.
    | The BiobbOject class contains all the properties and methods that are common to all the biobb blocks.

    Args:
        properties (dict - Python dictionary object containing the tool parameters, not input/output files):
            * **dev** (*str*) - (None) Adding additional options to command line.
            * **remove_tmp** (*bool*) - (True) [WF property] Remove temporal files.
            * **restart** (*bool*) - (False) [WF property] Do not execute if output files exist.
            * **container_path** (*str*) - (None)  Path to the binary executable of your container.
            * **container_image** (*str*) - (None) Container Image identifier.
            * **container_volume_path** (*str*) - ("/data") Path to an internal directory in the container.
            * **container_working_dir** (*str*) - (None) Path to the internal CWD in the container.
            * **container_user_id** (*str*) - (None) User number id to be mapped inside the container.
            * **container_shell_path** (*str*) - ("/bin/bash -c") Path to the binary executable of the container shell.
            * **container_generic_command** (*str*) - ("run") Which command typically run or exec will be used to execute your image.
    """

    def __init__(self, properties: dict = None, **kwargs) -> None:
        properties = properties or {}

        # Input/Output files
        self.io_dict = {"in": {}, "out": {}}

        # container Specific
        self.container_path = properties.get('container_path')
        self.container_image = properties.get('container_image')
        self.container_volume_path = properties.get('container_volume_path', '/data')
        self.container_working_dir = properties.get('container_working_dir')
        self.container_user_id = properties.get('container_user_id')
        self.container_shell_path = properties.get('container_shell_path', '/bin/bash -c')
        self.container_generic_command = properties.get('container_generic_command', 'run')

        # stage
        self.stage_io_dict = {"in": {}, "out": {}}


        # Properties common in all BB
        self.binary_path = properties.get('binary_path')
        self.can_write_console_log = properties.get('can_write_console_log', True)
        self.global_log = properties.get('global_log', None)
        self.out_log = None
        self.err_log = None
        self.prefix = properties.get('prefix', None)
        self.step = properties.get('step', None)
        self.path = properties.get('path', '')
        self.remove_tmp = properties.get('remove_tmp', True)
        self.restart = properties.get('restart', False)
        self.cmd = []
        self.environment = None
        self.return_code = None
        self.tmp_files = []

        self.dev = properties.get('dev', None)
        self.check_extensions = properties.get('check_extensions', True)
        self.check_var_typing = properties.get('check_var_typing', True)
        self.doc_arguments_dict, self.doc_properties_dict = fu.get_doc_dicts(self.__doc__)

        try:
            self.version = importlib.import_module(self.__module__.split('.')[0]).__version__
        except:
            self.version = None
    # print(self.__module__)
    # def check_paths(self):
    #     self.__module__
    #     self.check_extensions
    #     self.out_log


    def check_properties(self, properties: dict, reserved_properties: dict = None):
        if not reserved_properties:
            reserved_properties = []
        reserved_properties = set(["system", "working_dir_path"] + reserved_properties)
        error_properties = set([prop for prop in properties.keys() if prop not in self.__dict__.keys()])
        error_properties -= reserved_properties
        for error_property in error_properties:
            close_property = difflib.get_close_matches(error_property, self.__dict__.keys(), n=1, cutoff=0.01)
            close_property = close_property[0] if close_property else ""
            warnings.warn("Warning: %s is not a recognized property. The most similar property is: %s" % (
                error_property, close_property))

    def check_restart(self) -> bool:
        if self.version:
            fu.log(f"Executing {self.__module__} Version: {self.version}", self.out_log, self.global_log)

        if self.restart:
            if fu.check_complete_files(self.io_dict["out"].values()):
                fu.log('Restart is enabled, this step: %s will the skipped' % self.step, self.out_log, self.global_log)
                return True
        return False

    def stage_files(self):
        if self.container_path:
            unique_dir = str(Path(fu.create_unique_dir()).resolve())
            self.stage_io_dict = {"in": {}, "out": {}, "unique_dir": unique_dir}

            # IN files COPY and assign INTERNAL PATH
            for file_ref, file_path in self.io_dict["in"].items():
                if file_path:
                    if Path(file_path).exists():
                        shutil.copy2(file_path, unique_dir)
                        fu.log(f'Copy: {file_path} to {unique_dir}', self.out_log)
                        self.stage_io_dict["in"][file_ref] = str(Path(self.container_volume_path).joinpath(Path(file_path).name))
                    else:
                        # Default files in GMXLIB path like gmx_solvate -> input_solvent_gro_path (spc216.gro)
                        self.stage_io_dict["in"][file_ref] = file_path

            # OUT files assign INTERNAL PATH
            for file_ref, file_path in self.io_dict["out"].items():
                if file_path:
                    self.stage_io_dict["out"][file_ref] = str(Path(self.container_volume_path).joinpath(Path(file_path).name))
        else:
            self.stage_io_dict = self.io_dict

    def create_cmd_line(self):
        # Not documented and not listed option, only for devs
        if self.dev:
            fu.log(f'Adding development options: {self.dev}', self.out_log, self.global_log)
            self.cmd += self.dev.split()

        self.container_path = self.container_path or ''
        host_volume = self.stage_io_dict.get("unique_dir")
        if self.container_path.endswith('singularity'):
            fu.log('Using Singularity image %s' % self.container_image, self.out_log, self.global_log)
            if not Path(self.container_image).exists():
                fu.log(f"{self.container_image} does not exist trying to pull it", self.out_log, self.global_log)
                container_image_name = str(Path(self.container_image).with_suffix('.sif').name)
                singularity_pull_cmd = [self.container_path, 'pull', '--name', container_image_name, self.container_image]
                try:
                    from biobb_common.command_wrapper import cmd_wrapper
                    cmd_wrapper.CmdWrapper(singularity_pull_cmd, self.out_log).launch()
                    if Path(container_image_name).exists():
                        self.container_image = container_image_name
                    else:
                        raise FileNotFoundError
                except:
                    fu.log(f"{' '.join(singularity_pull_cmd)} not found", self.out_log, self.global_log)
                    raise FileNotFoundError
            singularity_cmd = [self.container_path, self.container_generic_command, '-e', '--bind', host_volume + ':' + self.container_volume_path,
                               self.container_image]

            # If we are working on a mac remove -e option because is still no available
            if platform == "darwin":
                if '-e' in singularity_cmd:
                    singularity_cmd.remove('-e')

            if not self.cmd and not self.container_shell_path:
                fu.log("WARNING: The command-line is empty your container should know what to do automatically.", self.out_log, self.global_log)
            else:
                cmd = ['"' + " ".join(self.cmd) + '"']
                singularity_cmd.append(self.container_shell_path)
                singularity_cmd.extend(cmd)
            self.cmd = singularity_cmd

        elif self.container_path.endswith('docker'):
            fu.log('Using Docker image %s' % self.container_image, self.out_log, self.global_log)
            docker_cmd = [self.container_path, self.container_generic_command]
            if self.container_working_dir:
                docker_cmd.append('-w')
                docker_cmd.append(self.container_working_dir)
            if self.container_volume_path:
                docker_cmd.append('-v')
                docker_cmd.append(host_volume + ':' + self.container_volume_path)
            if self.container_user_id:
                docker_cmd.append('--user')
                docker_cmd.append(self.container_user_id)

            docker_cmd.append(self.container_image)

            if not self.cmd and not self.container_shell_path:
                fu.log("WARNING: The command-line is empty your container should know what to do automatically.", self.out_log, self.global_log)
            else:
                cmd = ['"' + " ".join(self.cmd) + '"']
                docker_cmd.append(self.container_shell_path)
                docker_cmd.extend(cmd)
            self.cmd = docker_cmd

        elif self.container_path.endswith('pcocc'):
            # pcocc run -I racov56:pmx cli.py mutate -h
            fu.log('Using pcocc image %s' % self.container_image, self.out_log, self.global_log)
            pcocc_cmd = [self.container_path, self.container_generic_command, '-I', self.container_image]
            if self.container_working_dir:
                pcocc_cmd.append('--cwd')
                pcocc_cmd.append(self.container_working_dir)
            if self.container_volume_path:
                pcocc_cmd.append('--mount')
                pcocc_cmd.append(host_volume + ':' + self.container_volume_path)
            if self.container_user_id:
                pcocc_cmd.append('--user')
                pcocc_cmd.append(self.container_user_id)

            if not self.cmd and not self.container_shell_path:
                fu.log("WARNING: The command-line is empty your container should know what to do automatically.", self.out_log, self.global_log)
            else:
                cmd = ['\\"' + " ".join(self.cmd) + '\\"']
                pcocc_cmd.append(self.container_shell_path)
                pcocc_cmd.extend(cmd)
            self.cmd = pcocc_cmd

        else:
            pass
            # fu.log('Not using any container', self.out_log, self.global_log)

    def execute_command(self):
        self.return_code = cmd_wrapper.CmdWrapper(self.cmd, self.out_log, self.err_log, self.global_log, self.environment).launch()

    def copy_to_host(self):
        if not self.container_path:
            return

        # OUT files COPY
        for file_ref, file_path in self.stage_io_dict["out"].items():
            if file_path:
                container_file_path = str(Path(self.stage_io_dict["unique_dir"]).joinpath(Path(file_path).name))
                if Path(container_file_path).exists():
                    shutil.copy2(container_file_path, self.io_dict["out"][file_ref])


    def run_biobb(self):
        self.create_cmd_line()
        self.execute_command()

    def remove_tmp_files(self):
        if self.remove_tmp:
            fu.rm_file_list(self.tmp_files, self.out_log)
