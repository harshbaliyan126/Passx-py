import os
import fs 
from fs import open_fs
import gnupg
from pathlib import Path

def decrypt(passphrase_gpg):
    home = str(Path.home())
    gpg = gnupg.GPG(gnupghome=home + "/.gnupg")
    home_fs = open_fs("..")
    with open("encrypted/pass.gpg","rb") as f:
        status = gpg.decrypt_file(f, passphrase=passphrase_gpg,output="encrypted/pass")