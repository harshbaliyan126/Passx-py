import os
import fs 
from fs import open_fs
import gnupg

def encrypt(enter_reci):
    gpg = gnupg.GPG(gnupghome="/home/floppy04/.gnupg")
    home_fs = open_fs("..")
    with open("encrypted/pass","rb") as f:
        status = gpg.encrypt_file(f, recipients=[enter_reci], output= "encrypted/pass.gpg")