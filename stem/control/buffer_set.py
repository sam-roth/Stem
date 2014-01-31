
from ..core import errors

import types
from ..buffers import Buffer
from ..qt.buffer_set import BufferSetView
from ..core.responder import Responder, responds
from ..core import commands
from . import behavior
from .command_line_interaction import CommandLineInteractionMode
from .command_line_interpreter import CommandLineInterpreter
from ..abstract.application import app

from .interactive import interactive

import sys
import logging

class Tracer(object):
    def __init__(self):
        self.f = open('/tmp/stem-dump.txt', 'w')

    def __call__(self, frame, event, arg):
        self.f.write('%s, %r:%d\n' % (event, frame.f_code.co_filename, frame.f_lineno))
        self.f.flush()

    def set(self):
        sys.settrace(self)

class BufferSetController(Responder):
    def __init__(self, view):
        super().__init__()

        self._buffer_controllers = set()
        self._active_buffer_controller = None
        self._last_active_buffer_controller = None
        self._command_line_interpreter = CommandLineInterpreter()
        

        self.view = view
        app().next_responder = self.view
        view.next_responder = self

        self.view.active_view_changed.connect(self._after_active_view_change)


        from .buffer_controller import BufferController
        self._command_line_controller = BufferController(
            self,
            self.view.command_line_view, 
            Buffer(),
            provide_interaction_mode=False
        )

        cl_imode = self._command_line_controller.interaction_mode = \
                CommandLineInteractionMode(self._command_line_controller)
        cl_imode.accepted.connect(self._after_cmdline_accepted)
        cl_imode.cancelled.connect(self.__after_cmdline_cancelled)

        self._command_line_controller.add_tags(cmdline=True)

        self.view.will_close.connect(self._before_view_close)
        
    def __after_cmdline_cancelled(self):
        if self._last_active_buffer_controller is not None:
            self.view.active_view = self._last_active_buffer_controller.view


    def _before_view_close(self, event):
        
        try:
            paths = [c.path for c in self._buffer_controllers if c.is_modified]
            if paths:
                non_none_paths = [p for p in paths if p is not None]
                result = self.view.show_save_all_prompt(non_none_paths, len(paths)-len(non_none_paths))
                if result == 'save-all':
                    for bc in self._buffer_controllers:
                        raise NotImplementedError()
                elif result == 'discard-all':
                    for bc in self._buffer_controllers:
                        if bc.is_modified:
                            bc.is_modified = False
                            bc.remove_tags(['path'])
                            bc.view.close()
                else:
                    event.intercept()

        except Exception as exc:
            self.view.show_internal_failure_msg()
            event.intercept()


    def _after_active_view_change(self, view):
        if view is not None and view.controller is not None:
            self._last_active_buffer_controller = self._active_buffer_controller

            self.view.next_responder = view.controller
            view.controller.add_next_responders(self)

            self._active_buffer_controller = view.controller
            self._after_buffer_modified_changed()
            self.view.path = view.controller.path

        else:
            self.view.next_responder = self

    def _after_buffer_modified_changed(self, val=None):
        if self._active_buffer_controller:
            self.view.modified = self._active_buffer_controller.is_modified
        else:
            self.view.modified = False

    def _after_cmdline_accepted(self):

        text = self._command_line_controller.interaction_mode.current_cmdline

        
        if self._last_active_buffer_controller is not None:
            self.view.active_view = self._last_active_buffer_controller.view


        self._command_line_interpreter.exec(self.view, text)

    @responds(commands.set_trace)
    def set_trace(self):
        Tracer().set()
        logging.warning('Tracer set')
        
    
    @responds(commands.activate_cmdline)
    def activate_cmdline(self):
        self.view.active_view = self._command_line_controller.view
        
    @responds(commands.new_cmd)
    def open(self, path=None):
        bcontr = self.find(path) if path is not None else None
        if bcontr is None:
            from . import buffer_controller
            view = self.view.add_buffer_view()
            bcontr = buffer_controller.BufferController(self, view, Buffer())
            bcontr.modified_was_changed.connect(self._after_buffer_modified_changed)

            if path is not None:
                with bcontr.history.ignoring():
                    bcontr.replace_from_path(path)

            self._after_active_view_change(view)

        else:
            self.view.active_view = bcontr.view

        self.add_buffer_controller(bcontr)
        return bcontr



    def close_buffer(self, controller=None):
        controller = self.required_active_buffer_controller(controller)
        if controller.is_modified:
            raise errors.BufferModifiedError('Buffer is modified. To discard, use :destroy.')
        else:
            self.remove_buffer_controller(controller)

    def gui_close_buffer(self, controller=None):
        controller = self.required_active_buffer_controller(controller)
        if controller.is_modified:
            answer = self.view.show_save_prompt(controller.path)
            
            if answer == 'save':
                from . import buffer_controller
                buffer_controller.gui_save(controller)
                self.close_buffer(controller)
            elif answer == 'discard':
                controller.is_modified = False
                self.close_buffer(controller)
            # otherwise, do nothing.


        else:
            self.close_buffer(controller)



    @responds(commands.set_tag)
    def set_tag(self):
        tag_str = self.view.show_input_dialog('Set tags (DEBUGGING ONLY!!!). Use Python kwargs-style expression.')
        if tag_str:
            tags = eval('dict({})'.format(tag_str))
            self._active_buffer_controller.add_tags(**tags)

    
    @responds(commands.open_cmd)
    def run_open_dialog(self):
        path = self.view.run_open_dialog()
        if path:
            return self.open(path)
        else:
            return None

    

    def run_save_dialog(self, initial):
        return self.view.run_save_dialog(initial)
            

    def find(self, path):
        for c in self._buffer_controllers:
            if c.path == path:
                return c

    def add_buffer_controller(self, buffer_controller):
        self._buffer_controllers.add(buffer_controller)
        buffer_controller.buffer_set = self

    def remove_buffer_controller(self, buffer_controller):
        self.view.close_subview(buffer_controller.view)
        self._buffer_controllers.remove(buffer_controller)
        buffer_controller.buffer_set = None


    @property
    def buffer_controllers(self): return frozenset(self._buffer_controllers)
    
    @property
    def active_buffer_controller(self):
        return self._active_buffer_controller

    def required_active_buffer_controller(self, override=None):
        '''
        :rtype: stem.control.buffer_controller.BufferController
        '''
        controller = override or self._active_buffer_controller
        if not controller or controller is self._command_line_controller:
            raise errors.NoBufferActiveError('No buffer active.')
        return controller


