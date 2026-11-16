#!/usr/bin/env python3
"""Tkinter front end for the master-password vault in passx.store."""
import time
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox, simpledialog, ttk

from passx.store import (MIN_MASTER_LENGTH, Store, StoreError, WrongPassword,
                         generate_password, password_strength, suggest_url)

CLIPBOARD_CLEAR_SECONDS = 30
AUTO_LOCK_SECONDS = 5 * 60
FOLDER_PREFIX = 'folder:'


class PasswordField(ttk.Frame):
    """Masked entry with a Show toggle."""

    def __init__(self, parent, variable, width=30):
        super().__init__(parent)
        self.entry = ttk.Entry(self, textvariable=variable, show='•', width=width)
        self.entry.pack(side='left', fill='x', expand=True)
        self.shown = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text='Show', variable=self.shown,
                        command=self._toggle).pack(side='left', padx=(6, 0))

    def _toggle(self):
        self.entry.configure(show='' if self.shown.get() else '•')


class LockScreen(ttk.Frame):
    """Create a new master password, or unlock an existing vault."""

    def __init__(self, app):
        super().__init__(app, padding=40)
        self.app = app
        self.creating = not app.store.exists()
        self.master_pw = tk.StringVar()
        self.confirm = tk.StringVar()
        self.message = tk.StringVar()

        ttk.Label(self, text='Passx', style='Title.TLabel').pack(pady=(0, 4))
        if self.creating:
            ttk.Label(self, text='Create a master password to protect your vault.').pack()
            ttk.Label(self, text="It can't be recovered if you forget it.",
                      style='Hint.TLabel').pack(pady=(0, 16))
        else:
            ttk.Label(self, text='Enter your master password to unlock.').pack(pady=(0, 16))

        form = ttk.Frame(self)
        form.pack()
        ttk.Label(form, text='Master password').grid(row=0, column=0, sticky='w', pady=4)
        field = PasswordField(form, self.master_pw)
        field.grid(row=0, column=1, sticky='ew', padx=(8, 0))
        if self.creating:
            ttk.Label(form, text='Confirm').grid(row=1, column=0, sticky='w', pady=4)
            PasswordField(form, self.confirm).grid(row=1, column=1, sticky='ew', padx=(8, 0))
            self.strength = tk.StringVar()
            ttk.Label(form, textvariable=self.strength, style='Hint.TLabel').grid(
                row=2, column=1, sticky='w', padx=(8, 0))
            self.master_pw.trace_add('write', self._update_strength)

        ttk.Button(self, text='Create vault' if self.creating else 'Unlock',
                   style='Accent.TButton', command=self.submit).pack(pady=(16, 8))
        ttk.Label(self, textvariable=self.message, style='Error.TLabel').pack()

        field.entry.focus_set()
        self.bind_all('<Return>', lambda e: self.submit())

    def _update_strength(self, *_):
        pw = self.master_pw.get()
        self.strength.set('Strength: ' + password_strength(pw) if pw else '')

    def submit(self):
        master = self.master_pw.get()
        try:
            if self.creating:
                if len(master) < MIN_MASTER_LENGTH:
                    raise StoreError('Use at least %d characters' % MIN_MASTER_LENGTH)
                if master != self.confirm.get():
                    raise StoreError('Passwords do not match')
                self.app.store.create(master)
            else:
                self.app.store.unlock(master)
        except WrongPassword:
            self.master_pw.set('')
            self.message.set('Wrong master password')
            return
        except (StoreError, OSError, ValueError) as e:
            self.message.set(str(e))
            return
        self.unbind_all('<Return>')
        self.app.show_main()


