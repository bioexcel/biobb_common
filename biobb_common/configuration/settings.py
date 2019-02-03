#!/usr/bin/env python3

"""Settings loader module.

This module contains the classes to read the different formats of the
configuration files.
"""

import yaml
import json
import os
from os.path import join as opj
from biobb_common.tools import file_utils as fu

class ConfReader():
    """Configuration file loader for yaml format files.

    Args:
        config (str): Path to the configuration [YAML|JSON] file or JSON string.
        system (str): System name from the systems section in the configuration file.
    """

    def __init__(self, config=None, system=None):
        if not config:
            config = "{}"
        self.config = config
        self.system = system
        self.properties = self._read_config()
        if self.system:
            self.properties[self.system]['working_dir_path'] = fu.get_working_dir_path(self.properties[self.system].get('working_dir_path'))
        else:
            self.properties['working_dir_path'] = fu.get_working_dir_path(self.properties.get('working_dir_path'))

    def _read_config(self):
        try:
            config_file = os.path.abspath(self.config)
            with open(config_file, 'r') as stream:
                if config_file.lower().endswith((".yaml",".yml")):
                    return yaml.safe_load(stream)
                else:
                    return json.load(stream)
        except:
            return json.loads(self.config)

    def get_working_dir_path(self):
        if self.system:
            return self.properties[self.system].get('working_dir_path')

        return self.properties.get('working_dir_path' )

    def get_prop_dic(self, prefix=None, global_log=None):
        """get_prop_dic() returns the properties dictionary where keys are the
        step names in the configuration YAML file and every value contains another
        nested dictionary containing the keys and values of each step properties section.
        All the paths in the system section are copied in each nested dictionary.
        For each nested dictionary the following keys are added:
            | **path** (*str*): Absolute path to the step working dir.
            | **step** (*str*): Name of the step.
            | **prefix** (*str*): Prefix if provided.
            | **global_log** (*Logger object*): Log from the main workflow.

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
                prop_dic['path']=os.path.join(self.properties[self.system]['working_dir_path'], prefix)
            else:
                prop_dic['path']=os.path.join(self.properties['working_dir_path'],prefix)
            prop_dic['step']= None
            prop_dic['prefix']= prefix
            prop_dic['global_log']= global_log
            prop_dic['system']= self.system
            if self.system:
                prop_dic.update(self.properties[self.system].copy())
            else:
                prop_dic['working_dir_path']=self.properties.get('working_dir_path')

            if 'properties' in self.properties and isinstance(self.properties['properties'], dict):
                prop_dic.update(self.properties['properties'].copy())
                if self.system:
                    if self.properties[self.system].get('log_level', None):
                        prop_dic['log_level']= self.properties[self.system]['log_level']
                else:
                    if self.properties.get('log_level', None):
                        prop_dic['log_level']= self.properties['log_level']
        # There is step name
        else:
            for key in self.properties:
                if isinstance(self.properties[key], dict):
                    if 'paths' in self.properties[key] or 'properties' in self.properties[key]:
                        prop_dic[key] = dict()
                        if self.system:
                            prop_dic[key]['path']=os.path.join(self.properties[self.system]['working_dir_path'], prefix, key)
                        else:
                            prop_dic[key]['path']=os.path.join(self.properties['working_dir_path'],prefix, key)
                        prop_dic[key]['step']= key
                        prop_dic[key]['prefix']= prefix
                        prop_dic[key]['global_log']= global_log
                        prop_dic[key]['system']= self.system
                        if self.system:
                            prop_dic[key].update(self.properties[self.system].copy())
                        else:
                            prop_dic[key]['working_dir_path']=self.properties.get('working_dir_path')
                            prop_dic[key]['can_write_console_log']=self.properties.get('can_write_console_log', True)

                    if ('properties' in self.properties[key]) and isinstance(self.properties[key]['properties'], dict):
                        if self.system:
                            if self.properties[self.system].get('log_level', None):
                                prop_dic[key]['log_level']= self.properties[self.system]['log_level']
                            prop_dic[key]['can_write_console_log']=self.properties[self.system].get('can_write_console_log', True)
                        else:
                            if self.properties.get('log_level', None):
                                prop_dic[key]['log_level']= self.properties['log_level']
                            prop_dic[key]['can_write_console_log']=self.properties.get('can_write_console_log', True)
                        prop_dic[key].update(self.properties[key]['properties'].copy())
        # There is no step name and there is no properties or paths key return input
        if not prop_dic:
            prop_dic = dict()
            prop_dic.update(self.properties)
            if self.system:
                prop_dic['path']=os.path.join(self.properties[self.system]['working_dir_path'], prefix)
            else:
                prop_dic['path']=os.path.join(self.properties['working_dir_path'],prefix)
            prop_dic['step']= None
            prop_dic['prefix']= prefix
            prop_dic['global_log']= global_log
            prop_dic['system']= self.system
            if self.system:
                prop_dic.update(self.properties[self.system].copy())
            else:
                prop_dic['working_dir_path']=self.properties.get('working_dir_path')
                prop_dic['can_write_console_log']=self.properties.get('can_write_console_log', True)


        return prop_dic

    def get_paths_dic(self, prefix=None):
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
        step=False
        #Filtering just paths
        #Properties without step name
        if 'paths' in self.properties:
            step=False
            prop_dic=self.properties['paths'].copy()

        #Properties with name
        else:
            step=True
            for key in self.properties:
                if isinstance(self.properties[key], dict):
                    if 'paths' in self.properties[key]:
                        prop_dic[key]=self.properties[key]['paths'].copy()
                    else:
                        prop_dic[key] = {}

        #Solving dependencies and adding workflow and step path
        #Properties without step name: Do not solving dependencies
        if not step:
            for key2, value in prop_dic.items():
                if isinstance(value, str) and value.startswith('file:'):
                    prop_dic[key2] = value.split(':')[1]
                else:
                    if self.system:
                        prop_dic[key2] = opj(self.properties[self.system]['working_dir_path'], prefix, key, value)
                    else:
                        prop_dic[key2] = opj(self.properties['working_dir_path'], prefix, value)

        #Properties with step name
        else:
            for key in prop_dic:
                for key2, value in prop_dic[key].items():
                    if isinstance(value, str) and value.startswith('dependency'):
                        while isinstance(value, str) and value.startswith('dependency'):
                            dependency_step=value.split('/')[1]
                            value = prop_dic[value.split('/')[1]][value.split('/')[2]]
                        if self.properties.get(self.system):
                            prop_dic[key][key2] = opj(self.properties[self.system]['working_dir_path'], prefix, dependency_step, value)
                        else:
                            prop_dic[key][key2] = opj(self.properties['working_dir_path'], prefix, dependency_step, value)
                    elif isinstance(value, str) and value.startswith('file:'):
                        prop_dic[key][key2] = value.split(':')[1]
                    else:
                        if self.system:
                            prop_dic[key][key2] = opj(self.properties[self.system]['working_dir_path'], prefix, key, value)
                        else:
                            prop_dic[key][key2] = opj(self.properties['working_dir_path'], prefix, key, value)

        return prop_dic