@interactive('new')
def new(bufs: BufferSetController):
    bufs.open()

@interactive('gui_edit', 'gedit', 'ged')
def gui_edit(bufs: BufferSetController):
    bufs.run_open_dialog()
import ast, pathlib

@interactive('edit', 'e')
def edit(bufs: BufferSetController, path):
    if path.startswith('"') or path.startswith("'"):
        path = ast.literal_eval(path)        

    path = pathlib.Path(path)
    bufs.open(path)

@interactive('quit', 'q')
def quit_buffer(bufs: BufferSetController):
    bufs.close_buffer()

@interactive('gui_quit', 'gquit', 'gq')
def gui_quit_buffer(bufs: BufferSetController):
    bufs.gui_close_buffer()

@interactive('destroy')
def destroy_buffer(bufs: BufferSetController):
    bc = bufs.active_buffer_controller
    if bc is None:
        raise errors.NoBufferActiveError('No buffer active.')
    bc.is_modified = False
    bufs.close_buffer(bc)

@interactive('activate_cmdline')
def activate_cmdline(bufs: BufferSetController):
    bufs.activate_cmdline()

@interactive('next_tab')
def next_tab(bufs: BufferSetController, n_tabs=1):
    if isinstance(n_tabs, str):
        n_tabs = ast.literal_eval(n_tabs)
    bufs.view.next_tab(n_tabs)

def main():

    import logging
    from PyQt4 import Qt
    import sys

    logging.basicConfig(level=logging.DEBUG)
    app = Qt.QApplication(sys.argv)


    
    c = BufferSetController(BufferSetView())
    c.view.raise_()
    c.view.show()

    app.exec_()

if __name__ == '__main__':
    main()