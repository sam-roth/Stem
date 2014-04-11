
import sys
import contextlib
import math

from collections                import namedtuple

from PyQt4.Qt                   import *

from .qt_util                   import *
from .text_rendering            import *
from .completion_view           import CompletionView
from ..core                     import signal, attributed_string
from ..core.key                 import SimpleKeySequence
from ..                         import options

import time


import logging
import itertools



class BasicTextView(QAbstractScrollArea):
    class CursorType:
        Bar = 0
        Rect = 1
        FillRect = 2

    class MouseButtons:
        Left = Qt.LeftButton
        Right = Qt.RightButton
        Middle = Qt.MiddleButton

    def __init__(self, parent=None):
        try:
            super().__init__(parent)
            self.setFrameStyle(QFrame.NoFrame)
            self._config = None
            self._completion_view = None
            self.setAttribute(Qt.WA_OpaquePaintEvent, True)
            self.viewport().setAttribute(Qt.WA_OpaquePaintEvent, True)

            self.settings = TextViewSettings(options.DefaultColorScheme)
            self.setFont(self.settings.q_font)

            self._lines = []
            self._margins = QMargins(4, 4, 4, 4)

            self._plane_size = None
            self.update_plane_size()

            self._img_cache = None

            self.cursor_pos = None

            self.start_line = 0
            self._partial_redraw_ok = False
            self._prevent_partial_redraw = False
            self._last_cursor_line = None
            self.modelines = []

            mouse_cursor = self.cursor()
            mouse_cursor.setShape(Qt.IBeamCursor)
            self.setCursor(mouse_cursor)

            self.disable_partial_update = False
            self.controller = None        
            self.overlay_spans = {}

            
            self._cursor_blink_on_timer = QTimer()
#             self._cursor_blink_on_timer.setInterval((1.0-options.CursorDutyCycle)/options.CursorBlinkRate_Hz * 1000)

            self._cursor_blink_on_timer.setSingleShot(True)
            self._cursor_blink_on_timer.timeout.connect(self._on_cursor_blink_on)

            self._cursor_blink_off_timer = QTimer()
