import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="biobb_common",
    version="0.0.3",
    author="Biobb developers",
    author_email="pau.andrio@bsc.es",
    description="Biobb_common is the base package required to use the biobb packages.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="Bioinformatics Workflows BioExcel Compatibility",
    url="https://github.com/bioexcel/biobb_common",
    project_urls={
        "Documentation": "http://biobb_common.readthedocs.io/en/latest/",
        "Bioexcel": "https://bioexcel.eu/"
    },
    packages=setuptools.find_packages(exclude=['docs']),
    install_requires=['pyyaml', 'nose', 'jupyter', 'requests', 'Sphinx', 'sphinx-rtd-theme', 'recommonmark', 'biopython', 'cwltool'],
    python_requires='~=3.6',
    classifiers=(
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3.6",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
    ),
)