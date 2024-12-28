# -*- coding: windows-1252 -*-
COPYRIGHT = '''Copyright (C)2024, by maxpat78'''

__version__ = '0.40b'

# Compression levels
Z_NO_COMPRESSION = 0
Z_BEST_SPEED = 1
Z_BEST_COMPRESSION = 9
Z_DEFAULT_COMPRESSION = -1

# Compression strategies
Z_DEFAULT_STRATEGY = 0
Z_HUFFMAN_ONLY = 2
Z_RLE = 3
Z_FIXED = 4

from .deflate import compress
from .inflate import decompress
from .crc32 import crc32
