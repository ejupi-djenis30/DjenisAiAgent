"""
Setup script for DjenisAiAgent.

This allows the package to be installed with pip install -e .
"""
from setuptools import setup, find_packages
import os

# Read the README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="djenis-ai-agent",
    version="0.1.0",
    author="Djenis Ejupi",
    author_email="ejupi.djenis30@example.com",
    description="An intelligent UI automation agent powered by Google's Gemini AI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/ejupi-djenis30/DjenisAiAgent",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: Microsoft :: Windows :: Windows 11",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "djenis-agent=src.main:main",
            "djenis-ui=src.ui.agent_ui:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["config/*.json", "config/*.template"],
    },
)
