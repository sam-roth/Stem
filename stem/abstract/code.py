
from abc import ABCMeta, abstractmethod
from enum import IntEnum, Enum
        
from stem.buffers.cursor import Cursor
from stem.options import GeneralConfig

class AbstractCompletionResults(metaclass=ABCMeta):

    def __init__(self, token_start):
        '''
        token_start - the (line, col) position at which the token being completed starts
        '''
        self.token_start = token_start

    @abstractmethod
    def doc_async(self, index):
        '''
        Return a Future for the documentation for a given completion result as a list of 
        AttributedString.        
        '''

    @property
    @abstractmethod
    def rows(self):
        '''
        Return a list of tuples of AttributedString containing the contents of 
        each column for each row in the completion results.
        '''

    @abstractmethod
    def text(self, index):
        '''
        Return the text that should be inserted for the given completion.
        '''

    @abstractmethod
    def filter(self, text=''):
        '''
        Filter the completion results using the given text.
        '''

    @abstractmethod
    def dispose(self):
        pass

class AbstractCallTip(metaclass=ABCMeta):    
    @abstractmethod
    def to_astring(self, arg_index=None):
        pass


class RelatedNameType(IntEnum):
    decl = 1
    defn = 2
    assign = 4
    use = 8
    
    all = decl | defn | assign | use

class RelatedName(object):

    Type = RelatedNameType
            
    def __init__(self, type_, path, pos, name):
        self.type = type_
        self.path = path
        self.pos = pos
        self.name = name
    
    
    def __repr__(self):
        return 'RelatedName{!r}'.format((
            self.type,
            self.path,
            self.pos,
            self.name
        ))
        
class DiagnosticSeverity(Enum):
    unknown = -1
    fatal = 0
    error = 1
    warning = 2
    note = 3


class Diagnostic(object):
    Severity = DiagnosticSeverity
    
    def __init__(self, severity, text, ranges):
        self.severity = severity
        self.text = text
        self.ranges = ranges
    
    def __repr__(self):
        return 'Diagnostic{!r}'.format((
            self.severity,
            self.ranges,
            self.text
        ))

class Indent:
    def __init__(self, level, align=None):
        self.level = level
        self.align = align
    def __repr__(self):
        return 'Indent{!r}'.format((self.level, self.align))
    
class AbstractCodeModel(metaclass=ABCMeta):   
    '''
    The code model represents the editor's knowledge of the semantics of the
    buffer contents.
    
    :ivar buffer:      The buffer that this code model is built from.
    :ivar path:        The path where the buffer will be saved
    :ivar conf:        The object containing configuration information for this object.
    '''
    
    RelatedNameType = RelatedNameType
    completion_triggers = ['.']
    call_tip_triggers = []
    open_braces = '([{'
    close_braces = '}])'
    
    
    def __init__(self, buff, conf):
        '''
        :type buff: stem.buffers.Buffer
        '''
        self.buffer = buff
        self.path = None
        self.conf = conf
    
    @abstractmethod
    def indent_level(self, line):
        '''
        Return the indentation level as a multiple of the tab stop for a given line.
        '''
    
    def open_brace_pos(self, pos, exclude=('literal',)):
        '''
        Return the location of the closing brace for a given location in the text.
        '''
        
        c = Cursor(self.buffer).move(pos).advance(-1)
        
        level = 1
        for ch in c.walk(-1):
            if ch in self.open_braces and dict(c.rchar_attrs).get('lexcat') not in exclude:
                level -= 1
            elif ch in self.close_braces and dict(c.rchar_attrs).get('lexcat') not in exclude:
                level += 1
            
            if level == 0:
                return c.pos
        else:
            return None
        
    def close_brace_pos(self, pos, exclude=('literal',)):
        
        c = Cursor(self.buffer).move(pos).advance(1)
        
        level = 1
        for ch in c.walk(1):
            if ch in self.close_braces and dict(c.rchar_attrs).get('lexcat') not in exclude:
                level -= 1
            elif ch in self.open_braces and dict(c.rchar_attrs).get('lexcat') not in exclude:
                level += 1
            
            if level == 0:
                return c.pos
        else:
            return None
        
            
    def alignment_column(self, pos):
        c = Cursor(self.buffer).move(pos)
        try:
            c.opening_brace()
            if c.rchar == '{':
                return None # curly braces are for blocks (maybe)
                # TODO: make this handle initializer lists correctly
            else:
                return c.x + 1
        except RuntimeError:
            return None
            
                
    def indentation(self, pos):
        c = Cursor(self.buffer).move(pos)
        for _ in c.walklines(-1):
            if c.searchline(r'^\s*$') is None:
                c.home()
                break
            
        # find the start of the statement
        try:
            while True:
                p = c.pos
                c.opening_brace()
                if c.rchar == '{':
                    c.pos = p
                    break # the indent level is determined by curly braces in many languages
        except RuntimeError: # got to the outermost level
            pass
        
        level = self.indent_level(c.y+1)
        col = self.alignment_column(pos)
        
        return Indent(level, col)
        
    @abstractmethod
    def completions_async(self, pos):
        '''
        Return a future to the completions available at the given position in the document.
        
        Raise NotImplementedError if not implemented.
        '''
    
    def find_related_async(self, pos, types):
        '''
        Find related names for the token at the given position.
        
        decl       - find declarations
        defn       - find definitions
        assign     - find assignments
        
        
        Raises NotImplementedError by default.
        
        :rtype: concurrent.futures.Future of list of RelatedName
        '''
        raise NotImplementedError

    
    @abstractmethod
    def highlight(self):
        '''
        Rehighlight the buffer.        
        
        Note: This is different than other methods in the code model in that
        it involves mutation of the buffer, and it may be better to make
        the code model a factory for a "Highlighter" object.        
        '''
        
    @abstractmethod
    def dispose(self):
        '''
        Release system resources held by the model.
        '''
        
    @property
    def can_provide_call_tips(self):
        return False
    
    def call_tip_async(self, pos):
        raise NotImplementedError
    
    @property
    def can_provide_diagnostics(self):
        return False
        
    def diagnostics_async(self):
        raise NotImplementedError

class IndentRetainingCodeModel(AbstractCodeModel):
    indent_after = r'[{:]\s*$'
    
    def highlight(self):
        pass
                
    def completions_async(self, pos):
        raise NotImplementedError
    
    def indent_level(self, line):
        c = Cursor(self.buffer).move(line, 0).up()
        
        for _ in c.walklines(-1):
            m = c.searchline(r'^\s*\S')
            if m:
                tv_settings = GeneralConfig.from_config(self.conf)
                tstop = tv_settings.tab_stop
                indent_text = tv_settings.indent_text
                
                itext = m.group(0)
                itext = itext.expandtabs(tstop)
                ilevel = len(itext) // len(indent_text.expandtabs(tstop))
                if self.indent_after is not None and c.searchline(self.indent_after):
                    ilevel += 1
                return ilevel
        else:
            return 0
    
    def dispose(self):
        pass
        
