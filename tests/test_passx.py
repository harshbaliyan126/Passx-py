import os
import shelve
import shutil
import subprocess
import tempfile

import gnupg
import pytest

from passx import passx

EMAIL = 'test@passx.invalid'


@pytest.fixture(scope='session')
def gnupghome():
    # gpg-agent socket paths have a length limit, so avoid pytest's long tmp_path
    home = tempfile.mkdtemp(prefix='passx-gpg-')
    os.chmod(home, 0o700)
    gpg = gnupg.GPG(gnupghome=home)
    key = gpg.gen_key(gpg.gen_key_input(
        key_type='RSA', key_length=2048, name_email=EMAIL, no_protection=True))
    assert key.fingerprint, key.stderr
    yield home
    subprocess.run(['gpgconf', '--homedir', home, '--kill', 'gpg-agent'], check=False)
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def config(tmp_path, gnupghome, monkeypatch):
    monkeypatch.setenv('GNUPGHOME', gnupghome)
    monkeypatch.setattr(passx, 'CONFIG_DIR', tmp_path / 'passx')
    (tmp_path / 'passx').mkdir()
    (tmp_path / 'passx' / passx.RECIPIENT_FILE).write_text(EMAIL + '\n')
    return tmp_path / 'passx'


def test_roundtrip_never_stores_plaintext(config):
    vault = passx.Vault().load()
    vault.accounts['gmail'] = 'hunter2'
    vault.save()

    assert b'hunter2' not in (config / passx.VAULT_FILE).read_bytes()
    assert passx.Vault().load().accounts == {'gmail': 'hunter2'}
    assert oct(os.stat(config).st_mode & 0o777) == '0o700'


def test_failed_encryption_keeps_old_vault(config):
    vault = passx.Vault().load()
    vault.accounts['gmail'] = 'hunter2'
    vault.save()
    before = (config / passx.VAULT_FILE).read_bytes()

    (config / passx.RECIPIENT_FILE).write_text('nobody@nowhere.invalid')
    vault.accounts['other'] = 'x'
    with pytest.raises(passx.PassxError):
        vault.save()

    assert (config / passx.VAULT_FILE).read_bytes() == before


def test_failed_decryption_leaves_vault_untouched(config):
    (config / passx.VAULT_FILE).write_bytes(b'not a gpg file')
    with pytest.raises(passx.PassxError):
        passx.Vault().load()
    assert (config / passx.VAULT_FILE).read_bytes() == b'not a gpg file'


def write_legacy_shelve(path, accounts):
    with shelve.open(str(path)) as db:
        db.update(accounts)


def test_migrates_encrypted_legacy_vault(config, gnupghome, tmp_path):
    (config / passx.RECIPIENT_FILE).unlink()
    legacy = config / passx.LEGACY_DIR
    legacy.mkdir()
    # the old reader chopped a character off when the file ended in a newline
    (legacy / passx.RECIPIENT_FILE).write_text(EMAIL + '\n')
    write_legacy_shelve(tmp_path / 'pass', {'gmail': 'hunter2', 'bank': 's3cret'})
    gpg = gnupg.GPG(gnupghome=gnupghome)
    with open(tmp_path / 'pass', 'rb') as f:
        assert gpg.encrypt_file(f, [EMAIL], output=str(legacy / 'pass.gpg')).ok

    assert passx.Vault().load().accounts == {'gmail': 'hunter2', 'bank': 's3cret'}
    assert passx.Vault().load().accounts == {'gmail': 'hunter2', 'bank': 's3cret'}
    assert not (legacy / 'pass.gpg').exists()
    assert (legacy / 'pass.gpg.migrated').exists()


def test_migrates_leftover_plaintext_legacy_vault(config):
    legacy = config / passx.LEGACY_DIR
    legacy.mkdir()
    write_legacy_shelve(legacy / 'pass', {'gmail': 'hunter2'})

    assert passx.Vault().load().accounts == {'gmail': 'hunter2'}
    assert not (legacy / 'pass').exists()


def test_cli_add_list_copy_delete(config, monkeypatch, capsys):
    answers = iter(['n'])
    monkeypatch.setattr('builtins.input', lambda prompt='': next(answers))
    monkeypatch.setattr(passx.getpass, 'getpass', lambda prompt='': 'hunter2')
    assert passx.main(['-a', 'gmail']) == 0

    assert passx.main(['--list']) == 0
    assert capsys.readouterr().out.splitlines()[-1] == 'gmail'

    copied = []
    monkeypatch.setattr(passx.pyperclip, 'copy', copied.append)
    assert passx.main(['gmail', '-t', '0']) == 0
    assert copied == ['hunter2']

    assert passx.main(['-d', 'gmail']) == 0
    assert passx.Vault().load().accounts == {}


def test_cli_rejects_mismatched_confirmation(config, monkeypatch):
    monkeypatch.setattr('builtins.input', lambda prompt='': 'n')
    passwords = iter(['hunter2', 'typo'])
    monkeypatch.setattr(passx.getpass, 'getpass', lambda prompt='': next(passwords))
    assert passx.main(['-a', 'gmail']) == 1
    assert not (config / passx.VAULT_FILE).exists()


def test_cli_unknown_account_is_an_error(config, capsys):
    assert passx.main(['missing']) == 1
    assert passx.main(['-d', 'missing']) == 1
    assert "doesn't exist" in capsys.readouterr().err


def test_cli_rejects_account_with_action(config):
    with pytest.raises(SystemExit):
        passx.main(['gmail', '--list'])
