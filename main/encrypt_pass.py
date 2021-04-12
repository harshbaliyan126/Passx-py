import os
import fs 
from fs import open_fs
import gnupg
from pathlib import Path

def encrypt(enter_reci):
    home = str(Path.home())
    gpg = gnupg.GPG(gnupghome=home + "/.gnupg")
    home_fs = open_fs("..")
    with open("encrypted/pass","rb") as f:
        status = gpg.encrypt_file(f, recipients=[enter_reci], output= "encrypted/pass.gpg")