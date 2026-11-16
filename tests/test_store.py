import pytest

from passx import store
from passx.store import Store, StoreError, WrongPassword

MASTER = 'correct horse battery'


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    # keep the suite quick; the parameters are read from the file header anyway
    monkeypatch.setattr(store, 'KDF_MEMORY', 8 * 1024)
    monkeypatch.setattr(store, 'KDF_ITERATIONS', 1)


@pytest.fixture
def vault(tmp_path):
    s = Store(tmp_path / 'passwords.vault')
    s.create(MASTER)
    return s


def reopen(vault, master=MASTER):
    s = Store(vault.path)
    s.unlock(master)
    return s


def test_roundtrip_and_no_plaintext_on_disk(vault):
    vault.add_entry('Gmail', title='Personal', username='me@gmail.com',
                    password='hunter2', url='https://mail.google.com')
    vault.save()

    raw = vault.path.read_bytes()
    assert b'hunter2' not in raw and b'Gmail' not in raw
    entry = reopen(vault).folders['Gmail'][0]
    assert entry['username'] == 'me@gmail.com' and entry['password'] == 'hunter2'


def test_wrong_master_password(vault):
    with pytest.raises(WrongPassword):
        reopen(vault, 'not the password')


def test_tampering_is_detected(vault):
    raw = bytearray(vault.path.read_bytes())
    raw[-1] ^= 1
    vault.path.write_bytes(bytes(raw))
    with pytest.raises(WrongPassword):
        reopen(vault)


def test_tampered_header_is_detected(vault):
    raw = bytearray(vault.path.read_bytes())
    raw[store.HEADER.size - 13] ^= 1  # last byte of the salt
    vault.path.write_bytes(bytes(raw))
    with pytest.raises(WrongPassword):
        reopen(vault)


def test_every_save_uses_a_new_nonce(vault):
    first = vault.path.read_bytes()
    vault.save()
    second = vault.path.read_bytes()
    assert first[store.HEADER.size - 12:store.HEADER.size] != second[store.HEADER.size - 12:store.HEADER.size]


def test_not_a_vault(tmp_path):
    path = tmp_path / 'junk'
    path.write_bytes(b'hello')
    with pytest.raises(StoreError):
        Store(path).unlock(MASTER)


def test_short_master_rejected(tmp_path):
    with pytest.raises(StoreError):
        Store(tmp_path / 'v').create('short')
    assert not (tmp_path / 'v').exists()


def test_change_master(vault):
    vault.add_entry('Yahoo', title='Old', password='pw')
    with pytest.raises(WrongPassword):
        vault.change_master('wrong', 'a brand new password')
    vault.change_master(MASTER, 'a brand new password')

    with pytest.raises(WrongPassword):
        reopen(vault)
    assert reopen(vault, 'a brand new password').folders['Yahoo'][0]['title'] == 'Old'


def test_lock_forgets_everything(vault):
    vault.add_entry('Gmail', title='Personal', password='pw')
    vault.lock()
    assert not vault.unlocked and vault.folders == {}
    with pytest.raises(StoreError):
        vault.save()


def test_folders(vault):
    vault.add_folder('Gmail')
    vault.add_folder('Yahoo')
    with pytest.raises(StoreError):
        vault.add_folder(' Gmail ')
    with pytest.raises(StoreError):
        vault.add_folder('   ')
    entry = vault.add_entry('Gmail', title='Personal', password='pw')

    vault.rename_folder('Gmail', 'Google')
    assert list(vault.folders) == ['Google', 'Yahoo']
    assert vault.find(entry['id'])[0] == 'Google'
    with pytest.raises(StoreError):
        vault.rename_folder('Google', 'Yahoo')

    vault.delete_folder('Google')
    with pytest.raises(StoreError):
        vault.find(entry['id'])


def test_update_moves_entry_between_folders(vault):
    entry = vault.add_entry('Gmail', title='Work', password='pw')
    vault.update_entry(entry['id'], 'Outlook', title='Work', password='new')
    assert vault.folders['Gmail'] == []
    assert vault.folders['Outlook'][0]['password'] == 'new'

    vault.delete_entry(entry['id'])
    assert vault.folders['Outlook'] == []


def test_entry_validation(vault):
    with pytest.raises(StoreError):
        vault.add_entry('Gmail', title='  ', password='pw')
    with pytest.raises(StoreError):
        vault.add_entry('Gmail', title='x', colour='blue')
    with pytest.raises(StoreError):
        vault.add_entry('', title='x', password='pw')


def test_password_whitespace_is_kept(vault):
    entry = vault.add_entry('Gmail', title=' Personal ', password=' spaced ')
    assert entry['title'] == 'Personal' and entry['password'] == ' spaced '


@pytest.mark.parametrize('name, url', [
    ('Gmail', 'https://mail.google.com'),
    ('yahoo', 'https://login.yahoo.com'),
    ('Yahoo.com', 'https://login.yahoo.com'),
    ('Git Hub', 'https://github.com'),
    ('my local bank', ''),
    ('', ''),
])
def test_suggest_url(name, url):
    assert store.suggest_url(name) == url


def test_generate_password():
    pw = store.generate_password()
    assert len(pw) == 20
    assert any(c.isupper() for c in pw) and any(c.islower() for c in pw)
    assert any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)


def test_real_kdf_parameters_are_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'KDF_MEMORY', 64 * 1024)
    monkeypatch.setattr(store, 'KDF_ITERATIONS', 3)
    s = Store(tmp_path / 'v')
    s.create(MASTER)
    _, memory, iterations, lanes, _, _ = store.HEADER.unpack(s.path.read_bytes()[:store.HEADER.size])
    assert (memory, iterations, lanes) == (64 * 1024, 3, 4)
