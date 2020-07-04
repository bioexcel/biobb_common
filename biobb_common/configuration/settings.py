#!/usr/bin/env python3

"""Settings loader module.

This module contains the classes to read the different formats of the configuration files.

The configuration files are composed by paths to the files and properties. There are several common properties for all
the building blocks.


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
from biobb_common.tools import file_utils as fu

GALAXY_CHARACTER_MAP = {                       
        '__gt__':'>',                          
        '__lt__': '<',                         
        '__sq__': "'",                         
        '__dq__': '"',                         
        '__ob__': '[',                         
        '__cb__': ']',                         
        '__oc__': '{',  
        '__cc__': '}',  
        '__cn__': '\n',
        '__cr__': '\r',
        '__tc__': '\t',
        '__pd__': '#'  
}                      
                       
def trans_galaxy_charmap(input_str):
    '''Fixes escape characters introduced by Galaxy on Json inputs'''
    for ch in GALAXY_CHARACTER_MAP:
        input_str = input_str.replace(ch, GALAXY_CHARACTER_MAP[ch])
    return input_str

class ConfReader:
    """Configuration file loader for yaml format files.

    Args:
        config (str): Path to the configuration [YAML|JSON] file or JSON string.
        system (str): System name from the systems section in the configuration file.
    """

    def __init__(self, config: str = None, system: str = None):
        if not config:
            config = "{}"
        self.config = config
        self.system = system
        self.properties = self._read_config()
        if self.system:
            self.properties[self.system]['working_dir_path'] = fu.get_working_dir_path(self.properties[self.system].get('working_dir_path'), restart=self.properties[self.system].get('restart', False))
        else:
            self.properties['working_dir_path'] = fu.get_working_dir_path(self.properties.get('working_dir_path'), restart=self.properties.get('restart', False))

    def _read_config(self):
        try:
            config_file = str(Path(self.config).resolve())
            with open(config_file) as stream:
                if config_file.lower().endswith((".yaml",".yml")):
                    return yaml.safe_load(stream)
                else:
                    return json.load(stream)
        except:
            return json.loads(trans_galaxy_charmap(self.config))

    def get_working_dir_path(self) -> str:
        if self.system:
            return self.properties[self.system].get('working_dir_path')

        return self.properties.get('working_dir_path')

    def get_prop_dic(self, prefix: str = None, global_log: logging.Logger = None) -> dict:
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

        Args:
            prefix (str): Prefix if provided.
            global_log (:obj:Logger): Log from the main workflow.

        Returns:
            dict: Dictionary of properties.
        """
        prop_dic = dict()
        prefix = '' if prefix is None else prefix.strip()

        # There is no step
        if 'paths' in self.properties or 'properties' in self.properties:
            prop_dic = dict()
            if self.system:
                prop_dic['path'] = str(Path(self.properties[self.system]['working_dir_path']).joinpath(prefix))
            else:
                prop_dic['path'] = str(Path(self.properties['working_dir_path']).joinpath(prefix))
            prop_dic['step'] = None
            prop_dic['prefix'] = prefix
            prop_dic['global_log'] = global_log
            prop_dic['system'] = self.system
            if self.system:
                prop_dic.update(self.properties[self.system].copy())
            else:
                prop_dic['working_dir_path'] = self.properties.get('working_dir_path')
                prop_dic['restart'] = self.properties.get('restart', False)
                prop_dic['remove_tmp'] = self.properties.get('remove_tmp', True)

            if 'properties' in self.properties and isinstance(self.properties['properties'], dict):
                prop_dic.update(self.properties['properties'].copy())
                if self.system:
                    if self.properties[self.system].get('log_level', None):
                        prop_dic['log_level'] = self.properties[self.system]['log_level']
                else:
                    if self.properties.get('log_level', None):
                        prop_dic['log_level'] = self.properties['log_level']
        # There is step name
        else:
            for key in self.properties:
                if isinstance(self.properties[key], dict):
                    if 'paths' in self.properties[key] or 'properties' in self.properties[key]:
                        prop_dic[key] = dict()
                        if self.system:
                            prop_dic[key]['path'] = str(Path(self.properties[self.system]['working_dir_path']).joinpath(prefix, key))
                        else:
                            prop_dic[key]['path'] = str(Path(self.properties['working_dir_path']).joinpath(prefix, key))
                        prop_dic[key]['step'] = key
                        prop_dic[key]['prefix'] = prefix
                        prop_dic[key]['global_log'] = global_log
                        prop_dic[key]['system'] = self.system
                        if self.system:
                            prop_dic[key].update(self.properties[self.system].copy())
                        else:
                            prop_dic[key]['working_dir_path'] = self.properties.get('working_dir_path')
                            prop_dic[key]['can_write_console_log'] = self.properties.get('can_write_console_log', True)
                            prop_dic[key]['restart'] = self.properties.get('restart', False)
                            prop_dic[key]['remove_tmp'] = self.properties.get('remove_tmp', True)

                    if ('properties' in self.properties[key]) and isinstance(self.properties[key]['properties'], dict):
                        if self.system:
                            if self.properties[self.system].get('log_level', None):
                                prop_dic[key]['log_level'] = self.properties[self.system]['log_level']
                            prop_dic[key]['can_write_console_log'] = self.properties[self.system].get('can_write_console_log', True)
                        else:
                            if self.properties.get('log_level', None):
                                prop_dic[key]['log_level'] = self.properties['log_level']
                            prop_dic[key]['can_write_console_log'] = self.properties.get('can_write_console_log', True)
                        prop_dic[key].update(self.properties[key]['properties'].copy())

        # There is no step name and there is no properties or paths key return input
        if not prop_dic:
            prop_dic = dict()
            prop_dic.update(self.properties)
            if self.system:
                prop_dic['path'] = str(Path(self.properties[self.system]['working_dir_path']).joinpath(prefix))
            else:
                prop_dic['path'] = str(Path(self.properties['working_dir_path']).joinpath(prefix))
            prop_dic['step'] = None
            prop_dic['prefix'] = prefix
            prop_dic['global_log'] = global_log
            prop_dic['system'] = self.system
            if self.system:
                prop_dic.update(self.properties[self.system].copy())
            else:
                prop_dic['working_dir_path'] = self.properties.get('working_dir_path')
                prop_dic['can_write_console_log'] = self.properties.get('can_write_console_log', True)
                prop_dic['restart'] = self.properties.get('restart', False)
                prop_dic['remove_tmp'] = self.properties.get('remove_tmp', True)

        return prop_dic

    def get_paths_dic(self, prefix: str = None) -> dict:
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
        prefix = '' if prefix is None else prefix.strip()
        # Filtering just paths
        # Properties without step name
        if 'paths' in self.properties:
            step = False
            prop_dic = self.properties['paths'].copy()

        # Properties with name
        else:
            step = True
            for key in self.properties:
                if isinstance(self.properties[key], dict):
                    if 'paths' in self.properties[key]:
                        prop_dic[key] = self.properties[key]['paths'].copy()
                    else:
                        prop_dic[key] = {}

        # Solving dependencies and adding workflow and step path
        # Properties without step name: Do not solving dependencies
        if not step:
            for key2, value in prop_dic.items():
                if isinstance(value, str) and value.startswith('file:'):
                    prop_dic[key2] = value.split(':')[1]
                else:
                    if self.system:
                        prop_dic[key2] = str(Path(self.properties[self.system]['working_dir_path']).joinpath(prefix, key, value))
                    else:
                        prop_dic[key2] = str(Path(self.properties['working_dir_path']).joinpath(prefix, value))

        # Properties with step name
        else:
            for key in prop_dic:
                for key2, value in prop_dic[key].items():
                    if isinstance(value, str) and value.startswith('dependency'):
                        while isinstance(value, str) and value.startswith('dependency'):
                            dependency_step = value.split('/')[1]
                            value = prop_dic[value.split('/')[1]][value.split('/')[2]]
                        if self.properties.get(self.system):
                            prop_dic[key][key2] = str(Path(self.properties[self.system]['working_dir_path']).joinpath(prefix, dependency_step, value))
                        else:
                            prop_dic[key][key2] = str(Path(self.properties['working_dir_path']).joinpath(prefix, dependency_step, value))
                    elif isinstance(value, str) and value.startswith('file:'):
                        prop_dic[key][key2] = value.split(':')[1]
                    else:
                        if self.system:
                            prop_dic[key][key2] = str(Path(self.properties[self.system]['working_dir_path']).joinpath(prefix, key, value))
                        else:
                            prop_dic[key][key2] = str(Path(self.properties['working_dir_path']).joinpath(prefix, key, value))

        return prop_dic
