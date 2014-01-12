

import collections
import inspect

class ImmutableListView(collections.Sequence):
    def __init__(self, list_):
        self._list =  list_

    def __len__(self):
        return len(self._list)

    def __getitem__(self, i):
        return self._list[i]



def dump_object(obj):
    header = type(obj).__name__ + "{\n    "
     
    body = ',\n    '.join('{:<10}{!r}'.format(name + ':', value) 
                          for (name, value) in vars(obj).items()
                          if not (name.startswith('__') and name.endswith('__')))

    end = '\n}'

    return header + body + end



class FatalError(BaseException):
    pass
