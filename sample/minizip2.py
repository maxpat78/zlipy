# -*- coding: windows-1252 -*-

# Test compression with MiniZipWriter
from zlipy.minizip import MiniZipWriter
import glob

out = open('BINS_EXE.zip','wb')
zip = MiniZipWriter(out)
for fn in glob.glob('C:/Bin/*.exe'):
    zip.append(fn, open(fn,'rb').read())
    print(f'Added {fn} {zip.entries[-1][2]}/{zip.entries[-1][3]} ({100.0*zip.entries[-1][2]/zip.entries[-1][3]:.2f}%)')
zip.write()
zip.close()
print('END.')
