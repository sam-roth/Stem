
from .color import Color
from ..util import clamp
import random

class Colorscheme(object):
    
    fg = Color.from_hex('#000')
    bg = Color.from_hex('#FFF')
    
    lexical_categories = {}

    fallback_sat = 0.5
    fallback_val = 128

    def lexical_category_attrs(self, lexcat):
        if lexcat not in self.lexical_categories:
            print('will generate missing', lexcat)
            self.lexical_categories[lexcat] = dict(
                color=Color.from_hsv(random.random(), self.fallback_sat, self.fallback_val))

        return self.lexical_categories[lexcat]

    def emphasize(self, color, steps):
        
        color = Color.from_hex(color)
        h,s,v = color.hsv
        if v >= 127:
            v -= 25 * steps
        else:
            v += 25 * steps
        
        
        v = clamp(0, 256, v)
        
        return Color.from_hsv(h, s, v, color.alpha)

    @property
    def cursor_color(self):
        return self.fg


class AbstractSolarized(Colorscheme):
    _base03     = Color.from_hex('#002b36')
    _base02     = Color.from_hex('#073642')
    _base01     = Color.from_hex('#586e75')
    _base00     = Color.from_hex('#657b83')
    _base0      = Color.from_hex('#839496')
    _base1      = Color.from_hex('#93a1a1')
    _base2      = Color.from_hex('#eee8d5')
    _base3      = Color.from_hex('#fdf6e3')
    _yellow     = Color.from_hex('#b58900')
    _orange     = Color.from_hex('#cb4b16')
    _red        = Color.from_hex('#dc322f')
    _magenta    = Color.from_hex('#d33682')
    _violet     = Color.from_hex('#6c71c4')
    _blue       = Color.from_hex('#268bd2')
    _cyan       = Color.from_hex('#2aa198')
    _green      = Color.from_hex('#859900')


    fallback_sat = _blue.hsv[1]
    
    def __init__(self):
        super().__init__()
        self.lexical_categories.update(
            preprocessor=dict(color=self._orange),
            keyword=dict(color=self._green),
            function=dict(color=self._blue),
            literal=dict(color=self._cyan),
            escape=dict(color=self._red),
            todo=dict(color=self._magenta),
            docstring=dict(color=self._violet)
        )


class SolarizedDark(AbstractSolarized):
    
    fg = AbstractSolarized._base0
    bg = AbstractSolarized._base03

    fallback_val = fg.hsv[2]

    def __init__(self):
        super().__init__()
        self.lexical_categories.update(
            comment=dict(color=self._base01),
        )
