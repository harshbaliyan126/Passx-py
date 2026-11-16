"""Master-password protected vault used by the passx GUI.

File layout (all integers big-endian):

    magic      6 bytes   b'PASSX\\x01'
    memory     u32       Argon2id memory cost in KiB
    iterations u32       Argon2id passes
    lanes      u32       Argon2id parallelism
    salt       16 bytes
    nonce      12 bytes
    ciphertext           AES-256-GCM of the JSON document

Everything before the ciphertext is authenticated as associated data, so
tampering with the KDF parameters is detected just like tampering with the
ciphertext.
"""
import json
import os
import secrets
import string
import struct
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from passx.fileio import atomic_write

DEFAULT_PATH = Path.home() / '.config' / 'passx' / 'passwords.vault'

MAGIC = b'PASSX\x01'
HEADER = struct.Struct('>6sIII16s12s')
# OWASP-recommended Argon2id settings: 64 MiB, 3 passes, 4 lanes
KDF_MEMORY = 64 * 1024
KDF_ITERATIONS = 3
KDF_LANES = 4

MIN_MASTER_LENGTH = 8

FIELDS = ('title', 'username', 'password', 'url', 'notes')

# lowercase name -> login page, used to pre-fill the website field
KNOWN_SITES = {
    'gmail': 'https://mail.google.com',
    'google': 'https://accounts.google.com',
    'youtube': 'https://www.youtube.com',
    'yahoo': 'https://login.yahoo.com',
    'outlook': 'https://outlook.live.com',
    'hotmail': 'https://outlook.live.com',
    'microsoft': 'https://account.microsoft.com',
    'apple': 'https://account.apple.com',
    'icloud': 'https://www.icloud.com',
    'facebook': 'https://www.facebook.com',
    'instagram': 'https://www.instagram.com',
    'whatsapp': 'https://web.whatsapp.com',
    'twitter': 'https://x.com',
    'x': 'https://x.com',
    'linkedin': 'https://www.linkedin.com',
    'reddit': 'https://www.reddit.com',
    'discord': 'https://discord.com',
    'github': 'https://github.com',
    'gitlab': 'https://gitlab.com',
    'amazon': 'https://www.amazon.com',
    'flipkart': 'https://www.flipkart.com',
    'paypal': 'https://www.paypal.com',
    'netflix': 'https://www.netflix.com',
    'spotify': 'https://www.spotify.com',
    'dropbox': 'https://www.dropbox.com',
    'zoom': 'https://zoom.us',
    'slack': 'https://slack.com',
    'proton': 'https://account.proton.me',
    'protonmail': 'https://account.proton.me',
}


class StoreError(Exception):
    pass


class WrongPassword(StoreError):
    pass


def suggest_url(name):
    """Return the known login page for a site name like 'Gmail' or 'yahoo.com', or ''."""
    key = (name or '').strip().lower().replace(' ', '')
    for suffix in ('.com', '.in', '.org', '.net', '.me'):
        if key.endswith(suffix):
            key = key[:-len(suffix)]
    return KNOWN_SITES.get(key, '')


def generate_password(length=20):
    """Random password containing at least one of each character class."""
    symbols = '!@#$%^&*()-_=+[]{};:,.?'
    classes = (string.ascii_lowercase, string.ascii_uppercase, string.digits, symbols)
    alphabet = ''.join(classes)
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        if all(any(c in cls for c in password) for cls in classes):
            return password


def password_strength(password):
    """Rough strength label for user feedback, not a security guarantee."""
    classes = sum(any(c in cls for c in password) for cls in (
        string.ascii_lowercase, string.ascii_uppercase, string.digits, string.punctuation))
    if len(password) < MIN_MASTER_LENGTH:
        return 'Too short'
    if len(password) >= 16 or (len(password) >= 12 and classes >= 3):
        return 'Strong'
    if len(password) >= 10 and classes >= 2:
        return 'Good'
    return 'Weak'


def derive_key(master, salt, memory, iterations, lanes):
    kdf = Argon2id(salt=salt, length=32, iterations=iterations, lanes=lanes, memory_cost=memory)
    return kdf.derive(master.encode('utf-8'))


