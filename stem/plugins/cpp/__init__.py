
from stem.core import filetype
from stem.api import Filetype, Plugin, register_plugin

def make_cxx_code_model(*args):
    from .cppmodel import CXXCodeModel
    return CXXCodeModel(*args)

@register_plugin
class CPPCodeModelPlugin(Plugin):
    name = 'C/C++ Code Model'
    author = 'Sam Roth <sam.roth1@gmail.com>'

    def attach(self):
        Filetype('c++', 
                 suffixes='.c .cc .C .cpp .c++ .cxx .h .hh .H .hpp .h++ .hxx'.split(),
                 tags={'parmatch': True, 'commentchar': '//'},
                 code_model=make_cxx_code_model)
        
    def detach(self):
        pass
                        