class AccountDialog(tk.Toplevel):
    """Add or edit an account. Calls on_save(folder, fields) when confirmed."""

    def __init__(self, app, folders, on_save, folder='', entry=None):
        super().__init__(app)
        self.title('Edit account' if entry else 'Add account')
        self.transient(app)
        self.resizable(False, False)
        self.on_save = on_save
        entry = entry or {}

        self.folder = tk.StringVar(value=folder)
        self.title_var = tk.StringVar(value=entry.get('title', ''))
        self.username = tk.StringVar(value=entry.get('username', ''))
        self.password = tk.StringVar(value=entry.get('password', ''))
        self.url = tk.StringVar(value=entry.get('url', ''))
        self.error = tk.StringVar()
        # the last value we filled in ourselves, so we never overwrite a typed link
        self.auto_url = self.url.get() if self.url.get() == suggest_url(folder) else None

        body = ttk.Frame(self, padding=16)
        body.pack(fill='both', expand=True)
        body.columnconfigure(1, weight=1)

        def row(r, label, widget, hint=None):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky='nw', pady=4, padx=(0, 8))
            widget.grid(row=r, column=1, sticky='ew', pady=4)
            if hint:
                ttk.Label(body, text=hint, style='Hint.TLabel').grid(row=r + 1, column=1, sticky='w')

        folder_box = ttk.Combobox(body, textvariable=self.folder, values=sorted(folders), width=34)
        row(0, 'Folder', folder_box, 'Pick a folder or type a new name, e.g. Gmail')
        title_entry = ttk.Entry(body, textvariable=self.title_var, width=36)
        row(2, 'Account name', title_entry, 'e.g. Personal, Work, or the email address')
        row(4, 'Username / email', ttk.Entry(body, textvariable=self.username, width=36))

        pw_row = ttk.Frame(body)
        PasswordField(pw_row, self.password, width=24).pack(side='left', fill='x', expand=True)
        ttk.Button(pw_row, text='Generate', command=self._generate).pack(side='left', padx=(6, 0))
        row(5, 'Password', pw_row)

        row(6, 'Website', ttk.Entry(body, textvariable=self.url, width=36),
            'Filled in for known sites. Add or change the link if needed.')

        ttk.Label(body, text='Notes').grid(row=8, column=0, sticky='nw', pady=4)
        self.notes = tk.Text(body, width=36, height=3, wrap='word')
        self.notes.insert('1.0', entry.get('notes', ''))
        self.notes.grid(row=8, column=1, sticky='ew', pady=4)

        ttk.Label(body, textvariable=self.error, style='Error.TLabel').grid(
            row=9, column=0, columnspan=2, sticky='w')
        buttons = ttk.Frame(body)
        buttons.grid(row=10, column=0, columnspan=2, sticky='e', pady=(8, 0))
        ttk.Button(buttons, text='Cancel', command=self.destroy).pack(side='right')
        ttk.Button(buttons, text='Save', style='Accent.TButton',
                   command=self._save).pack(side='right', padx=(0, 6))

        self.folder.trace_add('write', self._suggest_url)
        self.title_var.trace_add('write', self._suggest_url)
        if not self.url.get():
            self._suggest_url()

        self.bind('<Return>', lambda e: self._save() if e.widget is not self.notes else None)
        self.bind('<Escape>', lambda e: self.destroy())
        (title_entry if folder else folder_box).focus_set()
        self.grab_set()

    def _suggest_url(self, *_):
        if self.url.get() and self.url.get() != self.auto_url:
            return
        suggestion = suggest_url(self.folder.get()) or suggest_url(self.title_var.get())
        self.auto_url = suggestion
        self.url.set(suggestion)

    def _generate(self):
        self.password.set(generate_password())

    def _save(self):
        folder = self.folder.get().strip()
        fields = {
            'title': self.title_var.get(),
            'username': self.username.get(),
            'password': self.password.get(),
            'url': self.url.get(),
            'notes': self.notes.get('1.0', 'end-1c'),
        }
        if not folder:
            self.error.set('Choose or type a folder name')
            return
        if not fields['title'].strip():
            self.error.set('Enter an account name')
            return
        if not fields['password']:
            self.error.set('Enter or generate a password')
            return
        try:
            self.on_save(folder, fields)
        except StoreError as e:
            self.error.set(str(e))
            return
        self.destroy()


class ChangeMasterDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.title('Change master password')
        self.transient(app)
        self.resizable(False, False)
        self.app = app
        self.current = tk.StringVar()
        self.new = tk.StringVar()
        self.confirm = tk.StringVar()
        self.error = tk.StringVar()

        body = ttk.Frame(self, padding=16)
        body.pack()
        for r, (label, var) in enumerate((('Current password', self.current),
                                          ('New password', self.new),
                                          ('Confirm new', self.confirm))):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky='w', pady=4, padx=(0, 8))
            PasswordField(body, var).grid(row=r, column=1, sticky='ew')
        self.strength = tk.StringVar()
        ttk.Label(body, textvariable=self.strength, style='Hint.TLabel').grid(row=3, column=1, sticky='w')
        self.new.trace_add('write', lambda *_: self.strength.set(
            'Strength: ' + password_strength(self.new.get()) if self.new.get() else ''))
        ttk.Label(body, textvariable=self.error, style='Error.TLabel').grid(
            row=4, column=0, columnspan=2, sticky='w')
        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky='e', pady=(8, 0))
        ttk.Button(buttons, text='Cancel', command=self.destroy).pack(side='right')
        ttk.Button(buttons, text='Change', style='Accent.TButton',
                   command=self._save).pack(side='right', padx=(0, 6))
        self.bind('<Return>', lambda e: self._save())
        self.bind('<Escape>', lambda e: self.destroy())
        self.grab_set()

    def _save(self):
        if self.new.get() != self.confirm.get():
            self.error.set('New passwords do not match')
            return
        try:
            self.app.store.change_master(self.current.get(), self.new.get())
        except (StoreError, OSError) as e:
            self.error.set(str(e))
            return
        self.app.set_status('Master password changed.')
        self.destroy()


