import pathlib, sys
thisfile = pathlib.Path(__file__).absolute()
sys.path.insert(0, str(thisfile.parent.parent.parent.parent / 'third-party'))

import unittest

from .cppmodel import CXXCodeModel, CXXCompletionResults
from .config import CXXConfig
from stem.core.nconfig import Config
from stem.buffers import Buffer, Cursor, Span
from stem.abstract.code import RelatedName, Diagnostic
import pprint

import sys


cxx_config = CXXConfig.from_config(Config.root)
cxx_config.clang_library = '/Library/Developer/CommandLineTools/usr/lib/libclang.dylib'

def add_to_buffer(buff, text):
    result = []
    for part in text.split('%%'):
        buff.insert(buff.end_pos, part)
        result.append(buff.end_pos)
    result.pop()
    return result
    

class TestCXXCodeModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.buffer = Buffer()
        cls.cmodel = CXXCodeModel(cls.buffer, Config.root)
        cls.cmodel.path = '/tmp/test.cpp'
        
    @classmethod
    def tearDownClass(cls):
        cls.cmodel.dispose()
        
    def setUp(self):
        self.buffer.remove((0,0), len(self.buffer.text))

        
    def test_completion(self):
        self.buffer.insert(
            (0, 0),
            'struct S { int abcdef; };\n'
            'void foo() { S s; s.' 
        )
        ep = self.buffer.end_pos
        self.buffer.insert(ep, 
            '   }\n')
        f = self.cmodel.completions_async(ep)
        
        res = f.result()
        
        assert isinstance(res, CXXCompletionResults)
        
        
        for i, row in enumerate(res.rows):
            if 'abcdef' == res.text(i):
                break
        else:
            self.fail('Expected abcdef when completing on s')
        
        
    def test_find_decl(self):
        
        decl_pos, find_decl_pos = add_to_buffer(
            self.buffer,
            '''
            void %%foo();
            
            void foo() { }
            
            void bar()
            {
                foo%%();
            }
            '''
        )

        f = self.cmodel.find_related_async(find_decl_pos, self.cmodel.RelatedNameType.decl)
        
        res = f.result(timeout=5)
        
        assert len(res) == 1
        result = res[0]
        
        assert isinstance(result, RelatedName)
        assert result.pos == decl_pos
        

    def test_find_defn(self):
        
        defn_pos, find_defn_pos = add_to_buffer(
            self.buffer,
            '''
            void foo();
            
            void %%foo() { }
            
            void bar()
            {
                foo%%();
            }
            '''
        )
        
        
        f = self.cmodel.find_related_async(find_defn_pos, self.cmodel.RelatedNameType.defn)
        
        res = f.result(timeout=5)
        
        assert len(res) == 1
        result = res[0]
        
        assert isinstance(result, RelatedName)
        assert result.pos == defn_pos
        
        
    def test_get_diagnostics(self):
        
        missing_semicolon_pos, = add_to_buffer(
            self.buffer,
            '''
            void bar();
            
            void foo()
            {
                bar()%%
            }
            '''
        )
        
        assert self.cmodel.can_provide_diagnostics
        
        diags = self.cmodel.diagnostics_async().result()
        assert len(diags) == 1
        diag = diags[0]
        
        assert isinstance(diag, Diagnostic)
        assert len(diag.ranges) == 1
        assert diag.ranges[0][2] == missing_semicolon_pos