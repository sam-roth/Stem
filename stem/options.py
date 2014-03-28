import os
import os.path
import pathlib
import platform

from .core import colorscheme
from .core.nconfig import ConfigGroup, Field


OnPosixSystem       = os.name == 'posix'
OnOSX               = platform.system() == 'Darwin'
OnWindows           = platform.system() == 'Windows'

UserConfigHome      = pathlib.Path(os.path.expanduser('~/.stem'))
DefaultColorScheme  = colorscheme.SolarizedDark()
DefaultDriverMod    = 'stem.qt.driver'



DefaultOtherFont                = 'Monospace', 11
DefaultOSXFont                  = 'Menlo', 12
DefaultWinFont                  = 'Consolas', 10

if OnOSX:
    TextViewFont                = DefaultOSXFont
elif OnWindows:
    TextViewFont                = DefaultWinFont
else:
    TextViewFont                = DefaultOtherFont

# You may wish to set this to False if spacing looks strange.
TextViewIntegerMetrics          = True

# Double striking text may improve legibility under FreeType
# when using light-on-dark color schemes. Generally, it makes
# the text look "bolder" without changing its metrics.
# This option is superfluous on Mac OS X, as CoreText 
# performs appropriate gamma adjustment automatically; however, it should
# work if you wish to use it.
TextViewDoubleStrike            = False

# CursorBlinkRate_Hz controls the number of blink cycles per second. CursorDutyCycle 
# controls the fraction of time each period during which the cursor should be visible.
# CursorDutyCycle is 0.8 by default to make it easier to find the cursor. There's a distinct lack of
# research on this topic, and my intuition might be wrong about it, so YMMV, but I did find this:
# https://twitter.com/ID_AA_Carmack/status/266267089596198912 .
CursorBlinkRate_Hz  = 1
CursorDutyCycle     = 0.8




class TextViewSettings(ConfigGroup):
    integer_metrics = Field(bool, True)
    double_strike = Field(bool, False)
    
    cursor_blink_rate = Field(float, 1)
    cursor_duty_cycle = Field(float, 0.8)
    
    tab_stop = Field(int, 4)
    expand_tabs = Field(bool, True)
    
    driver_mod = Field(str, 'stem.qt.driver')
    colorscheme = Field(str, 'stem.core.colorscheme.SolarizedDark')
    user_config_home = Field(pathlib.Path, pathlib.Path(os.path.expanduser('~/.stem')))
    
    
    