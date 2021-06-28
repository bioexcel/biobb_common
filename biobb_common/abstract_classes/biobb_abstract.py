#!/usr/bin/env python3

"""Module containing the BiobbAbstract class."""
import os
import urllib.parse
from biobb_common.configuration import settings
from biobb_common.tools import file_utils as fu
from biobb_common.tools.file_utils import launchlogger
from biobb_common.command_wrapper import cmd_wrapper

class BiobbAbstract:
    """
    | biobb_common BiobbAbstract
    | Abstract class to inherited from in the specific biobb classes.
    | Abstract class to inherited from in the specific biobb classes, adding the common properties to all biobbs.

    Args:
        properties (dict - Python dictionary object containing the tool parameters, not input/output files):

            * **can_write_console_log** (*bool*) - (True) Output log to console.
            * **restart** (*bool*) - (False) [WF property] Do not execute if output files exist.
            * **remove_tmp** (*bool*) - (True) [WF property] Remove temporal files.
            * **binary_path** (*str*) - (None) Path to the executable binary.
            * **container_path** (*str*) - (None)  Path to the binary executable of your container.
            * **container_image** (*str*) - ("gromacs/gromacs:latest") Container Image identifier.
            * **container_volume_path** (*str*) - ("/data") Path to an internal directory in the container.
            * **container_working_dir** (*str*) - (None) Path to the internal CWD in the container.
            * **container_user_id** (*str*) - (None) User number id to be mapped inside the container.
            * **container_shell_path** (*str*) - ("/bin/bash") Path to the binary executable of the container shell.
            * **api_base_url (*str*) - (None) Base URL for API biobb execution.
            * **api_launch_url (*str*) - ("launch") Launch URL
            * **api_poll_url (*str*) - ("retrieve/status")
            * **api_retrieve_url (*str*) - ("retrieve/data")

    """

    def __init__(self, properties: dict = None) -> None:
        properties = properties or {}

        # Input/Output files
        self.io_dict = {"in": {}, "out": {}}

        # Properties common in all BB
        self.can_write_console_log = properties.get('can_write_console_log', True)
        self.global_log = properties.get('global_log', None)
        self.prefix = properties.get('prefix', None)
        self.step = properties.get('step', None)
        self.path = properties.get('path', '')
        self.remove_tmp = properties.get('remove_tmp', True)
        self.restart = properties.get('restart', False)

        # Local execution
        self.binary_path = properties.get('binary_path')

        # Container execution
        self.container_path = properties.get('container_path')
        self.container_image = properties.get('container_image')
        self.container_volume_path = properties.get('container_volume_path', '/data')
        self.container_working_dir = properties.get('container_working_dir')
        self.container_user_id = properties.get('container_user_id')
        self.container_shell_path = properties.get('container_shell_path', '/bin/bash')

        # API execution
        self.api_execution = properties.get('api_excution', False)
        self.api_base_url = properties.get('api_base_url')
        if self.api_base_url:
            self.api_base_url =
            api_launch_url = properties.get('api_launch_url', 'launch')
            self.api_launch_url = api_launch_url if self.api_base_url in api_launch_url else urllib.parse.urljoin(self.api_base_url, api_launch_url)
            api_poll_url = properties.get('api_poll_url', 'retrieve/status')
            self.api_poll_url = api_poll_url if self.api_base_url in api_poll_url else urllib.parse.urljoin(self.api_base_url, api_poll_url)
            api_retrieve_url = properties.get('api_retrieve_url', 'retrieve/data')
            self.api_retrieve_url = api_retrieve_url if self.api_base_url in api_retrieve_url else urllib.parse.urljoin(self.api_base_url, api_retrieve_url)