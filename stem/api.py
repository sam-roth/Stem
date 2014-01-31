

from .control import keybinding, BufferController
from .control.buffer_set import BufferSetController
from .control.interactive import interactive, menu, submenu
from .core import Keys
from .core.tag import autoextend, autoconnect



def bind(key, interactive_command_name):
    keybinding.controller.add_binding(key, interactive_command_name)

def unbind(key):
    keybinding.controller.remove_binding(key)

# Strengthen refs to imported plugins so they aren't GCed.
_pkg_refs = []

def load_plugins(path, prefix):
    import logging
    import pkgutil
    import importlib

    def errh(name):
        logging.exception('error loading %r', name)
    for finder, name, is_pkg in pkgutil.walk_packages(path, prefix, errh):
        logging.info('loading plugin %r', name)
        _pkg_refs.append(importlib.import_module(name))


__all__ = '''
    bind
    unbind
    interactive
    menu
    submenu
    Keys
    autoextend
    autoconnect
    load_plugins
'''.split()


