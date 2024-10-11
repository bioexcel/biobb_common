import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="biobb_common",
    version="5.0.0",
    author="Biobb developers",
    author_email="pau.andrio@bsc.es",
    description="Biobb_common is the base package required to use the biobb packages.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="Bioinformatics Workflows BioExcel Compatibility",
    url="https://github.com/bioexcel/biobb_common",
    project_urls={
        "Documentation": "http://biobb-common.readthedocs.io/en/latest/",
        "Bioexcel": "https://bioexcel.eu/",
    },
    packages=setuptools.find_packages(exclude=["docs"]),
    package_data={'biobb_common': ['py.typed']},
    install_requires=["pyyaml", "requests", "biopython", "jsonschema"],
    python_requires='>=3.9',
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX",
        "Operating System :: Unix"
    ],
)
