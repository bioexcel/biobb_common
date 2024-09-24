"""Module containing the BiobbObject generic parent class."""
import os
import importlib
import difflib
import typing
from typing import Optional, Mapping, Set, Union, Dict, List, Any
import warnings
from pathlib import Path
from sys import platform
import shutil
from pydoc import locate
from biobb_common.tools import file_utils as fu
from biobb_common.command_wrapper import cmd_wrapper
from logging import Logger


class BiobbObject:
    """
    | biobb_common BiobbObject
    | Generic parent class for the rest of the Biobb clases.
    | The BiobbOject class contains all the properties and methods that are common to all the biobb blocks.

    Args:
        properties (dict - Python dictionary object containing the tool parameters, not input/output files):

            * **io_dict** (*dict*) - ({}) Input/Output files dictionary.
            * **container_path** (*str*) - (None)  Path to the binary executable of your container.
            * **container_image** (*str*) - (None) Container Image identifier.
            * **container_volume_path** (*str*) - ("/data") Path to an internal directory in the container.
            * **container_working_dir** (*str*) - (None) Path to the internal CWD in the container.
            * **container_user_id** (*str*) - (None) User number id to be mapped inside the container.
            * **container_shell_path** (*str*) - ("/bin/bash -c") Path to the binary executable of the container shell.
            * **container_generic_command** (*str*) - ("run") Which command typically run or exec will be used to execute your image.
            * **stage_io_dict** (*dict*) - ({}) Stage Input/Output files dictionary.
            * **sandbox_path** (*str*) - ("./") [WF property] Parent path to the sandbox directory.
            * **disable_sandbox** (*bool*) - (False) Disable the use of temporal unique directories aka sandbox. Only for local execution.
            * **global_properties_list** (*list*) - ([]) List of global properties.
            * **chdir_sandbox** (*bool*) - (False) Change directory to the sandbox using just file names in the command line. Only for local execution.
            * **binary_path** (*str*) - ('') Path to the binary executable.
            * **can_write_console_log** (*bool*) - (True) Can write console log.
            * **global_log** (*Logger object*) - (None) Log from the main workflow.
            * **out_log** (*Logger object*) - (None) Log from the step.
            * **err_log** (*Logger object*) - (None) Error log from the step.
            * **out_log_path** (*str*) - (None) Path to the log file.
            * **err_log_path** (*str*) - (None) Path to the error log file.
            * **disable_logs** (*bool*) - (False) Disable the logs.
            * **prefix** (*str*) - (None) Prefix if provided.
            * **step** (*str*) - (None) Name of the step.
            * **path** (*str*) - ('') Absolute path to the step working dir.
            * **remove_tmp** (*bool*) - (True) [WF property] Remove temporal files.
            * **restart** (*bool*) - (False) [WF property] Do not execute if output files exist.
            * **cmd** (*list*) - ([]) Command line list, NOT read from the dictionary.
            * **return_code** (*int*) - (0) Return code of the command execution, NOT read from the dictionary.
            * **timeout** (*int*) - (None) Timeout for the execution of the command.
            * **tmp_files** (*list*) - ([]) List of temporal files, NOT read from the dictionary.
            * **env_vars_dict** (*dict*) - ({}) Environment Variables Dictionary.
            * **shell_path** (*str*) - ("/bin/bash") Path to the binary executable of the shell.
            * **dev** (*str*) - (None) Development options.
            * **check_extensions** (*bool*) - (True) Check extensions of the input/output files.
            * **check_var_typing** (*bool*) - (True) Check typing of the input/output files.
            * **locals_var_dict** (*dict*) - ({}) Local variables dictionary.
            * **doc_arguments_dict** (*dict*) - ({}) Documentation arguments dictionary.
            * **doc_properties_dict** (*dict*) - ({}) Documentation properties dictionary.


    """

    def __init__(self, properties=None, **kwargs) -> None:  # type: ignore
        properties = properties or {}

        # Input/Output files
        self.io_dict: Dict[str, Dict] = {"in": {}, "out": {}}

        # container Specific
        self.container_path: Optional[str] = properties.get("container_path")
        self.container_image: str = properties.get("container_image", '')
        self.container_volume_path: str = properties.get("container_volume_path", "/data")
        self.container_working_dir: Optional[str] = properties.get("container_working_dir")
        self.container_user_id: Optional[str] = properties.get("container_user_id")
        self.container_shell_path: str = properties.get("container_shell_path", "/bin/bash -c")
        self.container_generic_command: str = properties.get("container_generic_command", "run")

        # stage
        self.stage_io_dict: Dict[str, Any] = {"in": {}, "out": {}}
        self.sandbox_path: Union[str, Path] = properties.get("sandbox_path", Path().cwd())
        self.disable_sandbox: bool = properties.get("disable_sandbox", False)

        # Properties common in all BB
        self.global_properties_list: List[str] = properties.get("global_properties_list", [])
        self.chdir_sandbox: bool = properties.get("chdir_sandbox", False)
        self.binary_path: str = properties.get("binary_path", '')
        self.can_write_console_log: bool = properties.get("can_write_console_log", True)
        self.global_log: Optional[Logger] = properties.get("global_log", None)
        self.out_log: Optional[Logger] = None
        self.err_log: Optional[Logger] = None
        self.out_log_path: Optional[Union[Path, str]] = properties.get("out_log_path", None)
        self.err_log_path: Optional[Union[Path, str]] = properties.get("err_log_path", None)
        self.disable_logs: bool = properties.get("disable_logs", False)
        self.prefix: Optional[str] = properties.get("prefix", None)
        self.step: Optional[str] = properties.get("step", None)
        self.path: str = properties.get("path", "")
        self.remove_tmp: bool = properties.get("remove_tmp", True)
        self.restart: bool = properties.get("restart", False)
        self.cmd: List[str] = []
        self.return_code: int = 0
        self.timeout: Optional[int] = properties.get("timeout", None)
        self.tmp_files: List[Union[str, Path]] = []
        self.env_vars_dict: typing.Dict = properties.get("env_vars_dict", {})
        self.shell_path: typing.Union[str, Path] = properties.get("shell_path", os.getenv("SHELL", "/bin/bash"))
        self.dev: Optional[str] = properties.get("dev", None)
        self.check_extensions: bool = properties.get("check_extensions", True)
        self.check_var_typing: bool = properties.get("check_var_typing", True)
        self.locals_var_dict: Mapping[str, str] = dict()
        self.doc_arguments_dict, self.doc_properties_dict = fu.get_doc_dicts(self.__doc__)

        try:
            self.version = importlib.import_module(
                self.__module__.split(".")[0]
            ).__version__
        except Exception:
            self.version = None

        if self.disable_sandbox and self.remove_tmp:
            self.remove_tmp = False
            fu.log("WARNING: Disabling remove_tmp because disable_sandbox is enabled", self.out_log, self.global_log)

    def check_arguments(
        self, output_files_created: bool = False, raise_exception: bool = True
    ):
        for argument, argument_dict in self.doc_arguments_dict.items():
            fu.check_argument(
                path=Path(self.locals_var_dict[argument])
                if self.locals_var_dict.get(argument)
                else None,
                argument=argument,
                optional=argument_dict.get("optional", False),
                module_name=self.__module__,
                input_output=argument_dict.get(
                    "input_output", "").lower().strip(),
                output_files_created=output_files_created,
                extension_list=list(argument_dict.get("formats")),
                check_extensions=self.check_extensions,
                raise_exception=raise_exception,
                out_log=self.out_log,
            )
        if output_files_created:
            fu.log("", self.out_log, self.global_log)

    def check_properties(
        self,
        properties: dict,
        reserved_properties: Optional[Set[str]] = None,
        check_var_typing: bool = False,
    ):
        if not reserved_properties:
            reserved_properties = set()
        reserved_properties = {"system", "working_dir_path", "tool"}.union(reserved_properties)
        reserved_properties = reserved_properties.union(set(self.global_properties_list))
        error_properties = set([prop for prop in properties.keys() if prop not in self.__dict__.keys()])

        # Check types
        if check_var_typing and self.doc_properties_dict:
            for prop, value in properties.items():
                if self.doc_properties_dict.get(prop):
                    property_type = self.doc_properties_dict[prop].get("type")
                    classinfo: object = locate(property_type).__class__
                    if classinfo == type:
                        classinfo = locate(property_type)
                    if not isinstance(value, classinfo):  # type: ignore
                        warnings.warn(
                            f"Warning: {prop} property type not recognized. Got {type(value)} Expected {locate(property_type)}"
                        )

        error_properties = set(
            [prop for prop in properties.keys() if prop not in self.__dict__.keys()]
        )
        error_properties -= reserved_properties
        for error_property in error_properties:
            close_property = difflib.get_close_matches(
                error_property, self.__dict__.keys(), n=1, cutoff=0.01
            )
            close_property = close_property[0] if close_property else ""
            warnings.warn(
                "Warning: %s is not a recognized property. The most similar property is: %s"
                % (error_property, close_property)
            )

    def check_restart(self) -> bool:
        if self.version:
            fu.log(
                f"Module: {self.__module__} Version: {self.version}",
                self.out_log,
                self.global_log,
            )

        if self.restart:
            if fu.check_complete_files(self.io_dict["out"].values()):  # type: ignore
                fu.log(
                    "Restart is enabled, this step: %s will the skipped" % self.step,
                    self.out_log,
                    self.global_log,
                )
                return True
        return False

    def stage_files(self):
        if self.disable_sandbox:
            self.stage_io_dict = self.io_dict.copy()
            self.stage_io_dict["unique_dir"] = os.getcwd()
            return

        unique_dir = str(Path(fu.create_unique_dir(path=str(self.sandbox_path), prefix="sandbox_", out_log=self.out_log)).resolve())
        self.stage_io_dict = {"in": {}, "out": {}, "unique_dir": unique_dir}

        # IN files COPY and assign INTERNAL PATH
        for file_ref, file_path in self.io_dict.get("in", {}).items():
            if file_path:
                if Path(file_path).exists():
                    shutil.copy2(file_path, unique_dir)
                    fu.log(f"Copy: {file_path} to {unique_dir}", self.out_log)
                    # Container
                    if self.container_path:
                        self.stage_io_dict["in"][file_ref] = str(
                            Path(self.container_volume_path).joinpath(
                                Path(file_path).name
                            )
                        )
                    # Local
                    else:
                        self.stage_io_dict["in"][file_ref] = str(
                            Path(unique_dir).joinpath(Path(file_path).name)
                        )
                        if self.chdir_sandbox:
                            self.stage_io_dict["in"][file_ref] = str(
                                Path(file_path).name
                            )
                else:
                    # Default files in GMXLIB path like gmx_solvate -> input_solvent_gro_path (spc216.gro)
                    self.stage_io_dict["in"][file_ref] = file_path

        # OUT files assign INTERNAL PATH
        for file_ref, file_path in self.io_dict.get("out", {}).items():
            if file_path:
                # Container
                if self.container_path:
                    self.stage_io_dict["out"][file_ref] = str(
                        Path(self.container_volume_path).joinpath(
                            Path(file_path).name)
                    )
                # Local
                else:
                    self.stage_io_dict["out"][file_ref] = str(
                        Path(unique_dir).joinpath(Path(file_path).name)
                    )
                    if self.chdir_sandbox:
                        self.stage_io_dict["out"][file_ref] = str(
                            Path(file_path).name)

    def create_cmd_line(self) -> None:
        # Not documented and not listed option, only for devs
        if self.dev:
            fu.log(
                f"Adding development options: {self.dev}", self.out_log, self.global_log
            )
            self.cmd += self.dev.split()

        # Containers
        host_volume: str = str(self.stage_io_dict.get("unique_dir", ''))
        self.container_path = self.container_path or ""
        # Singularity
        if self.container_path.endswith("singularity"):
            fu.log(
                "Using Singularity image %s" % self.container_image,
                self.out_log,
                self.global_log,
            )
            if not Path(self.container_image).exists():
                fu.log(
                    f"{self.container_image} does not exist trying to pull it",
                    self.out_log,
                    self.global_log,
                )
                container_image_name = str(
                    Path(self.container_image).with_suffix(".sif").name
                )
                singularity_pull_cmd = [
                    self.container_path,
                    "pull",
                    "--name",
                    container_image_name,
                    self.container_image,
                ]
                try:
                    from biobb_common.command_wrapper import cmd_wrapper

                    cmd_wrapper.CmdWrapper(
                        singularity_pull_cmd, self.shell_path, self.out_log
                    ).launch()
                    if Path(container_image_name).exists():
                        self.container_image = container_image_name
                    else:
                        raise FileNotFoundError
                except FileNotFoundError:
                    fu.log(
                        f"{' '.join(singularity_pull_cmd)} not found",
                        self.out_log,
                        self.global_log,
                    )
                    raise FileNotFoundError
            singularity_cmd = [
                self.container_path,
                self.container_generic_command,
                "-e",
            ]

            if self.env_vars_dict:
                singularity_cmd.append("--env")
                singularity_cmd.append(
                    ",".join(
                        f"{env_var_name}='{env_var_value}'"
                        for env_var_name, env_var_value in self.env_vars_dict.items()
                    )
                )

            singularity_cmd.extend(
                [
                    "--bind",
                    host_volume + ":" + self.container_volume_path,
                    self.container_image,
                ]
            )

            # If we are working on a mac remove -e option because is still no available
            if platform == "darwin":
                if "-e" in singularity_cmd:
                    singularity_cmd.remove("-e")

            if not self.cmd and not self.container_shell_path:
                fu.log(
                    "WARNING: The command-line is empty your container should know what to do automatically.",
                    self.out_log,
                    self.global_log,
                )
            else:
                cmd = ['"' + " ".join(self.cmd) + '"']
                singularity_cmd.append(self.container_shell_path)
                singularity_cmd.extend(cmd)
            self.cmd = singularity_cmd
        # Docker
        elif self.container_path.endswith("docker"):
            fu.log(
                "Using Docker image %s" % self.container_image,
                self.out_log,
                self.global_log,
            )
            docker_cmd = [self.container_path, self.container_generic_command]
            if self.env_vars_dict:
                for env_var_name, env_var_value in self.env_vars_dict.items():
                    docker_cmd.append("-e")
                    docker_cmd.append(f"{env_var_name}='{env_var_value}'")
            if self.container_working_dir:
                docker_cmd.append("-w")
                docker_cmd.append(self.container_working_dir)
            if self.container_volume_path:
                docker_cmd.append("-v")
                docker_cmd.append(host_volume + ":" +
                                  self.container_volume_path)
            if self.container_user_id:
                docker_cmd.append("--user")
                docker_cmd.append(self.container_user_id)

            docker_cmd.append(self.container_image)

            if not self.cmd and not self.container_shell_path:
                fu.log(
                    "WARNING: The command-line is empty your container should know what to do automatically.",
                    self.out_log,
                    self.global_log,
                )
            else:
                cmd = ['"' + " ".join(self.cmd) + '"']
                docker_cmd.append(self.container_shell_path)
                docker_cmd.extend(cmd)
            self.cmd = docker_cmd
        # Pcocc
        elif self.container_path.endswith("pcocc"):
            # pcocc run -I racov56:pmx cli.py mutate -h
            fu.log(
                "Using pcocc image %s" % self.container_image,
                self.out_log,
                self.global_log,
            )
            pcocc_cmd = [
                self.container_path,
                self.container_generic_command,
                "-I",
                self.container_image,
            ]
            if self.container_working_dir:
                pcocc_cmd.append("--cwd")
                pcocc_cmd.append(self.container_working_dir)
            if self.container_volume_path:
                pcocc_cmd.append("--mount")
                pcocc_cmd.append(host_volume + ":" +
                                 self.container_volume_path)
            if self.container_user_id:
                pcocc_cmd.append("--user")
                pcocc_cmd.append(self.container_user_id)

            if not self.cmd and not self.container_shell_path:
                fu.log(
                    "WARNING: The command-line is empty your container should know what to do automatically.",
                    self.out_log,
                    self.global_log,
                )
            else:
                cmd = ['\\"' + " ".join(self.cmd) + '\\"']
                pcocc_cmd.append(self.container_shell_path)
                pcocc_cmd.extend(cmd)
            self.cmd = pcocc_cmd
        # Local execution
        else:
            pass
            # fu.log('Not using any container', self.out_log, self.global_log)

    def execute_command(self):

        cwd = os.getcwd()
        if self.chdir_sandbox:
            os.chdir(self.stage_io_dict["unique_dir"])

        self.return_code = cmd_wrapper.CmdWrapper(
            cmd=self.cmd,
            shell_path=self.shell_path,
            out_log=self.out_log,
            err_log=self.err_log,
            global_log=self.global_log,
            env=self.env_vars_dict,
            timeout=self.timeout
        ).launch()

        if self.chdir_sandbox:
            os.chdir(cwd)

    def copy_to_host(self):
        for file_ref, file_path in self.stage_io_dict["out"].items():
            if file_path:
                sandbox_file_path = str(
                    Path(self.stage_io_dict["unique_dir"]).joinpath(
                        Path(file_path).name
                    )
                )
                if Path(sandbox_file_path).exists():
                    # Dest file exists
                    if Path(self.io_dict["out"][file_ref]).exists():
                        # Dest file exists and is NOT the same as the source file
                        if not Path(sandbox_file_path).samefile(
                            Path(self.io_dict["out"][file_ref])
                        ):
                            shutil.copy2(
                                sandbox_file_path, self.io_dict["out"][file_ref]
                            )
                    # Dest file does not exist
                    else:
                        shutil.copy2(sandbox_file_path,
                                     self.io_dict["out"][file_ref])

    def run_biobb(self):
        self.create_cmd_line()
        self.execute_command()

    def remove_tmp_files(self):
        if self.remove_tmp:
            fu.rm_file_list(self.tmp_files, self.out_log)
