#!/usr/bin/env python

"""Settings loader module.

This module contains the classes to read the different formats of the
configuration files.
"""

import yaml
import os
from os.path import join as opj
from tools import file_utils as fu

class YamlReader(object):
    """Configuration file loader for yaml format files.

    Args:
        yaml_path (str): Path to the configuration YAML file.
        system (str): System name from the systems section in the configuration file.
    """

    def __init__(self, yaml_path, system):
        self.yaml_path= os.path.abspath(yaml_path)
        self.system = system
        self.properties = self._read_yaml()
        self.properties[system]['workflow_path'] = fu.get_workflow_path(self.properties[system]['workflow_path'])

    def _read_yaml(self):
        with open(self.yaml_path, 'r') as stream:
            return yaml.safe_load(stream)

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
            rm_tmp (bool): Remove temporal files if provided in the system section of the YAML file.
            log_level (bool): Remove temporal files if provided in the system section of the YAML file.

        Returns:
            dict: Dictionary of properties.
        """
        prop_dic = dict()
        prefix = '' if prefix is None else prefix.strip()

        for key in self.properties:
            if isinstance(self.properties[key], dict):
                if 'paths' in self.properties[key] or 'properties' in self.properties[key]:
                    prop_dic[key] = dict()
                    prop_dic[key]['path']=fu.create_name(path=self.properties[self.system]['workflow_path'], prefix=prefix, step=key)
                    prop_dic[key]['step']= key
                    prop_dic[key]['prefix']= prefix
                    prop_dic[key]['global_log']= global_log
                if 'properties' in self.properties[key] and isinstance(self.properties[key]['properties'], dict):
                    if self.properties[self.system].get('rm_tmp', None):
                        prop_dic[key]['rm_tmp']= self.properties[self.system]['rm_tmp']
                    if self.properties[self.system].get('log_level', None):
                        prop_dic[key]['log_level']= self.properties[self.system]['log_level']
                    prop_dic[key].update(self.properties[self.system].copy())
                    prop_dic[key].update(self.properties[key]['properties'].copy())

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
        #Filtering just paths
        for key in self.properties:
            if isinstance(self.properties[key], dict):
                if 'paths' in self.properties[key]:
                    prop_dic[key]=self.properties[key]['paths'].copy()

        #Solving dependencies and adding workflow and step path
        for key in prop_dic:
            for key2, value in prop_dic[key].iteritems():
                if isinstance(value, basestring) and value.startswith('dependency'):
                    while isinstance(value, basestring) and value.startswith('dependency'):
                        dependency_step=value.split('/')[1]
                        value = prop_dic[value.split('/')[1]][value.split('/')[2]]
                    prop_dic[key][key2] = opj(self.properties[self.system]['workflow_path'], prefix, dependency_step, value)
                elif isinstance(value, basestring) and value.startswith('file:'):
                    prop_dic[key][key2] = value.split(':')[1]
                else:
                    prop_dic[key][key2] = opj(self.properties[self.system]['workflow_path'], prefix, key, value)

        return prop_dic