class Store:
    """Folders of accounts, encrypted at rest with a key derived from the master password."""

    def __init__(self, path=None):
        self.path = Path(path or DEFAULT_PATH)
        self.folders = {}
        self._key = None
        self._kdf = None

    @property
    def unlocked(self):
        return self._key is not None

    def exists(self):
        return self.path.exists()

    def create(self, master):
        if self.exists():
            raise StoreError('A vault already exists at %s' % self.path)
        self._set_master(master)
        self.folders = {}
        self.save()

    def unlock(self, master):
        try:
            blob = self.path.read_bytes()
        except FileNotFoundError:
            raise StoreError('No vault at %s' % self.path)
        if len(blob) < HEADER.size or not blob.startswith(MAGIC):
            raise StoreError('%s is not a passx vault' % self.path)
        header = blob[:HEADER.size]
        _, memory, iterations, lanes, salt, nonce = HEADER.unpack(header)
        key = derive_key(master, salt, memory, iterations, lanes)
        try:
            plain = AESGCM(key).decrypt(nonce, blob[HEADER.size:], header)
        except InvalidTag:
            raise WrongPassword('Wrong master password')
        self.folders = json.loads(plain.decode('utf-8'))['folders']
        self._key = key
        self._kdf = (memory, iterations, lanes, salt)

    def lock(self):
        self._key = None
        self._kdf = None
        self.folders = {}

    def save(self):
        if not self.unlocked:
            raise StoreError('Vault is locked')
        memory, iterations, lanes, salt = self._kdf
        # a fresh nonce for every save; never reuse one with the same key
        header = HEADER.pack(MAGIC, memory, iterations, lanes, salt, os.urandom(12))
        plain = json.dumps({'version': 1, 'folders': self.folders}).encode('utf-8')
        ciphertext = AESGCM(self._key).encrypt(header[-12:], plain, header)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write(self.path, header + ciphertext)

    def change_master(self, current, new):
        if not self.unlocked:
            raise StoreError('Vault is locked')
        memory, iterations, lanes, salt = self._kdf
        if derive_key(current, salt, memory, iterations, lanes) != self._key:
            raise WrongPassword('Current master password is wrong')
        self._set_master(new)
        self.save()

    def _set_master(self, master):
        if len(master) < MIN_MASTER_LENGTH:
            raise StoreError('Master password must be at least %d characters' % MIN_MASTER_LENGTH)
        self._kdf = (KDF_MEMORY, KDF_ITERATIONS, KDF_LANES, os.urandom(16))
        memory, iterations, lanes, salt = self._kdf
        self._key = derive_key(master, salt, memory, iterations, lanes)

    # folders

    def add_folder(self, name):
        name = self._folder_name(name)
        if name in self.folders:
            raise StoreError("Folder '%s' already exists" % name)
        self.folders[name] = []

    def rename_folder(self, old, new):
        new = self._folder_name(new)
        if new != old and new in self.folders:
            raise StoreError("Folder '%s' already exists" % new)
        # rebuild to keep the folder's position
        self.folders = {(new if k == old else k): v for k, v in self.folders.items()}

    def delete_folder(self, name):
        del self.folders[name]

    # accounts

    def find(self, entry_id):
        for folder, entries in self.folders.items():
            for entry in entries:
                if entry['id'] == entry_id:
                    return folder, entry
        raise StoreError('Account not found')

    def add_entry(self, folder, **fields):
        folder = self._folder_name(folder)
        entry = {'id': uuid.uuid4().hex}
        entry.update(self._clean(fields))
        self.folders.setdefault(folder, []).append(entry)
        return entry

    def update_entry(self, entry_id, folder, **fields):
        folder = self._folder_name(folder)
        old_folder, entry = self.find(entry_id)
        entry.update(self._clean(fields))
        if folder != old_folder:
            self.folders[old_folder].remove(entry)
            self.folders.setdefault(folder, []).append(entry)
        return entry

    def delete_entry(self, entry_id):
        folder, entry = self.find(entry_id)
        self.folders[folder].remove(entry)

    @staticmethod
    def _folder_name(name):
        name = (name or '').strip()
        if not name:
            raise StoreError('Folder name cannot be empty')
        return name

    @staticmethod
    def _clean(fields):
        unknown = set(fields) - set(FIELDS)
        if unknown:
            raise StoreError('Unknown fields: %s' % ', '.join(sorted(unknown)))
        if 'title' in fields and not fields['title'].strip():
            raise StoreError('Account name cannot be empty')
        return {k: (v.strip() if k != 'password' else v) for k, v in fields.items()}
