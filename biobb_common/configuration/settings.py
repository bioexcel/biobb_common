#!/usr/bin/env python3

"""Settings loader module.

This module contains the classes to read the different formats of the configuration files.

The configuration files are composed by paths to the files and properties. There are several common properties for all
the building blocks.

Some yaml files contain a tool key with the name of the tool to be executed inside the step key. The tool key is used
by the resp API to identify the tool to be executed.


Syntax:
    - **property** (*dataType*) - (Default value) Short description.

Available common step properties: (Each Biobb step also has their specific properties)
    - **tool** (*str*) - (None) Name of the tool to be executed, mostly used by the biobbAPI.
    - **global_log** (*Logger object*) - (None) Log from the main workflow.
    - **prefix** (*str*) - (None) Prefix if provided.
    - **step** (*str*) - (None) Name of the step.
    - **path** (*str*) - ('') Absolute path to the step working dir.
    - **working_dir_path** (*str*) - (Current working dir) Workflow output directory.
    - **global_properties_list** (*list*) - ([]) List of global properties.
"""

import yaml
import json
import logging
from pathlib import Path
from copy import deepcopy
from biobb_common.tools import file_utils as fu
from typing import Dict, Any, Optional

GALAXY_CHARACTER_MAP = {
    "__gt__": ">", "__lt__": "<", "__sq__": "'", "__dq__": '"', "__ob__": "[", "__cb__": "]",
    "__oc__": "{", "__cc__": "}", "__cn__": "\n", "__cr__": "\r", "__tc__": "\t", "__pd__": "#"}


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

    def __init__(self, config: Optional[str] = None, *args, **kwargs):
        self.properties = self._read_config(config)
        self.global_properties = self._get_global_properties()
        self.working_dir_path = fu.get_working_dir_path(working_dir_path=self.global_properties.get("working_dir_path", None), restart=self.global_properties.get("restart", False))

    def get_working_dir_path(self) -> str:
        """get_working_dir_path() returns the working directory path.

        Returns:
            str: Working directory path.
        """
        return self.working_dir_path

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

    def _get_global_properties(self) -> Dict[str, Any]:
        """_get_global_properties() returns the global properties of the configuration file.

        Returns:
            dict: Dictionary of global properties.
        """
        # Add default properties to the global properties
        return deepcopy((self.properties.get("global_properties") or {}))

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
        prop_dic["global_properties_list"] = list(self.global_properties.keys())
        prop_dic["step"] = key
        prop_dic["prefix"] = prefix
        prop_dic["global_log"] = global_log
        prop_dic["working_dir_path"] = self.working_dir_path
        prop_dic["path"] = str(Path(self.working_dir_path).joinpath(prefix, key))
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
            | **tool** (*str*): Name of the tool to be executed, mostly used by the biobbAPI.
            | **working_dir_path** (*str*): Workflow output directory.
            | **global_properties_list** (*list*): List of global properties.

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

    def get_paths_dic(self, prefix: str = "") -> Dict[str, Any]:
        paths_dic: Dict[str, Any] = dict()
        for key in self.properties:
            if key in ["global_properties", "paths", "properties", "tool"]:
                continue
            paths_dic[key] = self._get_step_paths(key=key, prefix=prefix)

        if not paths_dic:
            return self._get_step_paths(prefix=prefix)

        return paths_dic

    def _get_step_paths(self, key: str = "", prefix: str = "") -> Dict[str, Any]:
        step_paths_dic = dict()
        if key:
            paths_dic = self.properties[key].get("paths", {})
        else:
            paths_dic = self.properties.get("paths", {})
        for file_key, path_value in paths_dic.items():
            if path_value.startswith("file:"):
                step_paths_dic[file_key] = path_value.replace("file:", "")
                continue
            step_paths_dic[file_key] = str(Path(self.working_dir_path).joinpath(prefix, self._solve_dependency(key, path_value)))

        return step_paths_dic

    def _solve_dependency(self, step, dependency_str: str) -> str:
        """_solve_dependency() solves the dependency of a path in the configuration file.
        """
        dependency_tokens = dependency_str.strip().split("/")
        if dependency_tokens[0] != "dependency":
            return str(Path(step).joinpath(dependency_str))

        if not step:
            raise Exception("Step name is required to solve dependency")

        return str(Path(dependency_tokens[1]).joinpath(self.properties.get(dependency_tokens[1], {}).get('paths', {}).get(dependency_tokens[2], "")))
