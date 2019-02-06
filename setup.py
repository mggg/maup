from setuptools import find_packages, setup

import versioneer

with open("./README.rst") as f:
    long_description = f.read()

requirements = ["numpy", "scipy", "pandas", "geopandas", "shapely"]

setup(
    name="spatial-ops",
    version="0.1",
    description="Spatial data processing, especially for redistricting",
    author="Max Hully",
    author_email="max@mggg.org",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/mggg/spatial-ops",
    packages=find_packages(exclude=("tests",)),
    install_requires=requirements,
    classifiers=[
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
    ],
)
