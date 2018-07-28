"""Find/replace widget."""

# TODO: full words only option
# FIXME: finding 'as' or 'asa' from 'asasasasa' is broken

import re
import sys
import tkinter as tk
from tkinter import ttk
import weakref

from porcupine import actions, get_tab_manager, images, tabs, utils


# keys are tabs, values are Finder widgets
finders = weakref.WeakKeyDictionary()


class Finder(ttk.Frame):
    """A widget for finding and replacing text.

    Use the pack geometry manager with this widget.
    """

    def __init__(self, parent, textwidget, **kwargs):
        super().__init__(parent, **kwargs)

        self.grid_columnconfigure(1, weight=1)
        self._textwidget = textwidget

        entrygrid = ttk.Frame(self)
        entrygrid.grid(row=0, column=0)

        self.find_entry = self._add_entry(entrygrid, 0, "Find:")
        find_var = self.find_entry['textvariable'] = tk.StringVar()
        find_var.trace('w', self.highlight_all_matches)
        self.find_entry.lol = find_var     # because cpython gc

        self.find_entry.bind('<Shift-Return>', self._go_to_previous_match)
        self.find_entry.bind('<Return>', self._go_to_next_match)

        self._replace_entry = self._add_entry(entrygrid, 1, "Replace with:")

        buttonframe = ttk.Frame(self)
        buttonframe.grid(row=1, column=0, sticky='we')

        self._replace_this_button = ttk.Button(
            buttonframe, text="Replace this match",
            command=self._replace_this_match, state='disabled')

        pack_kwargs = {'side': 'left', 'fill': 'x', 'expand': True}
        ttk.Button(buttonframe, text="Previous match",
                   command=self._go_to_previous_match).pack(**pack_kwargs)
        ttk.Button(buttonframe, text="Next match",
                   command=self._go_to_next_match).pack(**pack_kwargs)
        self._replace_this_button.pack(**pack_kwargs)

        self.statuslabel = ttk.Label(self)
        self.statuslabel.grid(row=1, column=1, columnspan=2, sticky='nswe')

        closebutton = ttk.Label(self, cursor='hand2')
        closebutton.grid(row=0, column=2, sticky='ne')
        closebutton.bind('<Button-1>', self.hide)

        # TODO: figure out why images don't work in tests
        if 'pytest' not in sys.modules:     # pragma: no cover
            closebutton['image'] = images.get('closebutton')

        # TODO: use the pygments theme somehow?
        textwidget.tag_config('find_highlight',
                              foreground='black', background='yellow')

    def _add_entry(self, frame, row, text):
        ttk.Label(frame, text=text).grid(row=row, column=0)
        entry = ttk.Entry(frame, width=35, font='TkFixedFont')
        entry.bind('<Escape>', self.hide)
        entry.grid(row=row, column=1, sticky='we')
        return entry

    def show(self):
        self.pack(fill='x')
        self.find_entry.focus_set()
        self.highlight_all_matches()

    def hide(self, junk_event=None):
        # remove previous highlights from highlight_all_matches
        self._textwidget.tag_remove('find_highlight', '1.0', 'end')

        self.pack_forget()
        self._textwidget.focus_set()

    # tag_ranges returns (start1, end1, start2, end2, ...), and this thing
    # gives a list of (start, end) pairs
    def _get_match_ranges(self):
        starts_and_ends = list(
            map(str, self._textwidget.tag_ranges('find_highlight')))
        assert len(starts_and_ends) % 2 == 0
        pairs = list(zip(starts_and_ends[0::2], starts_and_ends[1::2]))
        return pairs

    # must be called when replacing becomes possible or impossible, i.e. when
    # find_highlight areas or the selection changes
    def _update_replace_button(self):
        try:
            start, end = map(str, self._textwidget.tag_ranges('sel'))
        except ValueError:
            self._replace_this_button['state'] = 'disabled'
            return

        if (start, end) in self._get_match_ranges():
            self._replace_this_button['state'] = 'enabled'
        else:
            self._replace_this_button['state'] = 'disabled'

    def highlight_all_matches(self, *junk):
        # clear previous highlights
        self._textwidget.tag_remove('find_highlight', '1.0', 'end')

        looking4 = self.find_entry.get()
        if not looking4:        # don't search for empty string
            self.statuslabel['text'] = ""
            return

        count = 0
        start_index = '1.0'

        while True:
            # searching at the beginning of a match gives that match, not
            # the next match, so we need + 1 char... unless we are looking
            # at the beginning of the file, and to avoid infinite
            # recursion, we haven't done it before
            if start_index == '1.0' and count == 0:
                search_arg = start_index
            else:
                search_arg = '%s + 1 char' % start_index

            start_index = self._textwidget.search(
                looking4, search_arg, 'end')
            if not start_index:
                # no more matches
                break

            self._textwidget.tag_add(
                'find_highlight', start_index,
                '%s + %d chars' % (start_index, len(looking4)))
            count += 1

        self._update_replace_button()
        if count == 0:
            self.statuslabel['text'] = "Found no matches :("
        elif count == 1:
            self.statuslabel['text'] = "Found 1 match."
        else:
            self.statuslabel['text'] = "Found %d matches." % count

    def _select_range(self, start, end):
        self._textwidget.tag_lower('find_highlight', 'sel')  # make sure sel shows
        self._textwidget.tag_remove('sel', '1.0', 'end')
        self._textwidget.tag_add('sel', start, end)
        self._textwidget.mark_set('insert', start)
        self._textwidget.see(start)

    def _go_to_next_match(self, junk_event=None):
        pairs = self._get_match_ranges()
        if not pairs:
            self.statuslabel['text'] = "No matches found!"
            return

        # find first pair that starts after the cursor
        for start, end in pairs:
            if self._textwidget.compare(start, '>', 'insert'):
                self._select_range(start, end)
                break
        else:
            # reached end of file, use the first match
            self._select_range(*pairs[0])

        self.statuslabel['text'] = ""
        self._update_replace_button()

    # see _go_to_next_match for comments
    def _go_to_previous_match(self, junk_event=None):
        pairs = self._get_match_ranges()
        if not pairs:
            self.statuslabel['text'] = "No matches found!"
            return

        for start, end in reversed(pairs):
            if self._textwidget.compare(start, '<', 'insert'):
                self._select_range(start, end)
                break
        else:
            self._select_range(*pairs[-1])

        self.statuslabel['text'] = ""
        self._update_replace_button()
        return

    def _replace_this_match(self):
        try:
            start, end = map(str, self._textwidget.tag_ranges('sel'))
            if (start, end) not in self._get_match_ranges():
                raise ValueError
        except ValueError:
            self.statuslabel['text'] = (
                'Click "Previous match" or "Next match" first.')
            return

        # _update_replace_button() must not be moved after .replace, think
        # about what happens when you replace 'asd' with 'asd'
        # TODO: test 'asd' --> 'asd' replace
        self._textwidget.tag_remove('find_highlight', start, end)
        self._update_replace_button()
        self._textwidget.replace(start, end, self._replace_entry.get())

        self._textwidget.mark_set('insert', start)   # TODO: test this
        self._go_to_next_match()
        if self.statuslabel['text'] == "No matches found!":
            self.statuslabel['text'] = "No more matches."   # TODO: test this


def find():
    tab = get_tab_manager().select()
    assert isinstance(tab, tabs.FileTab)
    if tab not in finders:
        finders[tab] = Finder(tab.bottom_frame, tab.textwidget)
    finders[tab].show()


def setup():
    actions.add_command("Edit/Find and Replace", find, '<Control-f>',
                        tabtypes=[tabs.FileTab])
