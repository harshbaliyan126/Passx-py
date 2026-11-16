#!/usr/bin/env python3
"""Tkinter front end for the master-password vault in passx.store."""
import time
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import ttk

from passx.store import (MIN_MASTER_LENGTH, Store, StoreError, WrongPassword,
                         generate_password, password_strength, suggest_url)

CLIPBOARD_CLEAR_SECONDS = 30
AUTO_LOCK_SECONDS = 5 * 60
ALL = None  # sidebar selection that shows every folder

BG = '#f4f5f9'
SURFACE = '#ffffff'
HOVER = '#f6f7fb'
BORDER = '#e1e4ec'
TEXT = '#1d2130'
MUTED = '#6b7185'
ACCENT = '#4f5bd5'
ACCENT_HOVER = '#3f4bc4'
ACCENT_SOFT = '#eaecfc'
DANGER = '#d23c3c'
DANGER_SOFT = '#fcebeb'
SIDEBAR = '#1f2433'
SIDEBAR_HOVER = '#292f42'
SIDEBAR_ACTIVE = '#343b53'
SIDEBAR_TEXT = '#e7e9f0'
SIDEBAR_MUTED = '#8a90a6'
TOAST = '#262b3a'
AVATAR_COLORS = ('#4f5bd5', '#d9534f', '#2a9d8f', '#e08e0b',
                 '#8e44ad', '#1f7ae0', '#c2185b', '#43a047')
STRENGTH = {  # label -> (filled segments, colour)
    'Too short': (1, DANGER),
    'Weak': (2, '#e08e0b'),
    'Good': (3, '#1f7ae0'),
    'Strong': (4, '#2e9d5b'),
}

FONTS = {}


def setup_fonts(root):
    family = tkfont.nametofont('TkDefaultFont').actual('family')
    mono = tkfont.nametofont('TkFixedFont').actual('family')
    for name, fam, size, weight in (('body', family, 10, 'normal'),
                                    ('bold', family, 10, 'bold'),
                                    ('small', family, 9, 'normal'),
                                    ('smallbold', family, 9, 'bold'),
                                    ('caption', family, 8, 'bold'),
                                    ('h2', family, 12, 'bold'),
                                    ('h1', family, 16, 'bold'),
                                    ('display', family, 22, 'bold'),
                                    ('mono', mono, 11, 'normal')):
        FONTS[name] = tkfont.Font(root, family=fam, size=size, weight=weight)


def label(parent, text='', font='body', fg=TEXT, **kw):
    kw.setdefault('bg', parent.cget('bg'))
    return tk.Label(parent, text=text, font=FONTS[font], fg=fg, **kw)


def bind_all_children(widget, sequence, func):
    widget.bind(sequence, func)
    for child in widget.winfo_children():
        bind_all_children(child, sequence, func)


def bind_hover(row, on_enter, on_leave):
    """Hover for a composite widget: moving between its children doesn't count as leaving."""
    def leave(e):
        inside = row.winfo_containing(e.x_root, e.y_root)
        if inside is None or not str(inside).startswith(str(row)):
            on_leave()
    row.bind('<Enter>', lambda e: on_enter())
    row.bind('<Leave>', leave)


def hex_rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


_circles = {}


def circle_image(color, bg, size):
    """Anti-aliased filled circle blended onto bg (Tk can't draw smooth circles itself)."""
    key = (color, bg, size)
    if key not in _circles:
        fg_rgb, bg_rgb = hex_rgb(color), hex_rgb(bg)
        r = size / 2
        samples = [(i + 0.5) / 4 for i in range(4)]
        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                cover = sum((x + sx - r) ** 2 + (y + sy - r) ** 2 <= r * r
                            for sx in samples for sy in samples) / 16
                row.append('#%02x%02x%02x' % tuple(
                    round(b + (f - b) * cover) for f, b in zip(fg_rgb, bg_rgb)))
            rows.append('{' + ' '.join(row) + '}')
        img = tk.PhotoImage(width=size, height=size)
        img.put(' '.join(rows))
        _circles[key] = img
    return _circles[key]


def avatar_color(name):
    return AVATAR_COLORS[sum(map(ord, name)) % len(AVATAR_COLORS)]


class Avatar(tk.Label):
    """Coloured circle with the first letter of a name."""

    def __init__(self, parent, name, size=36, font='bold', color=None):
        self.color = color or avatar_color(name)
        self.size = size
        bg = parent.cget('bg')
        super().__init__(parent, image=circle_image(self.color, bg, size), text=(name[:1] or '?').upper(),
                         compound='center', fg='white', font=FONTS[font], bg=bg, bd=0)

    def set_bg(self, bg):
        self.configure(bg=bg, image=circle_image(self.color, bg, self.size))


