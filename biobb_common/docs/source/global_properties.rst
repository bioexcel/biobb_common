BioBB Global Properties
=======================

Overview
--------

The ``BioBBGlobalProperties`` class provides a centralized way to manage global configuration properties that are shared across all BiobbObject instances in your workflow. This eliminates the need to pass the same properties repeatedly to each building block.

Features
--------

- **Global Configuration**: Set properties once and use them across all BioBB objects
- **Priority System**: Local properties override global properties when conflicts arise
- **Dictionary Interface**: Behaves like a standard Python dictionary
- **Shallow Copy Support**: Safe property sharing without unintended modifications

Usage
-----

Basic Usage
~~~~~~~~~~~

The global properties instance is automatically created and available for import:

.. code-block:: python

    from biobb_common import biobb_global_properties
    
    # Set global properties
    biobb_global_properties.update({
        'container_path': '/usr/bin/singularity',
        'container_image': 'biocontainers/gromacs:latest',
        'remove_tmp': True,
        'restart': False
    })

Setting Properties
~~~~~~~~~~~~~~~~~~

You can set properties using dictionary-style operations:

.. code-block:: python

    # Set individual properties
    biobb_global_properties['binary_path'] = '/usr/local/bin/gmx'
    biobb_global_properties['timeout'] = 3600
    
    # Set multiple properties at once
    biobb_global_properties.update({
        'container_volume_path': '/data',
        'container_working_dir': '/tmp',
        'disable_logs': False
    })

Using with BioBB Objects
~~~~~~~~~~~~~~~~~~~~~~~~

When creating BioBB objects, global properties are automatically merged with local properties:

.. code-block:: python

    from biobb_gromacs.gromacs.mdrun import mdrun
    from biobb_common import biobb_global_properties
    
    # Set global properties once
    biobb_global_properties.update({
        'container_path': '/usr/bin/singularity',
        'container_image': 'biocontainers/gromacs:latest',
        'remove_tmp': True
    })
    
    # Create BioBB object - global properties are automatically applied
    mdrun_obj = mdrun(
        input_tpr_path='input.tpr',
        output_trr_path='output.trr',
        output_gro_path='output.gro',
        output_edr_path='output.edr',
        output_log_path='output.log',
        properties={
            'mpi_bin': 'mpirun',  # This local property is added
            'timeout': 7200       # This overrides global timeout if set
        }
    )

Property Priority
~~~~~~~~~~~~~~~~~

Local properties always take precedence over global properties:

.. code-block:: python

    # Global setting
    biobb_global_properties['timeout'] = 3600
    
    # Local setting overrides global
    my_object = SomeBioBBClass(
        properties={
            'timeout': 7200  # This value will be used, not 3600
        }
    )

Common Use Cases
----------------

Container Configuration
~~~~~~~~~~~~~~~~~~~~~~~

Set container settings once for all building blocks:

.. code-block:: python

    biobb_global_properties.update({
        'container_path': '/usr/bin/singularity',
        'container_image': 'biocontainers/gromacs:2021.1--h_fbb9dd7_1',
        'container_volume_path': '/data',
        'container_working_dir': '/tmp'
    })

Workflow-wide Settings
~~~~~~~~~~~~~~~~~~~~~~

Configure common workflow properties:

.. code-block:: python

    biobb_global_properties.update({
        'remove_tmp': True,
        'restart': False,
        'sandbox_path': './workflow_sandbox',
        'disable_logs': False
    })

Environment Variables
~~~~~~~~~~~~~~~~~~~~~

Set environment variables for all containers:

.. code-block:: python

    biobb_global_properties['env_vars_dict'] = {
        'OMP_NUM_THREADS': '4',
        'CUDA_VISIBLE_DEVICES': '0',
        'GMX_MAXBACKUP': '-1'
    }

Best Practices
--------------

1. **Set Early**: Configure global properties at the beginning of your workflow
2. **Use for Common Settings**: Apply to properties shared across multiple building blocks
3. **Override When Needed**: Use local properties for block-specific configurations
4. **Clear Documentation**: Document which properties are set globally in your workflow

Example Workflow
----------------

.. code-block:: python

    from biobb_common import biobb_global_properties
    from biobb_gromacs.gromacs.editconf import editconf
    from biobb_gromacs.gromacs.solvate import solvate
    from biobb_gromacs.gromacs.mdrun import mdrun
    
    # Configure global properties once
    biobb_global_properties.update({
        'container_path': '/usr/bin/singularity',
        'container_image': 'biocontainers/gromacs:latest',
        'remove_tmp': True,
        'restart': False,
        'env_vars_dict': {
            'OMP_NUM_THREADS': '8'
        }
    })
    
    # All building blocks will inherit these properties
    editconf_step = editconf(
        input_gro_path='input.gro',
        output_gro_path='editconf.gro'
    )
    
    solvate_step = solvate(
        input_solute_gro_path='editconf.gro',
        output_gro_path='solvated.gro',
        properties={
            'shell': 1.0  # Local property specific to solvate
        }
    )
    
    mdrun_step = mdrun(
        input_tpr_path='input.tpr',
        output_trr_path='output.trr',
        properties={
            'timeout': 7200  # Override global timeout for this step
        }
    )

API Reference
-------------

.. autoclass:: biobb_common.BioBBGlobalProperties
   :members:
   :undoc-members:
   :show-inheritance:

.. autodata:: biobb_common.biobb_global_properties
   :annotation: = BioBBGlobalProperties()
   
   Global instance of BioBBGlobalProperties available for immediate use.
