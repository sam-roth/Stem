
from .nconfig import Settings

class Filetype(object):
    
    _by_suffix = {}
    _default = None
    
    def __init__(self, name, suffixes=(), code_model=None, tags=None):
        self._suffixes = ()
        self.name = name
        self.code_model = code_model
        self.tags = tags or {}
        self.suffixes = suffixes
        
    @property
    def suffixes(self):
        return self._suffixes
    
    @suffixes.setter
    def suffixes(self, val):
        for suffix in self._suffixes:
            del Filetype._by_suffix[suffix]
        self._suffixes = val
        for suffix in self._suffixes:
            if suffix in Filetype._by_suffix:
                raise KeyError('Suffix {!r} is already associated with {!r}'.format(
                    suffix,
                    Filetype._by_suffix[suffix].name
                ))
            Filetype._by_suffix[suffix] = self
            
    
    def make_code_model(self, buff, config):
        if self.code_model is not None:
            return self.code_model(buff, config)
        else:
            return None
    
    
    @classmethod
    def by_suffix(cls, suffix):
        return cls._by_suffix.get(suffix, cls.default())


    @classmethod
    def default(cls):
        if cls._default is None:
            cls._default = Filetype('<default>')
        
        return cls._default