class Button(tk.Label):
    """Flat button that looks the same on every platform."""

    KINDS = {  # kind -> (background or None for parent's, foreground, hover background)
        'primary': (ACCENT, '#ffffff', ACCENT_HOVER),
        'destructive': (DANGER, '#ffffff', '#b83131'),
        'secondary': (SURFACE, TEXT, HOVER),
        'ghost': (None, ACCENT, ACCENT_SOFT),
        'danger': (None, DANGER, DANGER_SOFT),
        'sidebar': (None, SIDEBAR_MUTED, SIDEBAR_HOVER),
    }

    def __init__(self, parent, text, command, kind='secondary', small=False):
        bg, fg, self.hover_bg = self.KINDS[kind]
        self.base_bg = bg or parent.cget('bg')
        super().__init__(parent, text=text, bg=self.base_bg, fg=fg, cursor='hand2',
                         font=FONTS['smallbold' if small else 'bold'],
                         padx=10 if small else 16, pady=4 if small else 8)
        if kind == 'secondary':
            self.configure(highlightthickness=1, highlightbackground=BORDER, highlightcolor=BORDER)
        self.command = command
        self.bind('<Enter>', lambda e: self.configure(bg=self.hover_bg))
        self.bind('<Leave>', lambda e: self.configure(bg=self.base_bg))
        self.bind('<Button-1>', lambda e: self.command())


class Field(tk.Frame):
    """Bordered text entry with an optional placeholder and Show/Hide toggle."""

    def __init__(self, parent, variable, secret=False, placeholder='', width=32):
        super().__init__(parent, bg=BORDER, padx=1, pady=1)
        inner = tk.Frame(self, bg=SURFACE)
        inner.pack(fill='both', expand=True)
        self.variable = variable
        self.entry = tk.Entry(inner, textvariable=variable, relief='flat', bd=0, bg=SURFACE, fg=TEXT,
                              insertbackground=TEXT, font=FONTS['body'], width=width,
                              highlightthickness=0, show='•' if secret else '')
        self.entry.pack(side='left', fill='x', expand=True, padx=10, pady=8)
        self.entry.bind('<FocusIn>', self._focus_in, add='+')
        self.entry.bind('<FocusOut>', self._focus_out, add='+')
        self.placeholder = None
        if placeholder:
            self.placeholder = label(inner, placeholder, fg=MUTED, cursor='xterm')
            self.placeholder.bind('<Button-1>', lambda e: self.entry.focus_set())
            variable.trace_add('write', lambda *_: self._update_placeholder())
            self._update_placeholder()
        if secret:
            self.toggle = label(inner, 'Show', 'smallbold', ACCENT, cursor='hand2', padx=10)
            self.toggle.pack(side='right')
            self.toggle.bind('<Button-1>', self._toggle)

    def _focus_in(self, _e):
        self.configure(bg=ACCENT)
        self._update_placeholder()

    def _focus_out(self, _e):
        self.configure(bg=BORDER)
        self._update_placeholder()

    def _update_placeholder(self):
        if self.placeholder is None:
            return
        if self.variable.get():
            self.placeholder.place_forget()
        else:
            self.placeholder.place(in_=self.entry, x=0, rely=0.5, anchor='w')

    def _toggle(self, _e=None):
        hidden = self.entry.cget('show') != ''
        self.entry.configure(show='' if hidden else '•')
        self.toggle.configure(text='Hide' if hidden else 'Show')

    def focus(self):
        self.entry.focus_set()


class StrengthBar(tk.Frame):
    def __init__(self, parent, variable):
        super().__init__(parent, bg=parent.cget('bg'))
        bars = tk.Frame(self, bg=self.cget('bg'))
        bars.pack(side='left')
        self.segments = []
        for i in range(4):
            seg = tk.Frame(bars, bg=BORDER, width=44, height=4)
            seg.pack(side='left', padx=(0 if i == 0 else 4, 0))
            self.segments.append(seg)
        self.text = label(self, '', 'small', MUTED)
        self.text.pack(side='left', padx=(10, 0))
        self.variable = variable
        variable.trace_add('write', lambda *_: self.update_strength())
        self.update_strength()

    def update_strength(self):
        password = self.variable.get()
        strength = password_strength(password) if password else None
        filled, color = STRENGTH.get(strength, (0, BORDER))
        for i, seg in enumerate(self.segments):
            seg.configure(bg=color if i < filled else BORDER)
        self.text.configure(text=strength or '', fg=color if strength else MUTED)


class ScrollArea(tk.Frame):
    """Vertically scrolling frame; put children in .inner."""

    def __init__(self, parent):
        super().__init__(parent, bg=parent.cget('bg'))
        self.canvas = tk.Canvas(self, bg=self.cget('bg'), highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview,
                                 style='Slim.Vertical.TScrollbar')
        self.inner = tk.Frame(self.canvas, bg=self.cget('bg'))
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor='nw')
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.bar.pack(side='right', fill='y')
        self.inner.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.bind('<Enter>', self._bind_wheel)
        self.bind('<Leave>', self._unbind_wheel)

    def _bind_wheel(self, _e):
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.bind_all(seq, self._wheel)

    def _unbind_wheel(self, _e):
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.unbind_all(seq)

    def _wheel(self, e):
        if self.inner.winfo_height() <= self.canvas.winfo_height():
            return
        if e.num == 4 or e.delta > 0:
            self.canvas.yview_scroll(-2, 'units')
        else:
            self.canvas.yview_scroll(2, 'units')

    def see(self, widget):
        self.update_idletasks()
        total = self.inner.winfo_height()
        if total <= self.canvas.winfo_height():
            return
        top, bottom = widget.winfo_y(), widget.winfo_y() + widget.winfo_height()
        view_top = self.canvas.canvasy(0)
        view_bottom = view_top + self.canvas.winfo_height()
        if top < view_top:
            self.canvas.yview_moveto(top / total)
        elif bottom > view_bottom:
            self.canvas.yview_moveto((bottom - self.canvas.winfo_height()) / total)


