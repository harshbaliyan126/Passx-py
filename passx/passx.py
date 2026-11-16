#!/usr/bin/env python3
import argparse
import getpass
import hashlib
import json
import os
import shelve
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import gnupg
import pyperclip

from passx.fileio import atomic_write

CONFIG_DIR = Path.home() / '.config' / 'passx'
VAULT_FILE = 'vault.gpg'
RECIPIENT_FILE = 'recipient.txt'
# files written by passx <= 0.0.7, kept only for migration
LEGACY_DIR = 'encrypted'

DEFAULT_CLIP_TIME = 45


class PassxError(Exception):
    pass


class Vault:
    """Accounts stored as a single GPG-encrypted JSON document.

    Plaintext never touches the disk: the vault is decrypted into memory,
    and saved by encrypting in memory and atomically replacing the old file.
    """

    def __init__(self, config_dir=None, gpg=None):
        self.config_dir = Path(config_dir or CONFIG_DIR)
        self.path = self.config_dir / VAULT_FILE
        # gnupghome=None lets gpg honour $GNUPGHOME or fall back to ~/.gnupg
        self.gpg = gpg or gnupg.GPG(gnupghome=os.environ.get('GNUPGHOME'))
        self.accounts = {}

    def ensure_config_dir(self):
        self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.config_dir, 0o700)

    def load(self):
        self.ensure_config_dir()
        if not self.path.exists():
            self.accounts = migrate_legacy(self) or {}
            return self
        with open(self.path, 'rb') as f:
            result = self.gpg.decrypt_file(f)
        if not result.ok:
            raise PassxError('Could not decrypt %s: %s' % (self.path, result.status))
        data = json.loads(result.data.decode('utf-8'))
        self.accounts = data['accounts']
        return self

    def save(self):
        self.ensure_config_dir()
        payload = json.dumps({'version': 1, 'accounts': self.accounts})
        result = self.gpg.encrypt(payload, [self.recipient()], armor=False)
        if not result.ok:
            raise PassxError('Encryption failed, vault left unchanged: %s' % result.status)
        atomic_write(self.path, result.data)

    def recipient(self):
        for path in (self.config_dir / RECIPIENT_FILE,
                     self.config_dir / LEGACY_DIR / RECIPIENT_FILE):
            if path.exists():
                reci = path.read_text().strip()
                if reci:
                    return reci
        reci = input('Enter GPG recipient (key ID or email): ').strip()
        if not reci:
            raise PassxError('A recipient is required to encrypt the vault')
        (self.config_dir / RECIPIENT_FILE).write_text(reci + '\n')
        return reci


def read_shelve(path):
    with shelve.open(str(path), flag='r') as db:
        return dict(db)


def migrate_legacy(vault):
    """Import accounts from the shelve database used by passx <= 0.0.7.

    Returns the accounts, or None if there is nothing to migrate. Legacy files
    are only renamed after the new vault has been written successfully.
    """
    legacy = vault.config_dir / LEGACY_DIR
    plain = legacy / 'pass'
    encrypted = legacy / 'pass.gpg'

    if plain.exists():
        # left behind unencrypted by an interrupted run of the old version
        accounts = read_shelve(plain)
    elif encrypted.exists():
        with open(encrypted, 'rb') as f:
            result = vault.gpg.decrypt_file(f)
        if not result.ok:
            raise PassxError('Could not decrypt legacy vault %s: %s' % (encrypted, result.status))
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'pass'
            db.write_bytes(result.data)
            accounts = read_shelve(db)
    else:
        return None

    vault.accounts = accounts
    vault.save()
    if plain.exists():
        os.remove(plain)
    if encrypted.exists():
        os.replace(encrypted, legacy / 'pass.gpg.migrated')
    print('Migrated %d account(s) to %s' % (len(accounts), vault.path), file=sys.stderr)
    return accounts


def prompt_password():
    show = input('Show password [y/N]: ').strip().lower()
    if show in ('y', 'yes'):
        password = input('Password: ')
    else:
        password = getpass.getpass('Password: ')
        if getpass.getpass('Confirm password: ') != password:
            raise PassxError('Passwords do not match')
    if not password:
        raise PassxError('Password cannot be empty')
    return password


def add_account(vault, account):
    if account in vault.accounts:
        answer = input('%s already exists. Overwrite? [y/N]: ' % account).strip().lower()
        if answer not in ('y', 'yes'):
            print('Aborted.')
            return
    vault.accounts[account] = prompt_password()
    vault.save()
    print('Saved ' + account)


def delete_account(vault, account):
    if account not in vault.accounts:
        raise PassxError("Account '%s' doesn't exist" % account)
    del vault.accounts[account]
    vault.save()
    print('Deleted ' + account)


def list_accounts(vault):
    for account in sorted(vault.accounts):
        print(account)


def copy_password(vault, account, clip_time):
    if account not in vault.accounts:
        raise PassxError("Account '%s' doesn't exist" % account)
    password = vault.accounts[account]
    pyperclip.copy(password)
    if clip_time > 0:
        schedule_clipboard_clear(password, clip_time)
        print('Password for %s copied to the clipboard. Clearing in %d seconds.' % (account, clip_time))
    else:
        print('Password for %s copied to the clipboard.' % account)


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def schedule_clipboard_clear(password, seconds):
    # a detached child clears the clipboard after we exit; it only gets a hash,
    # so the password never appears in its command line
    subprocess.Popen(
        [sys.executable, '-m', 'passx.passx', '--clear-clipboard', digest(password), str(seconds)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def clear_clipboard(expected_digest, seconds):
    time.sleep(seconds)
    try:
        # don't wipe something the user copied in the meantime
        if digest(pyperclip.paste()) == expected_digest:
            pyperclip.copy('')
    except pyperclip.PyperclipException:
        pass


def build_parser():
    parser = argparse.ArgumentParser(
        prog='passx', description='A password manager using GNUPG.')
    parser.add_argument('account', nargs='?', help='copy the password for ACCOUNT to the clipboard')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('-a', '--add', metavar='ACCOUNT', help='save an account')
    actions.add_argument('-d', '--delete', metavar='ACCOUNT', help='delete an account')
    actions.add_argument('-l', '--list', action='store_true', help='list all saved accounts')
    parser.add_argument('-t', '--clip-time', type=int, default=DEFAULT_CLIP_TIME, metavar='SECONDS',
                        help='clear the clipboard after SECONDS (default %(default)s, 0 to disable)')
    parser.add_argument('--clear-clipboard', nargs=2, help=argparse.SUPPRESS)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.clear_clipboard:
        clear_clipboard(args.clear_clipboard[0], float(args.clear_clipboard[1]))
        return 0

    action_given = args.add or args.delete or args.list
    if action_given and args.account:
        parser.error('ACCOUNT cannot be combined with --add, --delete or --list')
    if not action_given and not args.account:
        parser.print_help()
        return 0

    try:
        vault = Vault().load()
        if args.add:
            add_account(vault, args.add)
        elif args.delete:
            delete_account(vault, args.delete)
        elif args.list:
            list_accounts(vault)
        else:
            copy_password(vault, args.account, args.clip_time)
    except PassxError as e:
        print('passx: error: %s' % e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # nothing is written until save(), so an interrupt can't corrupt the vault
        print('\nAborted.', file=sys.stderr)
        return 130
    return 0


if __name__ == '__main__':
    sys.exit(main())
