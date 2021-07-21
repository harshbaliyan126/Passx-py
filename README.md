# Passx
It's a script, using GNUPG for encrypting passwords.

### Installation

 -  Create a GNUPG key pair if not created already, following this [GNUPG tutorial](https://www.gnupg.org/gph/en/manual/c14.html)
 -  After that, when key pair is created. Do following:

   ```console
   $ git clone https://github.com/harshbaliyan126/Passx-py.git
   $ cd Passx-py
   $ pip install -r requirement.txt
   $ chmod +x ./main/passx
   $ cp ./main/passx to/the/path/directory
   ```

### Usage

```
Usage:
    passx [account] - Loads password to clipboard

    -a , --add
        passx -a/--add [account] - Saves account
    -d, --delete
        passx -d/--delete [account] - Deletes account
    --list
        passx --list - List all accounts saved
```
