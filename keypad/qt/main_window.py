
from keypad.abstract.application import AbstractWindow, app, AbstractApplication
from keypad.abstract import ui

from keypad.core.errors import UserError
from keypad.core.responder import Responder
from keypad.core.nconfig import Config, Settings, Field

from ..core.notification_queue import in_main_thread
from ..control import interactive

from .qt_util import *
from .options import QtGuiSettings

import traceback
import logging

class CommandLineViewSettings(Settings):
    _ns_ = 'cmdline.view'

    opacity = Field(float, 0.9, 
                    docs='view opacity (0-1)')
    animation_duration_ms = Field(int, 100, 
                                  docs='popup animation duration (ms)')
    view_height = Field(int, 70, 
                        docs='view height (px)')

    max_view_height = Field(int, 300,
                            docs='height of view when expanded (px)')


def change_listener():
    print(list(app().next_responders))

@interactive.interactive('monitor')
def monitor(app: AbstractApplication):
    app.responder_chain_changed.connect(change_listener)

class CommandLineWidget(Responder, QWidget):
    def __init__(self, parent, config, prev_responder):
        super().__init__()
        self.__parent = parent
        self.setWindowFlags(Qt.Popup)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.prev_responder = prev_responder

        self.__settings = CommandLineViewSettings.from_config(config)

        from ..control import BufferController
        from ..control.command_line_interaction import CommandLineInteractionMode
        from ..control.command_line_interpreter import CommandLineInterpreter
        from ..control.cmdline_completer import CmdlineCompleter

        from ..buffers import Buffer

        if QtGuiSettings.from_config(config).use_experimental_text_view:
            from .textview import TextViewProxy
            self.__proxy = TextViewProxy()
            self.__view = self.__proxy.peer
        else:
            from .textlayout.widget import CodeView, CodeViewProxy
            self.__view = CodeView(self)
            self.__proxy = CodeViewProxy(self.__view)
        self.__proxy.modelines_visible = False

        self.__controller = BufferController(buffer_set=None, 
                                             view=self.__proxy,
                                             buff=Buffer(), 
                                             provide_interaction_mode=False,
                                             config=config)


        self.__imode = CommandLineInteractionMode(self.__controller)
        self.__controller.interaction_mode = self.__imode
        self.__completer = CmdlineCompleter(self.__controller)
        self.__interpreter = CommandLineInterpreter()
        
        self.add_next_responders(self.__completer, self.__controller)
        self.__completer.add_next_responders(self.prev_responder)


        # forward cancelled/accepted signals
        self.cancelled = self.__imode.cancelled
        self.accepted = self.__imode.accepted

        self.__imode.accepted.connect(self.__run_command)
        self.__imode.text_written.connect(self.__on_text_written)

        layout.addWidget(self.__view)
        self.setFocusProxy(self.__view)

        self.__view.installEventFilter(self)

        # prevent flickering when first showing view
        self.setWindowOpacity(0)
        self.__view.disable_partial_update = True


        
    def __on_text_written(self):
        if not self.isVisible():
            self.show()
        self.expand()

    def __run_command(self):
        self.hide()
        try:
            self.__interpreter.exec(app(), self.__imode.current_cmdline)
        except BaseException as exc:
            interactive.run('show_error', exc)

    def set_cmdline(self, text):
        self.__imode.current_cmdline = text

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.MouseButtonRelease:
            self.expand()

        return super().eventFilter(obj, ev)

    def __calculate_bottom_left(self):
        bleft = self.__parent.statusBar().mapToGlobal(self.__parent
                                                          .statusBar()
                                                          .rect()
                                                          .topLeft())

        ay = -7
        ax = 0
        bleft.setX(bleft.x() + ax)
        bleft.setY(bleft.y() + ay)

        return bleft

    def expand(self):
        geom = self.geometry()
        geom.setWidth(self.__parent.width())
        geom.setHeight(self.__settings.max_view_height)
        geom.moveBottomLeft(self.__calculate_bottom_left())
        self.setGeometry(geom)

    def showEvent(self, event):
        geom = self.geometry()
        geom.setWidth(self.__parent.width())
        geom.setHeight(self.__settings.view_height)
        geom.moveBottomLeft(self.__calculate_bottom_left())
        self.setGeometry(geom)        

        event.accept()
        self.anim = anim = QPropertyAnimation(self, 'windowOpacity')
        anim.setDuration(self.__settings.animation_duration_ms)
        anim.setStartValue(0.0)
        anim.setEndValue(self.__settings.opacity)
        anim.setEasingCurve(QEasingCurve.InOutQuart)
        anim.start()
        self.__controller.refresh_view(full=True)

    def hideEvent(self, event):
        event.accept()
        self.setWindowOpacity(0)

import weakref

def testref(p):
    def callback():
        val = p()
        logging.debug('testref: %r', val)
    return callback

