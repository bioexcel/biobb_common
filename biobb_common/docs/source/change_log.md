# Biobb_common ChangeLog


## What's new in version [5.2.1](https://github.com/bioexcel/biobb_common/releases/tag/v5.2.1)?

* [FEATURE] Minor bug fixes.

## What's new in version [5.2.0](https://github.com/bioexcel/biobb_common/releases/tag/v5.2.0)?

* [UPDATE] Update to Python 3.10
* [FEATURE] Add methods `create_tmp_dir`
* [UPDATE] Logs only create a file if there is something to write.
* [FEATURE] Add custom flags argument to `get_main`.


## What's new in version [5.1.1](https://github.com/bioexcel/biobb_common/releases/tag/v5.1.1)?
* [FEATURE] Add [global properties](https://biobb-common.readthedocs.io/en/latest/global_properties.html) shared by all the blocks.
* [FEATURE] Automatic block argument parser from docstring.
* [FEATURE] Automatic short flags -i/-o for blocks with only one input/output argument.
* [FEATURE] Folder as inputs and outputs.
* [FEATURE] Add new test fixture to check if a folder is not empty.
* [FEATURE] Enable deleting temporal files while sandbox is disabled. Use BiobbObject.create_tmp_file to safely create temporary files.
* [FEATURE] Add can_write_file_log property to toggle logging of file writes.

## What's new in version [5.1.0](https://github.com/bioexcel/biobb_common/releases/tag/v5.1.0)?

* [FEATURE] Add '#' to the list of lines considered as comments for xvg comparasion.
* [FEATURE] Improve not_empty fixture to consider zips without files as empty.

## What's new in version [5.0.1](https://github.com/bioexcel/biobb_common/releases/tag/v5.0.1)?

* [FEATURE] Add '#' to the list of lines considered as comments for xvg comparasion.
* [FEATURE] Improve not_empty fixture to consider zips without files as empty.

## What's new in version [5.0.0](https://github.com/bioexcel/biobb_common/releases/tag/v5.0.0)?

### Changes
* [UPDATE] Update to Python 3.9
* [FEATURE] Adding disable_logs property
* [FEATURE] Adding log_path property
* [FEATURE] Adding ConfReader Global Properties
* [CI/CD] Adding new TestFixtures
* [FEATURE] Adding timeout to CommandWrapper
* [FEATURE] Refactor ConfigReader


## What's new in version [4.2.0](https://github.com/bioexcel/biobb_common/releases/tag/v4.2.0)?

### Changes

* [FIX] Typing annotation Errors
* [FEATURE] Adding typing annotations
* [FIX] Fixing Read the Docs
* [FEATURE] Disabled closing inactive issues
* [FIX] Fixed JSON schema
* [FIX] Modify python version in .readthedocs.yaml