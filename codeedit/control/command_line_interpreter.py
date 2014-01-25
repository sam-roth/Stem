


from . import interactive

import shlex

class CommandLineInterpreter(object):

    @staticmethod
    def _lex(cmdline):
        lexer = shlex.shlex(cmdline)
        lexer.whitespace_split = True
        return list(lexer)

    def exec(self, first_responder, cmdline):
        tokens = self._lex(cmdline)
        interactive.dispatcher.dispatch(first_responder, *tokens)
        #interactive.dispatcher.dispatch(first_responder, cmdline.strip())
    


