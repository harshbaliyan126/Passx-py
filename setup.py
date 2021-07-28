from setuptools import setup, find_packages

with open("requirement.txt") as f:
        install_requires = f.read().splitlines()
with open("README.md", "r") as readme:
    LONG_DESCRIPTION = readme.read()

VERSION = '0.0.3'
DESCRIPTION = 'A Password manager using GNUPG'
URL = "https://github.com/harshbaliyan126/Passx-py"

# Setting up
setup(
    name="passx",
    version=VERSION,
    author="floppy04 <Harsh Baliyan>",
    author_email="<harshbaliyan126@gmail.com>",
    description=DESCRIPTION,
    url=URL,
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=install_requires,
    entry_points={
        "console_scripts" : [
            'passx = passx.passx:main'
            ]
        },
    classifiers=[
        "Development Status :: 1 - Planning",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Operating System :: Unix",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
    ]
)