#             self._cursor_blink_off_timer.setInterval(options.CursorDutyCycle/options.CursorBlinkRate_Hz * 1000)
            self._cursor_blink_off_timer.setSingleShot(True)
            self._cursor_blink_off_timer.timeout.connect(self._on_cursor_blink_off)

            self.__set_cursor_blink_rate(options.CursorBlinkRate_Hz, options.CursorDutyCycle)
            
            
            self._cursor_blink = False
            self._cursor_blink_on_timer.start()

            self._cursor_type = self.CursorType.Bar
            

        except:
            logging.exception('error initting TextView')
            raise
            
    def __set_cursor_blink_rate(self, rate, duty_cycle):
        self._cursor_blink_on_timer.setInterval((1.0-duty_cycle)/rate * 1000)
        self._cursor_blink_off_timer.setInterval(duty_cycle/rate * 1000)
        
            
    def run_modified_warning(self, modified):
        self.setFocus(Qt.OtherFocusReason)
        mb = QMessageBox(self)
        mb.setIcon(QMessageBox.Warning)
        mb.setText('This buffer has been modified externally since it was loaded.')
        mb.setInformativeText('Saving the buffer will OVERWRITE the modifications.')
        
        mb.setWindowFlags(mb.windowFlags() | Qt.Sheet)
        mb.setWindowModality(Qt.WindowModal)
        
        reload_text = 'Reload, Discarding Unsaved Changes' if modified else 'Reload'
        reload_role = QMessageBox.DestructiveRole if modified else QMessageBox.YesRole
        reload_btn = mb.addButton(reload_text, reload_role)
        
        cancel_btn = mb.addButton(QMessageBox.Cancel)
        
        if not modified:
            mb.setDefaultButton(reload_btn)
        
        mb.exec()
        
        if mb.clickedButton() is reload_btn:
            return 'reload'
        else:
            return 'cancel'
            
    def _on_settings_reloaded(self):
        for line in self._lines:
            line.invalidate()
        self.full_redraw()
        settings = options.GeneralSettings.from_config(self.config)
        self.__set_cursor_blink_rate(settings.cursor_blink_rate, settings.cursor_duty_cycle)
        
    @property
    def config(self):
        return self._config
        
    @config.setter
    def config(self, val):
        self._config = val
        self.settings = TextViewSettings(options.DefaultColorScheme, val)
        self.settings.reloaded.connect(self._on_settings_reloaded)
        self._on_settings_reloaded()
        


    @property
    def cursor_type(self): 
        return self._cursor_type
    
    @cursor_type.setter
    def cursor_type(self, value): 
        self._cursor_type = value
        self.partial_redraw()

    def _on_cursor_blink_on(self):
        self._cursor_blink = True
        self.partial_redraw()
        if self.hasFocus():
            self._cursor_blink_off_timer.start()

    def _on_cursor_blink_off(self):
        self._cursor_blink = False
        self.partial_redraw()
        self._cursor_blink_on_timer.start()


    def focusInEvent(self, event):
        self.full_redraw()
        self._cursor_blink_off_timer.start()

    @signal.Signal
    def will_close(self, event):
        pass

    @signal.Signal
    def closing(self):
        pass

    def closeEvent(self, event):
        ce = CloseEvent()
        self.will_close(ce)
        if ce.is_intercepted:
            event.ignore()
            return
        else:
            self.closing()

    @property
    def completion_view(self):
        '''
        Get the completion view for this TextView, creating one if it doesn't
        already exist.
        '''
        
        if self._completion_view is None:
            self._completion_view = CompletionView(parent=self, settings=self.settings)
            self._completion_view.key_press += self.key_press


        return self._completion_view



    @property
    def completion_doc_lines(self):
        if self._completion_view is not None:
            return self._completion_view.doc_lines
        else:
            return []

    @completion_doc_lines.setter
    def completion_doc_lines(self, val):
        if self._completion_view is not None:
            self._completion_view.doc_lines = val


    @property
    def completion_doc_plane_size(self):
        if self._completion_view is not None:
            return self._completion_view.doc_plane_size
        else:
            return 1,1




    @property
    def completions(self):
        return self.completion_view.model.completions

    
    @completions.setter
    def completions(self, val):
        self.completion_view.model.completions = val

    def show_completions(self):
        x,y = self.map_from_plane(*self.cursor_pos)
        
        normal_compl_rect = QRect(self.mapToGlobal(QPoint(x, y + self.line_height)), 
                                  self.completion_view.size())
        intersect = QApplication.desktop().screenGeometry().intersected(normal_compl_rect)
        if intersect != normal_compl_rect:
            normal_compl_rect.moveBottomLeft(
                self.mapToGlobal(
                    QPoint(x, y - self.line_height)))
        
            
        self.completion_view.move_(normal_compl_rect.topLeft())
        self.completion_view.show()




    def beep(self):
        qApp.beep()
    
    
    @property
    def buffer_lines_visible(self):
        h, w = self.plane_size
        return h - len(self.modelines)

    @property
    def tab_width(self): return self.settings.tab_stop

    @signal.Signal
    def plane_size_changed(self, width, height): pass

    @signal.Signal
    def scrolled(self, start_line): pass


    def scroll_to_line(self, line):
        self.verticalScrollBar().setValue(line)

    @property
    def lines(self): return self._lines

    @property
    def plane_size(self): 
        h, w = self._plane_size
        return int(h), int(w)

    @lines.setter
    def lines(self, lines):
        self._lines = lines
        self.update_plane_size()

    def update_plane_size(self):
        metrics = QFontMetricsF(self.settings.q_font)
        
        m = self._margins
        size = self.size()
        size.setWidth(size.width() - m.left() - m.right())
        size.setHeight(size.height() - m.top() - m.bottom())
        

        self.char_width = metrics.width('m')
        self.line_height = math.ceil(metrics.lineSpacing())


        width_chars   = size.width() / self.char_width
        height_chars  = size.height() / self.line_height
        
        new_plane_size = (height_chars, width_chars)
        if new_plane_size != self._plane_size:
            self._plane_size = new_plane_size
            self.verticalScrollBar().setPageStep(height_chars)
            self.plane_size_changed(width_chars, height_chars)
            

    def map_to_plane(self, x, y):
        line = int(math.floor((y - self._margins.top()) / self.line_height)) + self.start_line
        raw_col = int(math.floor((x-self._margins.left()) / self.char_width))

        cumulative_raw_cols = 0
        
        try:
            col = 0
            for col, ch in enumerate(self.lines[line].text):
                if cumulative_raw_cols >= raw_col:
                    break

                if ch == '\t':
                    cumulative_raw_cols = int(math.ceil((cumulative_raw_cols+1)/self.tab_width)) * self.tab_width
                else:
                    cumulative_raw_cols += 1
            else:
                col += 1
        except IndexError:
            return line, raw_col
        else:
            return line, col

    def map_from_plane(self, line, col):
        
        y = self._margins.top() + (line - self.start_line) * self.line_height
        fm = QFontMetricsF(self.settings.q_font)
        
        expanded_text = self.settings.expand_tabs(self.lines[line].text[:col])
        
        x = self._margins.left() + fm.width(expanded_text)

        return x, y

        
    @signal.Signal
    def mouse_down_char(self, line, col): pass

    @signal.Signal
    def mouse_move_char(self, buttons, line, col): pass

    @signal.Signal
    def key_press(self, event: KeyEvent): pass

    @signal.Signal
    def should_override_app_shortcut(self, event: KeyEvent): pass



    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_plane_size()

    def _viewport_paint(self, event):
        painter = QPainter(self.viewport())
        with ending(painter):
            area_size = self.viewport().size()
            self.verticalScrollBar().setPageStep(self.plane_size[0])
            self.verticalScrollBar().setRange(0, len(self.lines))

            if self.disable_partial_update or not self._partial_redraw_ok:
                painter.setCompositionMode(QPainter.CompositionMode_Source)
                painter.fillRect(self.rect(), self.settings.q_bgcolor)
        self._paint_to(self.viewport())

    def viewportEvent(self, event):
        if event.type() == QEvent.KeyPress:
            print(event)
        if event.type() == QEvent.Paint:
            assert isinstance(event, QPaintEvent)
            self._viewport_paint(event)
            return True
        elif event.type() == QEvent.MouseButtonPress:
            line, col = self.map_to_plane(event.x(), event.y())
            self.mouse_down_char(line, col)
            return True
        elif event.type() == QEvent.MouseMove:
            line, col = self.map_to_plane(event.x(), event.y())
            self.mouse_move_char(event.buttons(), line, col)
            return True

        else:
            return super().viewportEvent(event)

    def event(self, event):
        if event.type() == QEvent.KeyPress:
            self.keyPressEvent(event)
            return True
        elif event.type() == QEvent.ShortcutOverride:
            ce_evt = marshal_key_event(event)
            self.should_override_app_shortcut(ce_evt)
            if ce_evt.is_intercepted:
                event.accept()
                return True
            else:
                return super().event(event)
        else:
            return super().event(event)

    def keyPressEvent(self, event):
        event.accept()
        self.key_press(marshal_key_event(event))
    
    def scrollContentsBy(self, dx, dy):
        self.scrolled(self.verticalScrollBar().value())

    def _paint_to(self, device):
        painter = QPainter(device)
        with ending(painter):
            painter.setFont(self.font())
        
            
            should_draw_cursor = (
                self._cursor_blink
                and (self.hasFocus()
                     or (self.completion_view and self.completion_view.hasFocus()))
            )


            if self._prevent_partial_redraw or self.disable_partial_update:
                self._partial_redraw_ok = False
                self._prevent_partial_redraw = False

            cursor_color = to_q_color(self.settings.scheme.cursor_color)
            painter.setPen(cursor_color)
            painter.setBrush(cursor_color)

            x = self._margins.left()

            fm = QFontMetricsF(self.settings.q_font)
            y = self._margins.top()

            viewport_width = self.viewport().width()

            height = self.line_height 

            
            if self.cursor_pos is not None:
                cursor_line, cursor_col = self.cursor_pos
            else:
                cursor_line, cursor_col = None, None

            lines_drawn = 0
            lines_updated = 0

            plane_height, plane_width = self.plane_size

            text_lines = self.lines[self.start_line:self.start_line + plane_height - len(self.modelines)] 
            lines_to_display = text_lines + self.modelines

            text_lines_end = 0
            modeline_start = 0

            # merge the iterable of lists into a single list
            overlay_spans = list(itertools.chain.from_iterable(self.overlay_spans.values()))
            
            for i, row in enumerate(lines_to_display, self.start_line):

                overlays = set()                
                if i < len(text_lines) + self.start_line:
                    for overlay_span, attr_key, attr_val in overlay_spans:
                        start_pos, end_pos = overlay_span.start_curs.pos, overlay_span.end_curs.pos
    
                        start_y, start_x = start_pos
                        end_y, end_x = end_pos
                        
                        if start_y <= i <= end_y:
                            line_start_x = 0 if i != start_y else start_x
                            line_end_x = len(row) if i != end_y else end_x
                            
                            overlays.add((line_start_x, line_end_x, attr_key, attr_val))
    
                    if i == cursor_line and should_draw_cursor:
                        if self._cursor_type == self.CursorType.Rect:
                            overlays.add((cursor_col, cursor_col+1, 'cartouche', self.settings.fgcolor))
                        elif self._cursor_type == self.CursorType.FillRect:
                            # FIXME: this should overwrite the selection overlay.
                            overlays.add((cursor_col, cursor_col+1, 'bgcolor', self.settings.fgcolor))
                            overlays.add((cursor_col, cursor_col+1, 'color', self.settings.bgcolor))
                elif i == len(text_lines) + self.start_line:
                    text_lines_end = y
                    modeline_start = y = self.height() - height * len(self.modelines) - self._margins.bottom()

                drew_line, renewed_cache = draw_attr_text(
                    painter, 
                    QRect(QPoint(x, y), QSize(viewport_width, height)),
                    row, 
                    self.settings,
                    partial=(self._partial_redraw_ok and i != self._last_cursor_line),
                    overlay=overlays)
                if drew_line: lines_drawn += 1
                if renewed_cache: lines_updated += 1

                if i == cursor_line and should_draw_cursor and self._cursor_type == self.CursorType.Bar:
                    cursor_x = fm.width(self.settings.expand_tabs(row.text[:cursor_col])) + x
                    painter.fillRect(
                        QRectF(QPointF(cursor_x, y),
                               QSizeF(2, height)),
                        painter.pen().color()
                    )
                    #painter.drawLine(cursor_x, y + 1, cursor_x, y + height - 2)

                y += int(height)
                if y >= self.height():
                    break

            
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(
                QRect(
                    QPoint(x, text_lines_end), 
                    QSize(self.width() - x, modeline_start - text_lines_end)
                ), 
                self.settings.q_bgcolor
            )

            self._partial_redraw_ok = False
            self._last_cursor_line = cursor_line
            

    def partial_redraw(self):
        self._partial_redraw_ok = True
        self.viewport().update()

    def full_redraw(self):
        self._prevent_partial_redraw = True
        self.viewport().update()



def make_test_attr_str():
    astr = attributed_string.AttributedString('Hello, world!$')
    
    astr.set_attribute(0, 4, 'color', '#FAA')
    astr.set_attribute(7, 12, 'color', '#AAF')
    astr.set_attribute(12, 13, 'color', '#FFA')

    astr.set_attribute(13, 14, 'bgcolor', '#FFF')
    astr.set_attribute(13, 14, 'color', '#000')


    astr.insert(13, '!!')
    
    return astr
    

def main():

    app = QApplication(sys.argv)

    win = QWidget()
    win.setAttribute(Qt.WA_TranslucentBackground)
    layout = QVBoxLayout(win)
    layout.setContentsMargins(0, 0, 0, 0)
    win.setLayout(layout)

    tv = TextView(win)
    for _ in range(100):
        tv.lines.append(make_test_attr_str())
    layout.addWidget(tv)

    
    @tv.plane_size_changed.connect
    def on_plane_size_change(width, height):
        pass

    win.show()
    win.resize(640, 480)
    win.raise_()

    
    app.exec_()

