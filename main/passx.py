#!/usr/bin/python3
import os 
import pyperclip
import sys 
import shelve 
import getpass 

# custom module
import decrypt_pass, encrypt_pass

# list all accounts present in db
def list_all_account(pass1):
    for list_pass in pass1.keys():
                print(list_pass)
# it ask user whether he want to show password or not
def show_choice_pass(show_ch, account, pass1):
    if show_ch.lower() == 'y':
        pass1[account] = input('Password: ')
    elif show_ch.lower() == 'n' or show_ch == '':
        pass1[account] = getpass.getpass("Password: ")

# copy pasword to clipboard
def copy_pass_clip(pass1, account):
    if account in pass1:
        pyperclip.copy(pass1[account])
        print('Password for ' + account + ' copied to the clipboard.')
    else:
        print("Account doesn't exist")

# check whether user has given recipient for encryption 
def check_recipient():
    if os.path.exists('encrypted/recipient.txt'):
        with open("encrypted/recipient.txt", "r") as f:
            reci = f.read()
            if reci[len(reci)-1] == '\n':
                reci = reci[:len(reci)-2]
    else:
        reci = input("Enter Recipient: ")
        with open("encrypted/recipient.txt", "w") as f:
            f.write(reci)
    return reci

# If user have given command
def arg_true():
    if not os.path.exists('encrypted'):
        os.mkdir('encrypted')
    if os.path.exists('encrypted/pass.gpg'):
        passphrase_gpg = getpass.getpass("Passphrase: \uf084")
        decrypt_pass.decrypt(passphrase_gpg)
        os.remove('encrypted/pass.gpg')
    passwords = shelve.open('encrypted/pass')
    if len(sys.argv) == 3:
        if sys.argv[1].lower() == '--add' or sys.argv[1].lower() == '-a':
            show_choice = input('Show Password[y/N]: ')
            show_choice_pass(show_choice, sys.argv[2], passwords)
        elif sys.argv[1].lower() == '--delete' or sys.argv[1].lower() == '-d':
            del passwords[sys.argv[2]]
    elif len(sys.argv) == 2:
        if  sys.argv[1].lower() == '--list':
            list_all_account(passwords)
        elif sys.argv[1] in passwords:
            copy_pass_clip(passwords, sys.argv[1])
    passwords.close()
    if os.path.exists("encrypted/pass"):
        encrypt_pass.encrypt(check_recipient())
        os.remove('encrypted/pass')

# display how to use passx
def help():    
    usage_str  = '''\tpass [account] - Loads password to clipboard\n'''
    usage_str1 = '''\t-a , --add
            passx -a/--add [account] - Saves account'''
    usage_str2 = '''\t-d, --delete
            passx -d/--delete [account] - Deletes account'''
    usage_str3 = '''\t--list
            passx --list - List all accounts saved'''
    print('Usage:\n' + usage_str + '\n' + usage_str1 + '\n' + usage_str2 + '\n' + usage_str3)

# main function 
def main():
    if len(sys.argv) > 1:
        if sys.argv[1].lower() == '--help':
           help()
           sys.exit()
        arg_true()
    else:
        help()
           
if __name__=="__main__":
    main()


    
        
        
            