class MainScreen(ttk.Frame):
    def __init__(self, app):
        super().__init__(app, padding=8)
        self.app = app
        self.store = app.store
        self.search = tk.StringVar()

        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', pady=(0, 8))
        for text, command in (('New folder', self.new_folder),
                              ('Add account', self.add_account),
                              ('Edit', self.edit_selected),
                              ('Delete', self.delete_selected)):
            ttk.Button(toolbar, text=text, command=command).pack(side='left', padx=(0, 4))
        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=6)
        for text, command in (('Copy password', self.copy_password),
                              ('Copy username', self.copy_username),
                              ('Open website', self.open_website)):
            ttk.Button(toolbar, text=text, command=command).pack(side='left', padx=(0, 4))
        ttk.Button(toolbar, text='Lock', command=app.lock).pack(side='right')
        search = ttk.Entry(toolbar, textvariable=self.search, width=22)
        search.pack(side='right', padx=(0, 8))
        ttk.Label(toolbar, text='Search').pack(side='right', padx=(0, 4))
        self.search.trace_add('write', lambda *_: self.refresh())

        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=('username', 'url'), selectmode='browse')
        self.tree.heading('#0', text='Folder / account')
        self.tree.heading('username', text='Username / email')
        self.tree.heading('url', text='Website')
        self.tree.column('#0', width=240)
        self.tree.column('username', width=240)
        self.tree.column('url', width=260)
        scroll = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.tree.tag_configure('folder', font=app.bold_font)

        self.menu = tk.Menu(self, tearoff=False)
        self.menu.add_command(label='Copy password', command=self.copy_password)
        self.menu.add_command(label='Copy username', command=self.copy_username)
        self.menu.add_command(label='Open website', command=self.open_website)
        self.menu.add_separator()
        self.menu.add_command(label='Edit', command=self.edit_selected)
        self.menu.add_command(label='Delete', command=self.delete_selected)

        self.tree.bind('<Double-1>', self._on_double_click)
        self.tree.bind('<Button-3>', self._on_right_click)
        self.tree.bind('<Control-c>', lambda e: self.copy_password())
        self.tree.bind('<Control-b>', lambda e: self.copy_username())
        self.tree.bind('<Delete>', lambda e: self.delete_selected())
        self.tree.bind('<Return>', lambda e: self.edit_selected())

        hint = ('Double-click or Ctrl+C copies the password, then paste with Ctrl+V. '
                'Ctrl+B copies the username.')
        ttk.Label(self, text=hint, style='Hint.TLabel').pack(anchor='w', pady=(6, 0))

        self.refresh()
        self.tree.focus_set()

    # tree

    def refresh(self, select=None):
        query = self.search.get().strip().lower()
        open_state = {iid: self.tree.item(iid, 'open') for iid in self.tree.get_children()}
        self.tree.delete(*self.tree.get_children())
        for folder in sorted(self.store.folders, key=str.lower):
            entries = sorted(self.store.folders[folder], key=lambda e: e['title'].lower())
            if query and query not in folder.lower():
                entries = [e for e in entries if any(
                    query in e.get(k, '').lower() for k in ('title', 'username', 'url', 'notes'))]
                if not entries:
                    continue
            fid = FOLDER_PREFIX + folder
            self.tree.insert('', 'end', iid=fid, text='%s  (%d)' % (folder, len(entries)),
                             open=bool(query) or open_state.get(fid, True), tags=('folder',))
            for e in entries:
                self.tree.insert(fid, 'end', iid=e['id'], text=e['title'],
                                 values=(e.get('username', ''), e.get('url', '')))
        if select and self.tree.exists(select):
            self.tree.selection_set(select)
            self.tree.focus(select)
            self.tree.see(select)

    def selected(self):
        """Return ('folder', name), ('entry', id) or (None, None)."""
        sel = self.tree.selection()
        if not sel:
            return None, None
        iid = sel[0]
        if iid.startswith(FOLDER_PREFIX):
            return 'folder', iid[len(FOLDER_PREFIX):]
        return 'entry', iid

    def selected_entry(self):
        kind, value = self.selected()
        if kind != 'entry':
            self.app.set_status('Select an account first.')
            return None, None
        return self.store.find(value)

    def selected_folder_name(self):
        kind, value = self.selected()
        if kind == 'folder':
            return value
        if kind == 'entry':
            return self.store.find(value)[0]
        return ''

    def _on_double_click(self, event):
        if self.tree.identify_row(event.y) and self.selected()[0] == 'entry':
            self.copy_password()
            return 'break'

    def _on_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            if not row.startswith(FOLDER_PREFIX):
                self.menu.tk_popup(event.x_root, event.y_root)

    def _commit(self, select=None, status=None):
        try:
            self.store.save()
        except (StoreError, OSError) as e:
            messagebox.showerror('Save failed', 'Could not save the vault:\n%s' % e, parent=self)
            return False
        self.refresh(select)
        if status:
            self.app.set_status(status)
        return True

    # actions

    def new_folder(self):
        name = simpledialog.askstring('New folder', 'Folder name (e.g. Gmail, Yahoo, Banking):',
                                      parent=self)
        if name is None:
            return
        try:
            self.store.add_folder(name)
        except StoreError as e:
            messagebox.showerror('New folder', str(e), parent=self)
            return
        self._commit(FOLDER_PREFIX + name.strip(), "Folder '%s' created." % name.strip())

    def add_account(self):
        def on_save(folder, fields):
            entry = self.store.add_entry(folder, **fields)
            if not self._commit(entry['id'], "Saved '%s' in %s." % (entry['title'], folder)):
                self.store.delete_entry(entry['id'])
        AccountDialog(self.app, self.store.folders, on_save, folder=self.selected_folder_name())

    def edit_selected(self):
        kind, value = self.selected()
        if kind == 'folder':
            self.rename_folder(value)
            return
        if kind != 'entry':
            self.app.set_status('Select an account or folder first.')
            return
        folder, entry = self.store.find(value)

        def on_save(new_folder, fields):
            self.store.update_entry(entry['id'], new_folder, **fields)
            self._commit(entry['id'], "Updated '%s'." % entry['title'])
        AccountDialog(self.app, self.store.folders, on_save, folder=folder, entry=dict(entry))

    def rename_folder(self, folder):
        name = simpledialog.askstring('Rename folder', 'New name:', initialvalue=folder, parent=self)
        if name is None or name.strip() == folder:
            return
        try:
            self.store.rename_folder(folder, name)
        except StoreError as e:
            messagebox.showerror('Rename folder', str(e), parent=self)
            return
        self._commit(FOLDER_PREFIX + name.strip(), 'Folder renamed.')

    def delete_selected(self):
        kind, value = self.selected()
        if kind == 'folder':
            count = len(self.store.folders[value])
            msg = "Delete folder '%s'" % value
            msg += ' and its %d account(s)?' % count if count else '?'
            if messagebox.askyesno('Delete folder', msg, icon='warning', parent=self):
                self.store.delete_folder(value)
                self._commit(status="Folder '%s' deleted." % value)
        elif kind == 'entry':
            folder, entry = self.store.find(value)
            if messagebox.askyesno('Delete account', "Delete '%s' from %s?" % (entry['title'], folder),
                                   icon='warning', parent=self):
                self.store.delete_entry(value)
                self._commit(status="Deleted '%s'." % entry['title'])
        else:
            self.app.set_status('Select an account or folder first.')

    def copy_password(self):
        folder, entry = self.selected_entry()
        if entry:
            self.app.copy_secret(entry['password'],
                                 'Password for %s / %s copied' % (folder, entry['title']))

    def copy_username(self):
        folder, entry = self.selected_entry()
        if entry:
            if not entry.get('username'):
                self.app.set_status('No username saved for this account.')
                return
            self.app.copy_secret(entry['username'], 'Username copied', clear=False)

    def open_website(self):
        folder, entry = self.selected_entry()
        if not entry:
            return
        url = entry.get('url')
        if not url:
            if messagebox.askyesno('No website', 'No website saved for this account. Add one now?',
                                   parent=self):
                self.edit_selected()
            return
        if '://' not in url:
            url = 'https://' + url
        webbrowser.open(url)


