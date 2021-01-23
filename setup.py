#!/usr/bin/env python
import os
from setuptools import setup


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="lexode",
    version="0.2.0",
    author="Amirouche Boubekki",
    author_email="amirouche@hypermove.net",
    url="https://github.com/amirouche/python-lexode",
    description="Explore relational data",
    long_description=read("README.md"),
    py_modules=['lexode'],
    zip_safe=False,
    license="MIT",
    install_requires=[],
    classifiers=[
        "Intended Audience :: Developers",
        "Topic :: Software Development",
        "Programming Language :: Python :: 3",
    ],
)
