
import logging
import re

import pathlib

from .                          import syntax
from .cua_interaction           import CUAInteractionMode
from ..                         import util
from ..buffers                  import Cursor, BufferManipulator, Buffer, Span, Region
from ..core                     import AttributedString, errors, Signal, write_atomically
from ..core.tag                 import Tagged, autoconnect
from ..core.attributed_string   import lower_bound
from ..core.key                 import *


class Controller(Tagged):
    def __init__(self, view, buff):
        '''
        :type view: codeedit.qt.view.TextView
        :type buff: codeedit.buffers.Buffer
        '''
        super().__init__()

        self.view               = view
        self.buffer             = buff
        self.view.lines         = self.buffer.lines
        self.view.keep          = self
        self.manipulator        = BufferManipulator(buff)
        self.canonical_cursor   = Cursor(self.manipulator)
        self.anchor_cursor      = None

        self.interaction_mode   = CUAInteractionMode(self)

        self.view.scrolled                  += self._on_view_scrolled
        self.manipulator.executed_change    += self.user_changed_buffer
        self.view.completion_done           += self.completion_done
        buff.text_modified                  += self.buffer_was_changed


        self._prev_region = Region()

    @property
    def history(self):
        return self.manipulator.history
    
    def clear(self):
        '''
        Remove all text from `self.buffer`.

        Requires an active history transaction.
        '''
        start = Cursor(self.buffer)
        end = Cursor(self.buffer).move(*self.buffer.end_pos)
        start.remove_to(end)

    def append_from_path(self, path):
        '''
        Append the contents of `self.buffer` with the contents of the file
        located at `path` decoded using UTF-8.

        Requires an active history transaction.
        '''
        with path.open('rb') as f:
            Cursor(self.buffer).move(*self.buffer.end_pos).insert(f.read().decode())

    def replace_from_path(self, path):
        '''
        Replace the contents of `self.buffer` with the contents of the
        file located at `path` decoded using UTF-8. 

        Requires an active history transaction.
        '''

        self.clear()
        self.append_from_path(path)
        self.add_tags(path=path)
        self.canonical_cursor.move(0,0)

        self.loaded_from_path(path)

    def write_to_path(self, path):
        '''
        Atomically write the contents of `self.buffer` to the file located
        at `path` encoded with UTF-8.
        '''
        
        self.will_write_to_path(path)
        with write_atomically(path) as f:
            f.write(self.buffer.text.encode())
        self.wrote_to_path(path)
    
    
    @Signal
    def will_write_to_path(self, path):
        pass

    @Signal
    def wrote_to_path(self, path):
        pass

    @Signal
    def loaded_from_path(self, path):
        pass


    @Signal
    def user_changed_buffer(self, change):
        pass

    @Signal
    def buffer_was_changed(self, change):
        pass

    @Signal
    def buffer_needs_highlight(self):
        pass

    @Signal
    def completion_requested(self):
        pass

    @Signal
    def completion_done(self, index):
        pass

    @Signal
    def user_requested_help(self):
        pass

    def _on_view_scrolled(self, start_line):
        self.view.start_line = start_line

    def refresh_view(self, full=False):
        self.view.lines = self.buffer.lines

        
        self.buffer_needs_highlight()

        curs = self.canonical_cursor
        if curs is not None:
            curs_line = curs.line
            self.view.cursor_pos = curs.pos

        anchor = self.anchor_cursor
        
        # draw selection
        if anchor is not None:
            selected_region = Span(curs, anchor)
        else:
            selected_region = Region()

        previous_region = self._prev_region

        # areas in the currently selected region not in the previously
        # selected region
        added_region    = selected_region - previous_region

        # areas in the previously selected region not in the currently selected
        # region
        removed_region  = previous_region - selected_region
        
        removed_region.set_attributes(bgcolor=None)
        added_region.set_attributes(bgcolor='#666')


        self._prev_region = selected_region

        
        if full:
            self.view.full_redraw()
        else:
            self.view.partial_redraw()