class App(tk.Tk):
    def __init__(self, store=None):
        super().__init__()
        self.title('Passx')
        self.geometry('900x560')
        self.minsize(700, 400)
        self.store = store or Store()
        self.screen = None
        self.clip_value = None
        self.clip_job = None
        self.last_activity = time.monotonic()
        self.status = tk.StringVar()

        self._setup_style()
        menubar = tk.Menu(self)
        vault_menu = tk.Menu(menubar, tearoff=False)
        vault_menu.add_command(label='Change master password…', command=self.change_master)
        vault_menu.add_command(label='Lock', accelerator='Ctrl+L', command=self.lock)
        vault_menu.add_separator()
        vault_menu.add_command(label='Quit', accelerator='Ctrl+Q', command=self.quit_app)
        menubar.add_cascade(label='Vault', menu=vault_menu)
        self.vault_menu = vault_menu
        self.config(menu=menubar)

        ttk.Label(self, textvariable=self.status, style='Status.TLabel',
                  anchor='w', padding=(8, 4)).pack(side='bottom', fill='x')
        self.bind_all('<Control-l>', lambda e: self.lock())
        self.bind_all('<Control-q>', lambda e: self.quit_app())
        for seq in ('<Any-KeyPress>', '<Any-ButtonPress>', '<Motion>'):
            self.bind_all(seq, self._touch, add='+')
        self.protocol('WM_DELETE_WINDOW', self.quit_app)
        self.after(15000, self._check_idle)
        self.show_lock()

    def _setup_style(self):
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        default = tkfont.nametofont('TkDefaultFont')
        self.bold_font = default.copy()
        self.bold_font.configure(weight='bold')
        title_font = default.copy()
        title_font.configure(size=20, weight='bold')
        style.configure('Title.TLabel', font=title_font)
        style.configure('Hint.TLabel', foreground='#666666')
        style.configure('Error.TLabel', foreground='#b3261e')
        style.configure('Status.TLabel', background='#ececec')
        style.configure('Accent.TButton', font=self.bold_font)
        style.configure('Treeview', rowheight=24)
        self._fonts = (title_font,)  # keep a reference so Tk doesn't drop the font

    def _show(self, screen):
        if self.screen is not None:
            self.screen.destroy()
        self.screen = screen
        screen.pack(fill='both', expand=True)

    def show_lock(self):
        self.vault_menu.entryconfigure(0, state='disabled')
        self.vault_menu.entryconfigure(1, state='disabled')
        self._show(LockScreen(self))

    def show_main(self):
        self.vault_menu.entryconfigure(0, state='normal')
        self.vault_menu.entryconfigure(1, state='normal')
        self.last_activity = time.monotonic()
        self._show(MainScreen(self))
        self.set_status('Unlocked. %d folder(s).' % len(self.store.folders))

    def lock(self):
        if not self.store.unlocked:
            return
        for window in self.winfo_children():
            if isinstance(window, tk.Toplevel):
                window.destroy()
        self.clear_clipboard()
        self.store.lock()
        self.show_lock()
        self.set_status('Locked.')

    def change_master(self):
        if self.store.unlocked:
            ChangeMasterDialog(self)

    def set_status(self, text):
        self.status.set(text)

    def copy_secret(self, value, message, clear=True):
        self.clipboard_clear()
        self.clipboard_append(value)
        if self.clip_job:
            self.after_cancel(self.clip_job)
            self.clip_job = None
        if clear:
            self.clip_value = value
            self.clip_job = self.after(CLIPBOARD_CLEAR_SECONDS * 1000, self.clear_clipboard)
            message += ' (clears in %ds). Paste with Ctrl+V.' % CLIPBOARD_CLEAR_SECONDS
        else:
            self.clip_value = None
            message += '.'
        self.set_status(message)

    def clear_clipboard(self):
        self.clip_job = None
        if self.clip_value is None:
            return
        try:
            # don't wipe something the user copied in the meantime
            if self.clipboard_get() == self.clip_value:
                self.clipboard_clear()
                self.clipboard_append('')
                self.set_status('Clipboard cleared.')
        except tk.TclError:
            pass
        self.clip_value = None

    def _touch(self, _event=None):
        self.last_activity = time.monotonic()

    def _check_idle(self):
        if self.store.unlocked and time.monotonic() - self.last_activity > AUTO_LOCK_SECONDS:
            self.lock()
            self.set_status('Locked after %d minutes of inactivity.' % (AUTO_LOCK_SECONDS // 60))
        self.after(15000, self._check_idle)

    def quit_app(self):
        self.clear_clipboard()
        self.store.lock()
        self.destroy()


def main():
    App().mainloop()


if __name__ == '__main__':
    main()
