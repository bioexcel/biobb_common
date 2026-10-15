Provenance
==========

Overview
--------

BioBB can record the provenance of its executions as `RO-Crates <https://www.researchobject.org/ro-crate/>`_,
following the `Workflow Run RO-Crate <https://www.researchobject.org/workflow-run-crate/>`_ profiles:

- **Block level**: each building block execution writes a
  `Process Run Crate <https://w3id.org/ro/wfrun/process/0.5>`_ describing the block, the wrapped
  software, the input and output files, the properties, the command line and the machine where it ran.
- **Workflow level**: the block crates are merged into a
  `Provenance Run Crate <https://w3id.org/ro/wfrun/provenance/0.5>`_ with the workflow script, its
  steps and the files linking them.

Provenance is disabled by default. The hostname and the username are not recorded as metadata, but
file paths are recorded as they are: absolute paths in file ids, command lines and properties (ie:
``/home/<user>/project/structure.pdb``) can contain them. Review the crates before publishing them.

Block provenance
----------------

Enable the ``provenance`` property in any building block:

.. code-block:: python

    from biobb_gromacs.gromacs.pdb2gmx import pdb2gmx

    pdb2gmx(input_pdb_path='structure.pdb',
            output_gro_path='structure.gro',
            output_top_zip_path='topology.zip',
            properties={'provenance': True})

or for all the blocks using the :doc:`global properties <global_properties>`:

.. code-block:: python

    from biobb_common import biobb_global_properties
    biobb_global_properties['provenance'] = True

From the command line, add ``provenance: true`` to the configuration file passed with ``--config``.

Each execution writes its crate to ``<provenance_path>/<step>_<ClassName>_<timestamp>/ro-crate-metadata.json``,
together with an HTML preview (``ro-crate-preview.html``). ``<provenance_path>`` is the
``provenance_path`` property or, by default, ``<path>/provenance``, where ``<path>`` is the ``path``
property of the block or the current directory. ``<step>`` is the step name of the configuration file
(ie: ``step3_sander_mdrun_minH``), omitted when the block has none. Input and output files are referenced by their absolute
``file://`` URI and never copied.
Block crates are therefore a record tied to the machine where the block ran. To move or share the
provenance, use a workflow crate (see below), which references the files inside its directory with
relative paths.

If the block raises an exception or returns a non-zero code, the execution is recorded as failed.
Errors while writing the provenance are logged as warnings and never stop the block.

Properties
~~~~~~~~~~

All of them can be set per block or as :doc:`global properties <global_properties>`:

=========================== =========== =======================================================================
Property                    Default     Description
=========================== =========== =======================================================================
``provenance``              ``False``   Write the RO-Crate of the execution.
``provenance_author``       ``None``    Author of the crate, recorded as the crate ``author`` and the
                                        ``agent`` of the execution: ``{"name": str, "orcid": str,
                                        "affiliation": str, "affiliation_url": str}``, only ``name`` is
                                        required. A string is used as the name.
``provenance_checksum``     ``False``   Add the ``sha256`` checksum of the input and output files.
                                        Directories are not hashed. Each file is read only once per
                                        process, ie: the output of a step that is the input of the next one.
``provenance_license``      ``None``    License of the workflow script in the workflow crate: SPDX
                                        identifier (ie: ``"MIT"``) or URL. Only read as a global property
                                        (or the ``license`` argument of ``workflow_provenance``,
                                        ``--license`` of ``biobb_provenance merge``).
``provenance_path``         ``None``    Directory of the block crates, by default ``<path>/provenance``
                                        (``<workflow path>/provenance`` inside ``workflow_provenance``).
                                        Set it as a global property to share it between the steps.
=========================== =========== =======================================================================

.. code-block:: python

    biobb_global_properties.update({
        'provenance': True,
        'provenance_author': {'name': 'Jane Doe',
                              'orcid': 'https://orcid.org/0000-0002-1825-0097',
                              'affiliation': 'IRB Barcelona',
                              'affiliation_url': 'https://www.irbbarcelona.org/'},
        'provenance_checksum': True,
        'provenance_license': 'MIT',
    })

The author is never recorded unless ``provenance_author`` is set. The publisher of the crates is always
the `BioExcel Centre of Excellence <https://bioexcel.eu/>`_.

Restart
~~~~~~~

When a block is skipped by the ``restart`` property because its outputs already exist, the latest
crate of a previous execution of the same block with the same outputs is reused, so the workflow crate
records how the outputs were really produced. If there is no such crate (ie: the previous execution
did not record provenance), a crate of the skipped execution is written, with the description
"Skipped by the restart property" and without command line, wrapped software or environment.

Workflow provenance
-------------------

Run the building blocks inside the ``workflow_provenance`` context manager:

