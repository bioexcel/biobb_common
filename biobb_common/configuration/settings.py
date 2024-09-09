#!/usr/bin/env python3

"""Settings loader module.

This module contains the classes to read the different formats of the configuration files.

The configuration files are composed by paths to the files and properties. There are several common properties for all
the building blocks.

Some yaml files contain a tool key with the name of the tool to be executed inside the step key. The tool key is used
by the resp API to identify the tool to be executed. This reader will ignore the tool key.


Syntax:
    - **property** (*dataType*) - (Default value) Short description.

Available Workflow properties:
    - **working_dir_path** (*str*) - (Current working dir) Workflow output directory.
    - **can_write_console_log** (*bool*) - (True) Output log to console.
    - **restart** (*bool*) - (False) Do not execute steps if output files are already created.
    - **remove_tmp** (*bool*) - (True) Remove temporal files.

Available common step properties: (Each Biobb step also has their specific properties)
    - **can_write_console_log** (*bool*) - (True) Overwrite **can_write_console_log** workflow property on this step.
    - **restart** (*bool*) - (False) Overwrite **restart** workflow property on this step.
    - **remove_tmp** (*bool*) - (True) Overwrite **remove_tmp** workflow property on this step.

Available common step properties for containerized applications:
    - **container_path** (*string*) - (None)  Path to the binary executable of your container.
    - **container_image** (*string*) - (None) Container Image identifier.
    - **container_volume_path** (*string*) - (None) Path to an internal directory in the container.
    - **container_working_dir** (*string*) - (None) Path to the internal CWD in the container.
    - **container_user_id** (*string*) - (None) User number id to be mapped inside the container.
    - **container_shell_path** (*string*) - ("/bin/bash") Path to the binary executable of the container shell.
"""

import yaml
import json
import logging
from pathlib import Path
from copy import deepcopy
from biobb_common.tools import file_utils as fu
from typing import Dict, Any, Optional

GALAXY_CHARACTER_MAP = {
    "__gt__": ">",
    "__lt__": "<",
    "__sq__": "'",
    "__dq__": '"',
    "__ob__": "[",
    "__cb__": "]",
    "__oc__": "{",
    "__cc__": "}",
    "__cn__": "\n",
    "__cr__": "\r",
    "__tc__": "\t",
    "__pd__": "#"
}


def trans_galaxy_charmap(input_str):
    """Fixes escape characters introduced by Galaxy on Json inputs"""
    for ch in GALAXY_CHARACTER_MAP:
        input_str = input_str.replace(ch, GALAXY_CHARACTER_MAP[ch])
    return input_str


