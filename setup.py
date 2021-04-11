from setuptools import setup 
from setuptools import find_namespace_packages

# Load the README file.
with open(file='README.md', mode="r") as readme_handle:
    long_description = readme_handle.read()

setup(
    name='passx',
    author='Harsh Baliyan',
    author_email='harshbaliyan126@gmail.com',
    version='0.1.1',
    description='A Password manager used to store password using Gnupg',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/harshbaliyan126/Passx-py',
    install_requires=[
        "appdirs==1.4.4",
        "fs==2.4.13",
        "pyperclip==1.8.2",
        "python-gnupg==0.4.7",
        "pytz==2021.1",
        "six==1.15.0"
    ],
    keywords='Password manager, Gnupg',

    packages=find_namespace_packages(
        include=['main']
    ),
    include_package_data=True,
    python_requires='>=3.8',

)