.. code-block:: python

    from biobb_common.provenance import workflow_provenance

    with workflow_provenance(path='wf_output'):
        pdb2gmx(input_pdb_path='structure.pdb', output_gro_path='wf_output/structure.gro',
                output_top_zip_path='wf_output/topology.zip')
        editconf(input_gro_path='wf_output/structure.gro', output_gro_path='wf_output/box.gro')

The context manager enables provenance for all the blocks executed inside it and, on exit, writes
``wf_output/ro-crate-metadata.json``, a ``README.md`` and an HTML preview (``ro-crate-preview.html``).
The block crates are written to ``wf_output/provenance/``, unless the blocks set ``provenance_path``,
so the workflow crate and its block crates are in the same directory.
Existing ``README.md`` or ``ro-crate-preview.html`` files not written by biobb are never overwritten.
The workflow script (by default the script being executed) is copied into the crate directory. Files
inside the crate directory are referenced with relative paths, so the directory can be moved or shared
as a whole.

The global properties are not modified: only the blocks executed by the same thread (or asyncio task)
are recorded and collected. To include blocks executed in other threads, run them in a copy of the
context:

.. code-block:: python

    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    with workflow_provenance(path='wf_output'), ThreadPoolExecutor() as executor:
        executor.submit(contextvars.copy_context().run, pdb2gmx, input_pdb_path='structure.pdb', ...)

Nested ``workflow_provenance`` contexts write their own workflow crate, and their blocks are also part
of the outer workflow crate.

The steps are ordered by start time and connected through their files: when the output of a step is
the input of another step, both refer to the same file entity.

Block crates can also be merged afterwards, ie: when the steps run in different processes or SLURM jobs:

.. code-block:: python

    from biobb_common.provenance import find_block_crates, merge_block_crates

    merge_block_crates(find_block_crates('wf_output'), 'wf_output', workflow_file='workflow.py')

Example
~~~~~~~

Workflow crate of the `AMBER MD setup <https://github.com/bioexcel/biobb_wf_amber>`_ workflow
(25 steps of biobb_chemistry, biobb_structure_utils, biobb_amber and biobb_analysis, with short
simulations), run with ``workflow_provenance``:

- `HTML preview <_static/provenance_example/ro-crate-preview.html>`_ (``ro-crate-preview.html``)
- `RO-Crate metadata <_static/provenance_example/ro-crate-metadata.json>`_ (``ro-crate-metadata.json``)

The local paths of the execution were replaced by ``/home/user/amber_md_setup`` and
``/opt/conda/envs/biobb_wf_amber``.

Command line
------------

The ``biobb_provenance`` command merges, draws and validates the crates:

.. code-block:: bash

    # Merge all the block crates found inside wf_output into a workflow crate
    biobb_provenance merge wf_output -o wf_output -w workflow.py

    # Print the workflow graph in Mermaid format, or write it to a file
    biobb_provenance graph wf_output
    biobb_provenance graph wf_output -o workflow.md

    # Validate a crate (requires: pip install roc-validator)
    biobb_provenance validate wf_output

Graph formats are chosen by the output file extension: ``.mmd`` (Mermaid), ``.md`` (Mermaid inside a
Markdown code block, rendered by GitHub), ``.dot`` (Graphviz) and any format supported by Graphviz
(``.svg``, ``.png``, ``.pdf``...), which requires the ``graphviz`` Python package and the Graphviz
binaries: ``conda install python-graphviz`` installs both. Steps are drawn as boxes, files as
parallelograms and failed steps in red.

This is the graph of a two-step GROMACS workflow (pdb2gmx and editconf):

.. mermaid:: provenance_example.mmd

Validation uses `rocrate-validator <https://github.com/crs4/rocrate-validator>`_, which is not a
dependency of biobb_common. By default it checks the ``REQUIRED`` requirements of the
``process-run-crate`` profile for block crates and the ``provenance-run-crate`` profile for workflow
crates; use ``--severity RECOMMENDED`` for a stricter check.

Recorded metadata
-----------------

Block crate
~~~~~~~~~~~

=========================== =======================================================================
Entity                      Content
=========================== =======================================================================
``CreateAction``            Start and end time, status (``CompletedActionStatus`` or
                            ``FailedActionStatus`` with ``error``), command line as ``description``,
                            container image (``containerImage``) and ``executionEnvironment``.
``ContainerImage``          When the block runs in a container: registry, name, tag and ``sha256``
                            digest (Docker repository digest, or checksum of a local image file such
                            as a Singularity ``.sif``).
``SoftwareApplication``     The building block (``instrument``): name, biobb package version and
                            repository. Its ``@id`` is the block documentation page.
                            ``softwareRequirements`` points to the wrapped software.
Wrapped software            ``SoftwareApplication`` with name, version, license and ``url`` (the
                            anaconda.org, project or PyPI page of the package, also used in its ``@id``).
