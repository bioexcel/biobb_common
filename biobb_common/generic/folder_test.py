#!/usr/bin/env python3

"""Module containing the haddock  class and the command line interface."""

import os
import shutil
from typing import Optional

from biobb_common.generic.biobb_object import BiobbObject
from biobb_common.tools import file_utils as fu
from biobb_common.tools.file_utils import launchlogger


class FolderTest(BiobbObject):
    """
    | biobb_haddock FolderTest
    | Wrapper class for the FolderTest module.
    | The FolderTest module.

    Args:
        input_folder (dir) (Optional): Path of the input folder. File type: input. `Sample file <https://raw.githubusercontent.com/bioexcel/biobb_haddock/master/biobb_haddock/test/reference/haddock/input_folder>`_. Accepted formats: directory (edam:format_1915).
        output_folder (dir): Path of the output folder. File type: output. `Sample file <https://raw.githubusercontent.com/bioexcel/biobb_haddock/master/biobb_haddock/test/reference/haddock/output_folder>`_. Accepted formats: directory (edam:format_1915).
        properties (dict - Python dictionary object containing the tool parameters, not input/output files):
            * **n** (*int*) - (4) Number of files create.
            * **file_prefix** (*str*) - ("file") Prefix for the created files.

    Examples:
        This is a use example of how to use the building block from Python::

            from biobb_haddock.haddock.folder_test import folder_test
            folder_test(input_folder='/path/to/input_folder',
                        output_folder='/path/to/output_folder',
                        properties={'n': 4})

    Info:
        * wrapped_software:
            * name: None
            * version: None
            * license: Apache-2.0
        * ontology:
            * name: EDAM
            * schema: http://edamontology.org/EDAM.owl
    """

    def __init__(
        self,
        output_folder: str,
        input_folder: Optional[str] = None,
        properties: Optional[dict] = None,
        **kwargs,
    ) -> None:
        properties = properties or {}

        # Call parent class constructor
        super().__init__(properties)
        self.locals_var_dict = locals().copy()

        # Input/Output files
        self.io_dict = {
            "in": {"input_folder": input_folder},
            "out": {"output_folder": output_folder},
        }

        self.n = properties.get('n', 4)
        self.file_prefix = properties.get('file_prefix', 'file')
        # Check the properties
        self.check_init(properties)

    @launchlogger
    def launch(self) -> int:
        """Execute the :class:`FolderTest <biobb_haddock.haddock.folder_test>` object."""
        # tmp_files = []

        # Setup Biobb
        if self.check_restart():
            return 0
        self.stage_files()

        sandbox_output_folder = self.stage_io_dict["out"]["output_folder"]
        os.makedirs(sandbox_output_folder, exist_ok=True)
        # Just move the input files to the output
        if self.stage_io_dict["in"].get("input_folder") and self.stage_io_dict["in"]["input_folder"] != sandbox_output_folder:
            shutil.copytree(self.stage_io_dict["in"]["input_folder"],
                            sandbox_output_folder+'/prev',
                            dirs_exist_ok=True)
        fu.log('Directory contents: ' + str(os.listdir(sandbox_output_folder)), self.out_log, self.global_log)
        # Create n files in the output folder
        fu.log(f"Creating {self.n} files in the output folder: {sandbox_output_folder}",
               self.out_log, self.global_log)
        for i in range(1, self.n + 1):
            with open(f'{sandbox_output_folder}/{self.file_prefix}_{i}.txt', 'w') as f:
                f.write(f"This is file number {i}")
        fu.log('Directory contents: ' + str(os.listdir(sandbox_output_folder)), self.out_log, self.global_log)
        # Copy files to host
        self.copy_to_host()

        # Remove temporal files
        self.remove_tmp_files()
        # self.check_arguments(output_files_created=True, raise_exception=False)
        return self.return_code


def folder_test(output_folder: str, input_folder: Optional[str] = None, properties: Optional[dict] = None, **kwargs) -> int:
    """Create :class:`FolderTest <biobb_haddock.haddock.folder_test>` class and
    execute the :meth:`launch() <biobb_haddock.haddock.folder_test.launch>` method."""
    return FolderTest(**dict(locals())).launch()


folder_test.__doc__ = FolderTest.__doc__
main = FolderTest.get_main(folder_test, "Wrapper of the HADDOCK3 FolderTest module.")

if __name__ == "__main__":
    main()