class Dialog(tk.Toplevel):
    """Modal window with a title, a body to fill in and a button row."""

    def __init__(self, app, title, width=440):
        super().__init__(app, bg=SURFACE)
        self.app = app
        self.title(title)
        self.transient(app)
        self.resizable(False, False)
        self.error = tk.StringVar()
        outer = tk.Frame(self, bg=SURFACE, padx=28, pady=24)
        outer.pack(fill='both', expand=True)
        label(outer, title, 'h2').pack(anchor='w', pady=(0, 16))
        self.body = tk.Frame(outer, bg=SURFACE, width=width)
        self.body.pack(fill='both', expand=True)
        label(outer, textvariable=self.error, font='small', fg=DANGER, anchor='w',
              justify='left', wraplength=width).pack(fill='x', pady=(8, 0))
        self.footer = tk.Frame(outer, bg=SURFACE)
        self.footer.pack(fill='x', pady=(12, 0))
        self.bind('<Escape>', lambda e: self.destroy())

    def add_field(self, caption, widget, hint=None):
        label(self.body, caption.upper(), 'caption', MUTED).pack(anchor='w', pady=(10, 4))
        widget.pack(fill='x')
        if hint:
            label(self.body, hint, 'small', MUTED, anchor='w').pack(fill='x', pady=(4, 0))

    def add_buttons(self, confirm_text, on_confirm, kind='primary'):
        Button(self.footer, confirm_text, on_confirm, kind).pack(side='right')
        Button(self.footer, 'Cancel', self.destroy).pack(side='right', padx=(0, 8))

    def show(self, focus=None):
        self.update_idletasks()
        x = self.app.winfo_rootx() + (self.app.winfo_width() - self.winfo_reqwidth()) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry('+%d+%d' % (max(x, 0), max(y, 0)))
        self.grab_set()
        if focus is not None:
            focus.focus()


class PromptDialog(Dialog):
    def __init__(self, app, title, caption, on_save, initial=''):
        super().__init__(app, title, width=360)
        self.on_save = on_save
        self.value = tk.StringVar(value=initial)
        field = Field(self.body, self.value)
        self.add_field(caption, field)
        field.entry.select_range(0, 'end')
        self.add_buttons('Save', self._save)
        self.bind('<Return>', lambda e: self._save())
        self.show(field)

    def _save(self):
        try:
            self.on_save(self.value.get())
        except StoreError as e:
            self.error.set(str(e))
            return
        self.destroy()


class ConfirmDialog(Dialog):
    def __init__(self, app, title, message, confirm_text, on_confirm):
        super().__init__(app, title, width=360)
        self.on_confirm = on_confirm
        label(self.body, message, fg=MUTED, justify='left', wraplength=360, anchor='w').pack(fill='x')
        self.add_buttons(confirm_text, self._confirm, kind='destructive')
        self.bind('<Return>', lambda e: self._confirm())
        self.show()
        self.focus_set()

    def _confirm(self):
        self.destroy()
        self.on_confirm()


class AccountDialog(Dialog):
    """Add or edit an account. Calls on_save(folder, fields) when confirmed."""

    def __init__(self, app, folders, on_save, folder='', entry=None):
        super().__init__(app, 'Edit account' if entry else 'Add account')
        self.on_save = on_save
        entry = entry or {}
        self.folder = tk.StringVar(value=folder)
        self.title_var = tk.StringVar(value=entry.get('title', ''))
        self.username = tk.StringVar(value=entry.get('username', ''))
        self.password = tk.StringVar(value=entry.get('password', ''))
        self.url = tk.StringVar(value=entry.get('url', ''))
        # the last link we filled in ourselves, so we never overwrite a typed one
        self.auto_url = self.url.get() if self.url.get() == suggest_url(folder) else None

        folder_box = ttk.Combobox(self.body, textvariable=self.folder, values=sorted(folders, key=str.lower),
                                  font=FONTS['body'], style='Field.TCombobox')
        self.add_field('Folder', folder_box, 'Pick a folder or type a new name, e.g. Gmail')
        title_field = Field(self.body, self.title_var, placeholder='e.g. Personal, Work')
        self.add_field('Account name', title_field)
        self.add_field('Username or email', Field(self.body, self.username))

        pw_row = tk.Frame(self.body, bg=SURFACE)
        Field(pw_row, self.password, secret=True, width=24).pack(side='left', fill='x', expand=True)
        Button(pw_row, 'Generate', self._generate, 'ghost').pack(side='left', padx=(8, 0))
        self.add_field('Password', pw_row)
        StrengthBar(self.body, self.password).pack(anchor='w', pady=(6, 0))

        self.add_field('Website', Field(self.body, self.url, placeholder='https://'),
                       'Filled in for known sites. Add or change the link if needed.')

        notes_border = tk.Frame(self.body, bg=BORDER, padx=1, pady=1)
        self.notes = tk.Text(notes_border, height=3, wrap='word', relief='flat', bd=0, font=FONTS['body'],
                             fg=TEXT, bg=SURFACE, insertbackground=TEXT, padx=10, pady=8, highlightthickness=0)
        self.notes.insert('1.0', entry.get('notes', ''))
        self.notes.pack(fill='both')
        self.notes.bind('<FocusIn>', lambda e: notes_border.configure(bg=ACCENT))
        self.notes.bind('<FocusOut>', lambda e: notes_border.configure(bg=BORDER))
        self.add_field('Notes', notes_border)

        self.add_buttons('Save', self._save)
        self.folder.trace_add('write', self._suggest_url)
        self.title_var.trace_add('write', self._suggest_url)
        if not self.url.get():
            self._suggest_url()
        self.bind('<Return>', lambda e: self._save() if e.widget is not self.notes else None)
        self.show(title_field if folder else folder_box)

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


class ChangeMasterDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, 'Change master password', width=380)
        self.current = tk.StringVar()
        self.new = tk.StringVar()
        self.confirm = tk.StringVar()
        first = Field(self.body, self.current, secret=True)
        self.add_field('Current password', first)
        self.add_field('New password', Field(self.body, self.new, secret=True))
        StrengthBar(self.body, self.new).pack(anchor='w', pady=(6, 0))
        self.add_field('Confirm new password', Field(self.body, self.confirm, secret=True))
        self.add_buttons('Change password', self._save)
        self.bind('<Return>', lambda e: self._save())
        self.show(first)

    def _save(self):
        if self.new.get() != self.confirm.get():
            self.error.set('New passwords do not match')
            return
        try:
            self.app.store.change_master(self.current.get(), self.new.get())
        except (StoreError, OSError) as e:
            self.error.set(str(e))
            return
        self.app.toast('Master password changed')
        self.destroy()


class LockScreen(tk.Frame):
    """Create a new master password, or unlock an existing vault."""

    def __init__(self, app):
        super().__init__(app, bg=BG)
        self.app = app
        self.creating = not app.store.exists()
        self.master_pw = tk.StringVar()
        self.confirm = tk.StringVar()
        self.message = tk.StringVar()
        self.master_pw.trace_add('write', lambda *_: self.master_pw.get() and self.message.set(''))

        card = tk.Frame(self, bg=SURFACE, padx=44, pady=36, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER)
        card.place(relx=0.5, rely=0.46, anchor='center')
        Avatar(card, 'P', size=64, font='display', color=ACCENT).pack()
        label(card, 'Passx', 'display').pack(pady=(14, 2))
        label(card, 'Create a master password to protect your vault' if self.creating
              else 'Enter your master password to unlock', fg=MUTED).pack(pady=(0, 18))

        label(card, 'MASTER PASSWORD', 'caption', MUTED).pack(anchor='w', pady=(0, 4))
        field = Field(card, self.master_pw, secret=True, width=34)
        field.pack(fill='x')
        field.entry.bind('<Return>', lambda e: self.submit())
        if self.creating:
            StrengthBar(card, self.master_pw).pack(anchor='w', pady=(8, 0))
            label(card, 'CONFIRM PASSWORD', 'caption', MUTED).pack(anchor='w', pady=(14, 4))
            confirm = Field(card, self.confirm, secret=True, width=34)
            confirm.pack(fill='x')
            confirm.entry.bind('<Return>', lambda e: self.submit())

        label(card, textvariable=self.message, font='small', fg=DANGER).pack(pady=(10, 0))
        Button(card, 'Create vault' if self.creating else 'Unlock', self.submit, 'primary').pack(
            fill='x', pady=(6, 0))
        note = ("At least %d characters. It can't be recovered if you forget it." % MIN_MASTER_LENGTH
                if self.creating else 'Locks automatically after %d minutes of inactivity.'
                % (AUTO_LOCK_SECONDS // 60))
        label(card, note, 'small', MUTED).pack(pady=(14, 0))
        self.after(50, field.focus)

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
        self.app.show_main()


class MainScreen(tk.Frame):
    KEYS = ('<Control-c>', '<Control-b>', '<Control-n>', '<Control-f>', '<Delete>', '<Up>', '<Down>')

    def __init__(self, app):
        super().__init__(app, bg=BG)
        self.app = app
        self.store = app.store
        self.folder = ALL
        self.selected_id = None
        self.reveal = False
        self.rows = {}
        self.visible_ids = []
        self.search = tk.StringVar()

        self.sidebar = tk.Frame(self, bg=SIDEBAR, width=220)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        self.list_pane = tk.Frame(self, bg=SURFACE, width=330)
        self.list_pane.pack(side='left', fill='y')
        self.list_pane.pack_propagate(False)
        tk.Frame(self, bg=BORDER, width=1).pack(side='left', fill='y')
        self.detail = tk.Frame(self, bg=BG)
        self.detail.pack(side='left', fill='both', expand=True)

        self._build_sidebar()
        self._build_list_pane()

        app.bind('<Control-c>', self._key(self.copy_password))
        app.bind('<Control-b>', self._key(self.copy_username))
        app.bind('<Control-n>', lambda e: self.add_account())
        app.bind('<Control-f>', lambda e: self.search_field.focus())
        app.bind('<Delete>', self._key(self.delete_account))
        app.bind('<Up>', lambda e: self.move_selection(-1))
        app.bind('<Down>', lambda e: self.move_selection(1))
        self.refresh()

    def destroy(self):
        for seq in self.KEYS:
            self.app.unbind(seq)
        super().destroy()

    @staticmethod
    def _key(action):
        def handler(event):
            if isinstance(event.widget, (tk.Entry, tk.Text, ttk.Entry)):
                return None  # leave normal text editing alone
            action()
            return 'break'
        return handler

    # layout

    def _build_sidebar(self):
        brand = tk.Frame(self.sidebar, bg=SIDEBAR, padx=18, pady=20)
        brand.pack(fill='x')
        Avatar(brand, 'P', size=30, color=ACCENT).pack(side='left')
        label(brand, 'Passx', 'h2', SIDEBAR_TEXT).pack(side='left', padx=(10, 0))

        bottom = tk.Frame(self.sidebar, bg=SIDEBAR, padx=10, pady=14)
        bottom.pack(side='bottom', fill='x')
        for text, command in (('Change master password', lambda: ChangeMasterDialog(self.app)),
                              ('Lock vault  (Ctrl+L)', self.app.lock)):
            Button(bottom, text, command, 'sidebar', small=True).configure(anchor='w', padx=10)
            bottom.winfo_children()[-1].pack(fill='x', pady=(0, 2))

        self.folder_area = tk.Frame(self.sidebar, bg=SIDEBAR)
        self.folder_area.pack(fill='both', expand=True)

    def _build_list_pane(self):
        header = tk.Frame(self.list_pane, bg=SURFACE, padx=18, pady=18)
        header.pack(fill='x')
        top = tk.Frame(header, bg=SURFACE)
        top.pack(fill='x')
        self.list_title = label(top, '', 'h1', anchor='w')
        self.list_title.pack(side='left')
        self.folder_actions = tk.Frame(top, bg=SURFACE)
        Button(self.folder_actions, 'Delete', self.delete_folder, 'danger', small=True).pack(side='right')
        Button(self.folder_actions, 'Rename', self.rename_folder, 'ghost', small=True).pack(side='right')
        self.list_count = label(header, '', 'small', MUTED, anchor='w')
        self.list_count.pack(fill='x', pady=(2, 12))
        self.search_field = Field(header, self.search, placeholder='Search accounts')
        self.search_field.pack(fill='x')
        self.search.trace_add('write', lambda *_: self.refresh())
        Button(header, '+  New account', self.add_account, 'primary').pack(fill='x', pady=(10, 0))
        tk.Frame(self.list_pane, bg=BORDER, height=1).pack(fill='x')
        self.list_area = ScrollArea(self.list_pane)
        self.list_area.pack(fill='both', expand=True)

    # rendering

    def refresh(self):
        if self.folder is not ALL and self.folder not in self.store.folders:
            self.folder = ALL
        self._render_sidebar()
        self._render_list()
        self._render_detail()

    def _render_sidebar(self):
        for child in self.folder_area.winfo_children():
            child.destroy()
        total = sum(len(v) for v in self.store.folders.values())
        self._sidebar_row('All accounts', total, ALL)

        heading = tk.Frame(self.folder_area, bg=SIDEBAR, padx=18)
        heading.pack(fill='x', pady=(18, 6))
        label(heading, 'FOLDERS', 'caption', SIDEBAR_MUTED).pack(side='left')
        add = label(heading, '+', 'h2', SIDEBAR_MUTED, cursor='hand2')
        add.pack(side='right')
        add.bind('<Button-1>', lambda e: self.new_folder())
        add.bind('<Enter>', lambda e: add.configure(fg=SIDEBAR_TEXT))
        add.bind('<Leave>', lambda e: add.configure(fg=SIDEBAR_MUTED))

        if not self.store.folders:
            label(self.folder_area, 'No folders yet.\nClick + to add Gmail, Yahoo…', 'small',
                  SIDEBAR_MUTED, justify='left', anchor='w', padx=18).pack(fill='x')
        for name in sorted(self.store.folders, key=str.lower):
            self._sidebar_row(name, len(self.store.folders[name]), name)

    def _sidebar_row(self, text, count, folder):
        active = folder == self.folder
        bg = SIDEBAR_ACTIVE if active else SIDEBAR
        row = tk.Frame(self.folder_area, bg=bg, cursor='hand2')
        row.pack(fill='x', padx=8, pady=1)
        tk.Frame(row, bg=ACCENT if active else bg, width=3).pack(side='left', fill='y')
        name = label(row, text, 'bold' if active else 'body', SIDEBAR_TEXT, anchor='w', padx=10, pady=7)
        name.pack(side='left', fill='x', expand=True)
        label(row, str(count), 'small', SIDEBAR_MUTED, padx=10).pack(side='right')

        def paint(color):
            for w in [row] + row.winfo_children()[1:]:
                w.configure(bg=color)
        if not active:
            bind_hover(row, lambda: paint(SIDEBAR_HOVER), lambda: paint(SIDEBAR))
        bind_all_children(row, '<Button-1>', lambda e: self.select_folder(folder))
        if folder is not ALL:
            bind_all_children(row, '<Button-3>', lambda e: self._folder_menu(e, folder))

    def _folder_menu(self, event, folder):
        self.select_folder(folder)
        menu = tk.Menu(self, tearoff=False, font=FONTS['body'])
        menu.add_command(label='Rename folder', command=self.rename_folder)
        menu.add_command(label='Delete folder', command=self.delete_folder)
        menu.tk_popup(event.x_root, event.y_root)

    def _matches(self):
        query = self.search.get().strip().lower()
        # searching always looks in every folder
        folders = (self.store.folders if self.folder is ALL or query
                   else {self.folder: self.store.folders[self.folder]})
        result = []
        for folder, entries in folders.items():
            for entry in entries:
                haystack = ' '.join([folder, entry['title'], entry.get('username', ''),
                                     entry.get('url', ''), entry.get('notes', '')]).lower()
                if query in haystack:
                    result.append((folder, entry))
        result.sort(key=lambda fe: (fe[1]['title'].lower(), fe[0].lower()))
        return result

    def _render_list(self):
        query = self.search.get().strip()
        self.list_title.configure(text='Search results' if query else
                                  'All accounts' if self.folder is ALL else self.folder)
        if self.folder is ALL or query:
            self.folder_actions.pack_forget()
        else:
            self.folder_actions.pack(side='right')

        for child in self.list_area.inner.winfo_children():
            child.destroy()
        self.rows = {}
        matches = self._matches()
        self.visible_ids = [e['id'] for _, e in matches]
        if self.selected_id not in self.visible_ids:
            self.selected_id = None
            self.reveal = False

        count = len(matches)
        self.list_count.configure(text='%d account%s%s' % (count, '' if count == 1 else 's',
                                                           ' found' if query else ''))
        if not matches:
            msg = ('No accounts match "%s"' % query if query else
                   'No accounts in this folder yet' if self.folder is not ALL else
                   'No accounts yet.\nClick "New account" to add one.')
            label(self.list_area.inner, msg, fg=MUTED, justify='center', pady=40).pack(fill='x')
            return
        for folder, entry in matches:
            self._list_row(folder, entry)

    def _list_row(self, folder, entry):
        selected = entry['id'] == self.selected_id
        bg = ACCENT_SOFT if selected else SURFACE
        row = tk.Frame(self.list_area.inner, bg=bg, padx=16, pady=10, cursor='hand2')
        row.pack(fill='x')
        avatar = Avatar(row, entry['title'], size=36)
        avatar.pack(side='left')
        text = tk.Frame(row, bg=bg)
        text.pack(side='left', fill='x', expand=True, padx=(12, 0))
        label(text, entry['title'], 'bold', anchor='w').pack(fill='x')
        sub = entry.get('username') or entry.get('url') or 'No username'
        if self.folder is ALL or self.search.get().strip():
            sub = '%s  ·  %s' % (folder, sub)
        label(text, sub, 'small', MUTED, anchor='w').pack(fill='x')
        self.rows[entry['id']] = row

        def paint(color):
            row.configure(bg=color)
            text.configure(bg=color)
            avatar.set_bg(color)
            for w in text.winfo_children():
                w.configure(bg=color)

        def state_color():
            return ACCENT_SOFT if entry['id'] == self.selected_id else SURFACE

        bind_hover(row, lambda: entry['id'] != self.selected_id and paint(HOVER),
                   lambda: paint(state_color()))
        row.paint = paint
        bind_all_children(row, '<Button-1>', lambda e: self.select(entry['id']))
        bind_all_children(row, '<Double-Button-1>', lambda e: self.copy_password())

    def _render_detail(self):
        for child in self.detail.winfo_children():
            child.destroy()
        if self.selected_id is None:
            self._empty_detail()
            return
        folder, entry = self.store.find(self.selected_id)

        page = tk.Frame(self.detail, bg=BG, padx=32, pady=28)
        page.pack(fill='both', expand=True)
        header = tk.Frame(page, bg=BG)
        header.pack(fill='x')
        Avatar(header, entry['title'], size=56, font='h1').pack(side='left', anchor='n')
        Button(header, 'Delete', self.delete_account, 'danger').pack(side='right', anchor='n')
        Button(header, 'Edit', self.edit_account).pack(side='right', anchor='n', padx=(16, 8))
        titles = tk.Frame(header, bg=BG)
        titles.pack(side='left', fill='x', expand=True, padx=(16, 0))
        title = label(titles, entry['title'], 'h1', anchor='w', justify='left')
        title.pack(fill='x')
        titles.bind('<Configure>', lambda e: title.configure(wraplength=max(e.width, 100)))
        chip = label(titles, folder, 'smallbold', ACCENT, bg=ACCENT_SOFT, padx=8, pady=2, cursor='hand2')
        chip.pack(anchor='w', pady=(4, 0))
        chip.bind('<Button-1>', lambda e: self.select_folder(folder))

        card = tk.Frame(page, bg=SURFACE, highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=BORDER)
        card.pack(fill='x', pady=(24, 0))
        self._detail_row(card, 'Username or email', entry.get('username') or 'Not set',
                         [('Copy', self.copy_username)] if entry.get('username') else [],
                         fg=TEXT if entry.get('username') else MUTED, first=True)
        shown = entry['password'] if self.reveal else '•' * 12
        self._detail_row(card, 'Password', shown,
                         [('Hide' if self.reveal else 'Show', self.toggle_reveal),
                          ('Copy', self.copy_password)], font='mono')
        if entry.get('url'):
            self._detail_row(card, 'Website', entry['url'],
                             [('Open', self.open_website), ('Copy', self.copy_url)],
                             fg=ACCENT, on_click=self.open_website)
        else:
            self._detail_row(card, 'Website', 'Not set', [('Add link', self.edit_account)], fg=MUTED)
        if entry.get('notes'):
            self._detail_row(card, 'Notes', entry['notes'], [], wrap=True)

        label(page, 'Tip: double-click an account or press Ctrl+C to copy its password.',
              'small', MUTED, anchor='w', justify='left', wraplength=440).pack(fill='x', pady=(16, 0))

    def _detail_row(self, card, caption, value, actions, font='body', fg=TEXT,
                    on_click=None, wrap=False, first=False):
        if not first:
            tk.Frame(card, bg=BORDER, height=1).pack(fill='x', padx=18)
        row = tk.Frame(card, bg=SURFACE, padx=18, pady=12)
        row.pack(fill='x')
        for text, command in reversed(actions):
            Button(row, text, command, 'ghost', small=True).pack(side='right', padx=(4, 0))
        left = tk.Frame(row, bg=SURFACE)
        left.pack(side='left', fill='x', expand=True)
        label(left, caption.upper(), 'caption', MUTED, anchor='w').pack(fill='x')
        value_label = label(left, value, font, fg, anchor='w', justify='left',
                            wraplength=420 if wrap else 0)
        value_label.pack(fill='x', pady=(3, 0))
        if on_click:
            value_label.configure(cursor='hand2')
            value_label.bind('<Button-1>', lambda e: on_click())

    def _empty_detail(self):
        box = tk.Frame(self.detail, bg=BG)
        box.place(relx=0.5, rely=0.45, anchor='center')
        Avatar(box, 'P', size=64, font='display', color='#c9cde0').pack()
        if not any(self.store.folders.values()):
            label(box, 'Your vault is empty', 'h2').pack(pady=(16, 4))
            label(box, 'Add your first account, like Gmail or Yahoo.', fg=MUTED).pack()
            Button(box, '+  New account', self.add_account, 'primary').pack(pady=(16, 0))
        else:
            label(box, 'Select an account', 'h2').pack(pady=(16, 4))
            label(box, 'Its username, password and website will show here.', fg=MUTED).pack()

    # selection

    def select_folder(self, folder):
        self.folder = folder
        self.refresh()

    def select(self, entry_id):
        if entry_id == self.selected_id:
            return
        previous = self.rows.get(self.selected_id)
        self.selected_id = entry_id
        self.reveal = False
        if previous is not None:
            previous.paint(SURFACE)
        row = self.rows.get(entry_id)
        if row is not None:
            row.paint(ACCENT_SOFT)
            self.list_area.see(row)
        self._render_detail()

    def select_first(self):
        if self.visible_ids:
            self.select(self.visible_ids[0])

    def move_selection(self, step):
        if not self.visible_ids:
            return
        if self.selected_id not in self.visible_ids:
            self.select(self.visible_ids[0])
            return
        i = self.visible_ids.index(self.selected_id) + step
        self.select(self.visible_ids[max(0, min(i, len(self.visible_ids) - 1))])

    def _follow(self, folder):
        """Switch to the folder an account was saved in, if it's not already visible."""
        if self.folder is not ALL and self.folder != folder.strip():
            self.folder = folder.strip()

    def current(self):
        if self.selected_id is None:
            self.app.toast('Select an account first')
            return None, None
        return self.store.find(self.selected_id)

    def _commit(self, message=None):
        try:
            self.store.save()
        except (StoreError, OSError) as e:
            self.app.toast('Could not save the vault: %s' % e, error=True)
            return False
        self.refresh()
        if message:
            self.app.toast(message)
        return True

    # folder actions

    def new_folder(self):
        def save(name):
            self.store.add_folder(name)
            self.folder = name.strip()
            self._commit('Folder "%s" created' % name.strip())
        PromptDialog(self.app, 'New folder', 'Folder name (e.g. Gmail, Yahoo, Banking)', save)

    def rename_folder(self):
        old = self.folder
        if old is ALL:
            return

        def save(name):
            if name.strip() == old:
                return
            self.store.rename_folder(old, name)
            self.folder = name.strip()
            self._commit('Folder renamed')
        PromptDialog(self.app, 'Rename folder', 'Folder name', save, initial=old)

    def delete_folder(self):
        name = self.folder
        if name is ALL:
            return
        count = len(self.store.folders[name])
        message = ('This also deletes the %d account%s inside it. This can\'t be undone.'
                   % (count, '' if count == 1 else 's') if count else 'The folder is empty.')

        def confirm():
            self.store.delete_folder(name)
            self.folder = ALL
            self._commit('Folder "%s" deleted' % name)
        ConfirmDialog(self.app, 'Delete folder "%s"?' % name, message, 'Delete folder', confirm)

    # account actions

    def add_account(self):
        def save(folder, fields):
            entry = self.store.add_entry(folder, **fields)
            self.selected_id = entry['id']
            self._follow(folder)
            if not self._commit('Saved "%s" in %s' % (entry['title'], folder)):
                self.store.delete_entry(entry['id'])
        folder = '' if self.folder is ALL else self.folder
        if not folder and self.selected_id:
            folder = self.store.find(self.selected_id)[0]
        AccountDialog(self.app, self.store.folders, save, folder=folder)

    def edit_account(self):
        folder, entry = self.current()
        if not entry:
            return

        def save(new_folder, fields):
            self.store.update_entry(entry['id'], new_folder, **fields)
            self._follow(new_folder)
            self._commit('Updated "%s"' % entry['title'])
        AccountDialog(self.app, self.store.folders, save, folder=folder, entry=dict(entry))

    def delete_account(self):
        folder, entry = self.current()
        if not entry:
            return

        def confirm():
            self.store.delete_entry(entry['id'])
            self.selected_id = None
            self._commit('Deleted "%s"' % entry['title'])
        ConfirmDialog(self.app, 'Delete "%s"?' % entry['title'],
                      'It will be removed from %s. This can\'t be undone.' % folder,
                      'Delete account', confirm)

    def toggle_reveal(self):
        self.reveal = not self.reveal
        self._render_detail()

    def copy_password(self):
        folder, entry = self.current()
        if entry:
            self.app.copy_secret(entry['password'], 'Password copied')

    def copy_username(self):
        folder, entry = self.current()
        if entry and entry.get('username'):
            self.app.copy_secret(entry['username'], 'Username copied', clear=False)

    def copy_url(self):
        folder, entry = self.current()
        if entry and entry.get('url'):
            self.app.copy_secret(entry['url'], 'Link copied', clear=False)

    def open_website(self):
        folder, entry = self.current()
        if not entry or not entry.get('url'):
            return
        url = entry['url']
        if '://' not in url:
            url = 'https://' + url
        webbrowser.open(url)


class App(tk.Tk):
    def __init__(self, store=None):
        super().__init__()
        self.title('Passx')
        self.geometry('1060x660')
        self.minsize(920, 560)
        self.configure(bg=BG)
        self.store = store or Store()
        self.screen = None
        self.clip_value = None
        self.clip_job = None
        self.toast_job = None
        self.last_activity = time.monotonic()

        _circles.clear()  # images belong to a Tk interpreter; don't reuse a previous one's
        setup_fonts(self)
        self._setup_style()
        self.toast_label = tk.Label(self, bg=TOAST, fg='white', font=FONTS['body'], padx=18, pady=10)

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
        style.layout('Slim.Vertical.TScrollbar', [
            ('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
                ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
        style.configure('Slim.Vertical.TScrollbar', troughcolor=SURFACE, background='#cfd3df',
                        bordercolor=SURFACE, lightcolor='#cfd3df', darkcolor='#cfd3df',
                        gripcount=0, width=8)
        style.map('Slim.Vertical.TScrollbar', background=[('active', '#b4b9c9')])
        style.configure('Field.TCombobox', fieldbackground=SURFACE, background=SURFACE,
                        bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE,
                        arrowcolor=MUTED, foreground=TEXT, padding=(9, 7))
        style.map('Field.TCombobox', bordercolor=[('focus', ACCENT)],
                  fieldbackground=[('readonly', SURFACE)])
        self.option_add('*TCombobox*Listbox.font', FONTS['body'])
        self.option_add('*TCombobox*Listbox.selectBackground', ACCENT)

    def _show(self, screen):
        if self.screen is not None:
            self.screen.destroy()
        self.screen = screen
        screen.pack(fill='both', expand=True)

    def show_lock(self):
        self._show(LockScreen(self))

    def show_main(self):
        self.last_activity = time.monotonic()
        self._show(MainScreen(self))

    def lock(self):
        if not self.store.unlocked:
            return
        for window in self.winfo_children():
            if isinstance(window, tk.Toplevel):
                window.destroy()
        self.clear_clipboard()
        self.store.lock()
        self.show_lock()

    def toast(self, text, error=False):
        self.toast_label.configure(text=text, bg=DANGER if error else TOAST)
        self.toast_label.place(relx=0.5, rely=1.0, y=-24, anchor='s')
        self.toast_label.lift()
        if self.toast_job:
            self.after_cancel(self.toast_job)
        self.toast_job = self.after(3000, self.toast_label.place_forget)

    def copy_secret(self, value, message, clear=True):
        self.clipboard_clear()
        self.clipboard_append(value)
        if self.clip_job:
            self.after_cancel(self.clip_job)
            self.clip_job = None
        if clear:
            self.clip_value = value
            self.clip_job = self.after(CLIPBOARD_CLEAR_SECONDS * 1000, self.clear_clipboard)
            message += '  ·  paste with Ctrl+V, clears in %ds' % CLIPBOARD_CLEAR_SECONDS
        else:
            self.clip_value = None
        self.toast(message)

    def clear_clipboard(self):
        self.clip_job = None
        if self.clip_value is None:
            return
        try:
            # don't wipe something the user copied in the meantime
            if self.clipboard_get() == self.clip_value:
                self.clipboard_clear()
                self.clipboard_append('')
                if self.store.unlocked:
                    self.toast('Clipboard cleared')
        except tk.TclError:
            pass
        self.clip_value = None

    def _touch(self, _event=None):
        self.last_activity = time.monotonic()

    def _check_idle(self):
        if self.store.unlocked and time.monotonic() - self.last_activity > AUTO_LOCK_SECONDS:
            self.lock()
        self.after(15000, self._check_idle)

    def quit_app(self):
        self.clear_clipboard()
        self.store.lock()
        self.destroy()


def main():
    App().mainloop()


if __name__ == '__main__':
    main()