``File`` / ``Dataset``      Inputs (``object``) and outputs (``result``) with their EDAM format as
                            ``encodingFormat`` (a reference to the EDAM term, described as a
                            ``WebSite``), their size and, with ``provenance_checksum``, their
                            ``sha256``.
``Person``                  With ``provenance_author``: crate ``author`` and action ``agent``,
                            identified by the ORCID, with its ``affiliation`` (``Organization``).
``Organization``            The BioExcel Centre of Excellence, crate ``publisher``.
``PropertyValue``           Documented properties of the block (``object``) and environment values.
=========================== =======================================================================

Workflow crate
~~~~~~~~~~~~~~

All the entities of the block crates, plus:

=========================== =======================================================================
Entity                      Content
=========================== =======================================================================
``ComputationalWorkflow``   The workflow script (``mainEntity``), with its ``step`` list and the
                            building blocks it uses in ``hasPart``. It follows the `Bioschemas
                            ComputationalWorkflow <https://bioschemas.org/profiles/ComputationalWorkflow/1.0-RELEASE>`_
                            profile: ``version`` (git commit, or ``sha256:`` of the script if it is
                            not committed), ``url`` (the script in the git remote at that commit, or
                            its original ``file://`` URI), ``dateCreated``, ``creator`` (the
                            authors), ``sdPublisher`` (BioExcel), ``input``, ``output`` and, with
                            ``provenance_license``, ``license``.
``FormalParameter``         One per workflow input and output, linked from the files with
                            ``exampleOfWork``.
``HowToStep``               One per block execution, with its ``position``, the block as
                            ``workExample`` and, as ``name``, the step name of the configuration file
                            (the ``alternateName`` of the block ``CreateAction``) or the block name.
``ControlAction``           Links each ``HowToStep`` with the ``CreateAction`` of the block execution.
``CreateAction``            ``#workflow-run``: the whole execution. Its inputs are the files no step
                            produced and its outputs the files no step consumed. The authors of the
                            steps are its ``agent`` and the crate ``author``.
``OrganizeAction``          The orchestration by biobb_common, linking the control actions and the
                            workflow run.
``File``                    ``README.md`` (about the crate), with the steps, inputs, outputs and the
                            Mermaid graph.
=========================== =======================================================================

Wrapped software version
~~~~~~~~~~~~~~~~~~~~~~~~

The version of the wrapped software is detected from the first available source:

1. **container**: the tag of the container image, when the block runs in a container. Tags that are
   not versions (``latest``, ``serial``...) fall back to the documented version; the image digest is
   recorded in the ``ContainerImage``.
2. **conda**: the conda package that installed the binary (``binary_path``), read from the
   ``conda-meta`` directory of its environment without executing it.
3. **python** or **conda**: the Python distribution or conda package matching the first word of the
   documented name, ie: "Ambertools Cpptraj" matches ``ambertools``. Names that do not start with the
   package name are mapped in ``PACKAGE_NAMES`` (``provenance/software.py``), ie: "PyTorch" matches
   ``torch`` and "Open Babel" ``openbabel``.
4. **documentation**: the version documented in the docstring.

Only exact versions are recorded (ie: ``24.8``, ``v1.1.2``). A documented range such as ``>=20.0`` is
not a version: when no version is detected, the wrapped software has no ``softwareVersion`` and its
``description`` gives the documented requirement.

Execution environment
~~~~~~~~~~~~~~~~~~~~~

Operating system and kernel version, CPU architecture, CPU model and core count, total memory, Python
version, conda environment name, the SLURM job id and cluster name, the NVIDIA GPU model, count, memory
and driver version (from ``nvidia-smi``) and ``CUDA_VISIBLE_DEVICES`` when available.

Terms
-----

Term used in the crates that is not defined by schema.org or the
`workflow-run <https://w3id.org/ro/terms/workflow-run>`_ vocabulary:

.. raw:: html

    <span id="executionEnvironment"></span>

``executionEnvironment``
    ``PropertyValue`` entities describing the machine where a ``CreateAction`` was executed.

Limitations
-----------

- Only NVIDIA GPUs are recorded, and all the GPUs of the machine are listed, not only the ones used.
- The main workflow has a local file id, so rocrate-validator reports the RECOMMENDED check
  "SoftwareApplication id SHOULD be an absolute URI", which conflicts with Workflow RO-Crate (the main
  workflow must be a file of the crate).
- Workflows without a script (ie: Jupyter notebooks, or ``biobb_provenance merge`` without
  ``--workflow-file``) produce a crate that only conforms to Process Run Crate: a Workflow RO-Crate
  requires the workflow file. The steps, their links and the workflow run are still recorded, the
  workflow is a ``ComputationalWorkflow`` entity without file and it is not the ``mainEntity``.
