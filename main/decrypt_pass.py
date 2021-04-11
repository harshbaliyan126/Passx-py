import os
import fs 
from fs import open_fs
import gnupg

def decrypt(passphrase_gpg):
    gpg = gnupg.GPG(gnupghome="/home/floppy04/.gnupg")
    home_fs = open_fs("..")
    with open("encrypted/pass.gpg","rb") as f:
        status = gpg.decrypt_file(f, passphrase=passphrase_gpg,output="encrypted/pass")