class MainWindow(AutoresponderMixin, AbstractWindow, QMainWindow, metaclass=ABCWithQtMeta):
    def __init__(self, config):
        super().__init__()
        self.__cmdline = CommandLineWidget(self, config, self)
        self.__cmdline.cancelled.connect(self.deactivate_cmdline)
        

        self.statusBar()
        self.setUnifiedTitleAndToolBarOnMac(True)

        self.__mdi = QMdiArea(self)
        self.setCentralWidget(self.__mdi)
        self.__mdi.setDocumentMode(True)
        self.__mdi.setViewMode(QMdiArea.TabbedView)
        self.__mdi.subWindowActivated.connect(self.__on_sub_window_activated)
        self.__mdi.setTabsMovable(True)

        self._command_for_action = {}
        self._item_for_action = {}
        self._menus = []
        self.rebuild_menus()

        self.setStyleSheet('''
                           QStatusBar
                           {
                               font-size: 12pt;
                           }
                           ''')

        interactive.root_menu.changed.connect(self.rebuild_menus)

    @property
    def active_editor(self):
        asw = self.__mdi.activeSubWindow()
        if asw is not None:
            return asw.widget()
        else:
            return None


    @property
    def editors(self):
        for win in self.__mdi.subWindowList():
            yield win.widget()

    def closeEvent(self, event):
        for editor in self.editors:
            if not app().close(editor):
                event.ignore()
                break
        else:
            event.accept()
            self.deleteLater()

    def next_tab(self):
        self.__mdi.activateNextSubWindow()

    def prev_tab(self):
        self.__mdi.activatePreviousSubWindow()

    def activate_cmdline(self):
        self.__cmdline.show()
        self.__cmdline.setFocus()

    def deactivate_cmdline(self):
        self.__cmdline.hide()

    def set_cmdline(self, text):
        self.activate_cmdline()
        self.__cmdline.set_cmdline(text)


    def __kill_editor(self, editor):
        for sw in self.__mdi.subWindowList():
            if sw.widget() is editor:
                sw.close()
                return

    def add_editor(self, editor):
        '''
        Add an editor to this window.
        '''

        sw = self.__mdi.addSubWindow(editor)
        editor.destroyed.connect(sw.close)
        editor.show()
        editor.window_should_kill_editor.connect(self.__kill_editor)
        editor.is_modified_changed.connect(self.__child_modified_changed, add_sender=True)
        editor.saved.connect(self.__child_saved, add_sender=True)

    def __child_saved(self, sender):
        self.setWindowFilePath(None)
        self.__update_window_path()

    def event(self, evt):
        return super().event(evt)


    def __child_modified_changed(self, sender):
        self.__update_window_path()

    def __update_window_path(self):
        asw = self.__mdi.activeSubWindow()

        if asw is None:
            self.clear_next_responders()
            self.editor_activated(None)
            return


        editor = asw.widget()

        self.setWindowModified(editor.is_modified)
        if editor.path is not None:
            self.setWindowFilePath(str(editor.path.absolute()))
            self.setWindowTitle(editor.path.name + ' [*]')
            asw.setWindowTitle(editor.path.name)
        else:
            self.setWindowFilePath(None)
            self.setWindowTitle('Untitled [*]')
            asw.setWindowTitle('Untitled')

        self.editor_activated(editor)

    def __on_sub_window_activated(self, win):
        self.__update_window_path()
        asw = self.__mdi.activeSubWindow()

    def rebuild_menus(self):
        logging.debug('rebuilding menus')

        for menu in self._menus:
            self.menuBar().removeAction(menu.menuAction())
        self._item_for_action.clear()
        self._command_for_action.clear()
        self._menus.clear()

#         self._menus_by_hier.clear()

        from ..control import interactive
        
        def create_menu(qt_menu, ce_menu, depth=0):
            if depth == 1:
                self._menus.append(qt_menu)
                
            for name, item in ce_menu:
                if isinstance(item, interactive.MenuItem):
                    action = qt_menu.addAction(name)
                    if item.keybinding is not None:
                        action.setShortcut(to_q_key_sequence(item.keybinding))
                    self._item_for_action[action] = item
                    action.triggered.connect(self._on_action_triggered)
                else:
                    submenu = qt_menu.addMenu(name)
                    create_menu(submenu, item, depth+1)
            
        create_menu(self.menuBar(), interactive.root_menu)
    
    def _on_action_triggered(self):
        from ..control import interactive
        item = self._item_for_action[self.sender()]

        try:
            interactive.dispatcher.dispatch(app(), item.interactive_name, *item.interactive_args)
        except Exception as exc:
            interactive.dispatcher.dispatch(self, 'show_error', exc)


    def close(self):
        QMainWindow.close(self)

@interactive.interactive('set_cmdline')
def set_cmdline(win: MainWindow, *text):
    win.set_cmdline(' '.join(text))

@interactive.interactive('show_error')
def show_error(win: MainWindow, msg):
    sb = win.statusBar()
    app().beep()
    sb.showMessage(str(msg) + ' [' + type(msg).__name__ + ']', 2500)

    if isinstance(msg, BaseException):
        tb = ''.join(traceback.format_exception(type(msg),
                                                msg,
                                                msg.__traceback__))
        if isinstance(msg, UserError):
            logging.debug('User error passed to show_error:\n%s', tb)
        else:
            logging.error('Exception passed to show_error:\n%s', tb)

@interactive.interactive('activate_cmdline')
def activate_cmdline(win: MainWindow):
    @in_main_thread
    def update():
        win.activate_cmdline()
    update()



@interactive.interactive('about')
def about(win: MainWindow):
    from . import about
    about.AboutDialog(win).show()

interactive.menu(0, 'Help/About', 'about')