class ConfReader:
    """Configuration file loader for yaml format files.

    Args:
        config (str): Path to the configuration [YAML|JSON] file or JSON string.
        system (str): System name from the systems section in the configuration file.
    """

    def __init__(self, config: Optional[str] = None, **kwargs):
        self.properties = self._read_config(config)
        self.default_properties = self._get_default_properties()
        self.global_properties = self._get_global_properties()

    def _read_config(self, config: Optional[str] = None) -> Dict[str, Any]:
        """_read_config() reads the configuration file and returns a dictionary.
        """
        if not config:
            return dict()
        config_dict = dict()
        config_tokens = str(config).split("#")
        if (json_string := config_tokens[0].strip()).startswith("{"):
            config_dict = json.loads(trans_galaxy_charmap(json_string))
        else:
            config_file_path = Path(config_tokens[0]).resolve()
            if not config_file_path.exists():
                raise FileNotFoundError(f"Configuration file {config_file_path} not found.")
            with open(config_file_path) as stream:
                try:
                    config_dict = yaml.safe_load(stream) or {}
                except yaml.YAMLError as yaml_error:
                    try:
                        config_dict = json.load(stream) or {}
                    except json.JSONDecodeError as json_error:
                        raise Exception(f"Error reading configuration file {config_file_path} is not a valid YAML: {yaml_error} or a valid JSON: {json_error}")

        # Read just one step specified in the configuration file path
        # i.e: Read just Editconf step from workflow_configuration.yaml file
        # "/home/user/workflow_configuration.yaml#Editconf"
        if len(config_tokens) > 1:
            return config_dict[config_tokens[1]]

        return config_dict

    def _get_default_properties(self) -> Dict[str, Any]:
        """_get_default_properties() returns the default properties of the configuration file.

        Returns:
            dict: Dictionary of default properties.
        """

        return {
            "path": None,
            "step": None,
            "prefix": None,
            "global_log": None,
            "can_write_console_log": True,
            "working_dir_path": str(fu.get_working_dir_path()),
            "restart": False,
            "remove_tmp": True,
            "sandbox_path": str(Path.cwd())
        }

    def _get_global_properties(self) -> Dict[str, Any]:
        """_get_global_properties() returns the global properties of the configuration file.

        Returns:
            dict: Dictionary of global properties.
        """
        # Add default properties to the global properties
        global_properties = deepcopy(self.default_properties)
        global_properties.update(deepcopy((self.properties.get("global_properties") or {})))
        return global_properties

    def _get_step_properties(self, key: str = "", prefix: str = "", global_log: Optional[logging.Logger] = None) -> Dict[str, Any]:
        """_get_step_properties() returns the properties of the configuration file.

        Args:
            global_properties (dict): Global properties.
            key (str): Step name.
            prefix (str): Prefix if provided.
            global_log (Logger): Log from the main workflow.

        Returns:
            dict: Dictionary of properties.
        """
        prop_dic = dict()
        prop_dic.update(deepcopy(self.global_properties))
        prop_dic["step"] = key
        prop_dic["prefix"] = prefix
        prop_dic["global_log"] = global_log
        prop_dic["working_dir_path"] = fu.get_working_dir_path(working_dir_path=prop_dic.get("working_dir_path", None), restart=prop_dic.get("restart", False))
        prop_dic["path"] = str(Path(prop_dic["working_dir_path"]).joinpath(prefix, key))
        if key:
            prop_dic["tool"] = self.properties[key].get("tool", None)
            prop_dic.update(deepcopy((self.properties[key].get("properties") or {})))
        else:
            prop_dic["tool"] = self.properties.get("tool", None)
            prop_dic.update(deepcopy((self.properties.get("properties") or {})))

        return prop_dic

    def get_prop_dic(self, prefix: str = "", global_log: Optional[logging.Logger] = None) -> Dict[str, Any]:
        """get_prop_dic() returns the properties dictionary where keys are the
        step names in the configuration YAML file and every value contains another
        nested dictionary containing the keys and values of each step properties section.
        All the paths in the system section are copied in each nested dictionary.
        For each nested dictionary the following keys are added:
            | **path** (*str*): Absolute path to the step working dir.
            | **step** (*str*): Name of the step.
            | **prefix** (*str*): Prefix if provided.
            | **global_log** (*Logger object*): Log from the main workflow.
            | **restart** (*bool*): Restart from previous execution.
            | **remove_tmp** (*bool*): Remove temporal files.
            | **sandbox_path** (*str*) - ("./") Parent path to the sandbox directory.

        Args:
            prefix (str): Prefix if provided.
            global_log (:obj:Logger): Log from the main workflow.

        Returns:
            dict: Dictionary of properties.
        """

        prop_dic: Dict[str, Any] = dict()
        for key in self.properties:
            if key in ["global_properties", "paths", "properties", "tool"]:
                continue
            prop_dic[key] = self._get_step_properties(key=key, prefix=prefix, global_log=global_log)

        if not prop_dic:
            return self._get_step_properties(prefix=prefix, global_log=global_log)

        return prop_dic

    # def get_prop_dic(self, prefix: Optional[str] = None, global_log: Optional[logging.Logger] = None) -> Dict[str, Any]:
    #     """get_prop_dic() returns the properties dictionary where keys are the
    #     step names in the configuration YAML file and every value contains another
    #     nested dictionary containing the keys and values of each step properties section.
    #     All the paths in the system section are copied in each nested dictionary.
    #     For each nested dictionary the following keys are added:
    #         | **path** (*str*): Absolute path to the step working dir.
    #         | **step** (*str*): Name of the step.
    #         | **prefix** (*str*): Prefix if provided.
    #         | **global_log** (*Logger object*): Log from the main workflow.
    #         | **restart** (*bool*): Restart from previous execution.
    #         | **remove_tmp** (*bool*): Remove temporal files.
    #         | **sandbox_path** (*str*) - ("./") Parent path to the sandbox directory.

    #     Args:
    #         prefix (str): Prefix if provided.
    #         global_log (:obj:Logger): Log from the main workflow.

    #     Returns:
    #         dict: Dictionary of properties.
    #     """

    #     prop_dic: Dict[str, Any] = dict()
    #     prefix = "" if prefix is None else prefix.strip()

    #     # There is no step
    #     if "paths" in self.properties or "properties" in self.properties:
    #         prop_dic = dict()
    #         prop_dic["path"] = str(Path(self.properties["working_dir_path"]).joinpath(prefix))
    #         prop_dic["step"] = None
    #         prop_dic["prefix"] = prefix
    #         prop_dic["global_log"] = global_log
    #         prop_dic["working_dir_path"] = self.properties.get("working_dir_path")
    #         prop_dic["restart"] = self.properties.get("restart", False)
    #         prop_dic["remove_tmp"] = self.properties.get("remove_tmp", True)
    #         prop_dic["sandbox_path"] = self.properties.get("sandbox_path", Path.cwd())

    #         if "properties" in self.properties and isinstance(
    #             self.properties["properties"], dict
    #         ):
    #             prop_dic.update(self.properties["properties"].copy())
    #             if self.properties.get("", None):
    #                 prop_dic[""] = self.properties[""]
    #     # There is step name
    #     else:
    #         for key in self.properties:
    #             if isinstance(self.properties[key], dict):
    #                 if (
    #                     "paths" in self.properties[key]
    #                     or "properties" in self.properties[key]
    #                 ):
    #                     prop_dic[key] = dict()
    #                     prop_dic[key]["path"] = str(
    #                         Path(self.properties["working_dir_path"]).joinpath(
    #                             prefix, key
    #                         )
    #                     )
    #                     prop_dic[key]["step"] = key
    #                     prop_dic[key]["prefix"] = prefix
    #                     prop_dic[key]["global_log"] = global_log
    #                     prop_dic[key]["working_dir_path"] = self.properties.get(
    #                         "working_dir_path"
    #                     )
    #                     prop_dic[key][
    #                         "can_write_console_log"
    #                     ] = self.properties.get("can_write_console_log", True)
    #                     prop_dic[key]["restart"] = self.properties.get(
    #                         "restart", False
    #                     )
    #                     prop_dic[key]["remove_tmp"] = self.properties.get(
    #                         "remove_tmp", True
    #                     )

    #                 if ("properties" in self.properties[key]) and isinstance(
    #                     self.properties[key]["properties"], dict
    #                 ):
    #                     if self.properties.get("", None):
    #                         prop_dic[key][""] = self.properties[
    #                             ""
    #                         ]
    #                     prop_dic[key][
    #                         "can_write_console_log"
    #                     ] = self.properties.get("can_write_console_log", True)
    #                     prop_dic[key].update(self.properties[key]["properties"].copy())

    #     # There is no step name and there is no properties or paths key: return input
    #     if not prop_dic:
    #         prop_dic = dict()
    #         prop_dic.update(self.properties)
    #         prop_dic["path"] = str(
    #             Path(self.properties["working_dir_path"]).joinpath(prefix)
    #         )
    #         prop_dic["step"] = None
    #         prop_dic["prefix"] = prefix
    #         prop_dic["global_log"] = global_log
    #         prop_dic["working_dir_path"] = self.properties.get("working_dir_path")
    #         prop_dic["can_write_console_log"] = self.properties.get(
    #             "can_write_console_log", True
    #         )
    #         prop_dic["restart"] = self.properties.get("restart", False)
    #         prop_dic["remove_tmp"] = self.properties.get("remove_tmp", True)

    #     return prop_dic

    def get_paths_dic(self, prefix: Optional[str] = None) -> dict:
        """get_paths_dic() returns the paths dictionary where keys are the
        step names in the configuration YAML file and every value contains another
        nested dictionary containing the keys and values of each step paths section.
        All the paths starting with 'dependency' are resolved. If the path starts
        with the string 'file:' nothing is done, however if the path starts with
        any other string path is prefixed with the absolute step path.

        Args:
            prefix (str): Prefix if provided.

        Returns:
            dict: Dictionary of paths.
        """
        prop_dic = dict()
        prefix = "" if prefix is None else prefix.strip()
        # Filtering just paths
        # Properties without step name
        if "paths" in self.properties:
            step = False
            prop_dic = self.properties["paths"].copy()

        # Properties with name
        else:
            step = True

            for key in self.properties:
                if isinstance(self.properties[key], dict):
                    if "paths" in self.properties[key]:
                        prop_dic[key] = self.properties[key]["paths"].copy()
                    else:
                        prop_dic[key] = {}

        # Solving dependencies and adding workflow and step path
        # Properties without step name: Do not solving dependencies
        if not step:
            for key2, value in prop_dic.items():
                if isinstance(value, str) and value.startswith("file:"):
                    prop_dic[key2] = value.split(":")[1]
                else:
                    prop_dic[key2] = str(
                        Path(self.properties["working_dir_path"]).joinpath(
                            prefix, value
                        )
                    )

        # Properties with step name
        else:

            for key in prop_dic:
                for key2, value in prop_dic[key].items():
                    if isinstance(value, str) and value.startswith("dependency"):
                        dependency_step = value.split("/")[1]
                        while isinstance(value, str) and value.startswith("dependency"):
                            dependency_step = value.split("/")[1]
                            value = prop_dic[value.split("/")[1]][value.split("/")[2]]
                        prop_dic[key][key2] = str(
                            Path(self.properties["working_dir_path"]).joinpath(
                                prefix, dependency_step, value
                            )
                        )
                    elif isinstance(value, str) and value.startswith("file:"):
                        prop_dic[key][key2] = value.split(":")[1]
                    else:
                        prop_dic[key][key2] = str(
                            Path(self.properties["working_dir_path"]).joinpath(
                                prefix, key, value
                            )
                        )

        return prop_dic
