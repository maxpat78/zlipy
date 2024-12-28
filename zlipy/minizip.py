# -*- coding: windows-1252 -*-
from zlipy.deflate import compress
from zlipy.inflate import decompress
from zlipy.crc32 import crc32

import struct, zlib

class compressobj:
    def __init__ (p, level=9, method=8, wbits=-15):
        p.wbits = wbits
        
    def compress(p, s):
        return compress(s, wbits=p.wbits)

    def flush(p):
        return b''

if 0:
    class MiniZipWriter():
        "Comprime un singolo file in un archivio ZIP"
        def __init__ (p, stream):
            # Output stream to ZIP archive
            p.fp = stream
            # Starts zlib "raw" Deflate compressor
            #~ p.compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
            p.compressor = compressobj(9, 8, -15)
            p.crc = 0
            p.method = 8 # 0=Stored, 8=Deflated
            
        def append(p, entry, s):
            # Adds a file name
            p.entry = bytes(entry, 'utf8')
            cs = p.compressor.compress(s) + p.compressor.flush()
            p.crc = crc32(s) & 0xFFFFFFFF
            p.usize, p.csize = len(s), len(cs)
            p.blob = cs

        def write(p):
            p.fp.write(p.PK0304())
            p.fp.write(p.blob)
            cdir = p.PK0102()
            cdirpos = p.fp.tell()
            p.fp.write(cdir)
            p.fp.write(p.PK0506(len(cdir), cdirpos))
            p.fp.flush()

        def close(p):
            p.fp.close()

        def rewind(p):
            p.fp.seek(0, 0)
            
        def PK0304(p):
            return b'PK\x03\x04' + struct.pack('<5H3I2H', 0x14, 0, p.method, 0, 33, p.crc, p.csize, p.usize, len(p.entry), 0) + p.entry

        def PK0102(p):
            return b'PK\x01\x02' + struct.pack('<6H3I5H2I', 0x14, 0x14, 0, p.method, 0, 33, p.crc, p.csize, p.usize, len(p.entry), 0, 0, 0, 0, 0x20, 0) + p.entry

        def PK0506(p, cdirsize, offs):
            if hasattr(p, 'zipcomment'):
                p.zipcomment = bytes(p.zipcomment, 'utf8')
                return b'PK\x05\x06' + struct.pack('<4H2IH', 0, 0, 1, 1, cdirsize, offs, len(p.zipcomment)) + p.zipcomment
            else:
                return b'PK\x05\x06' + struct.pack('<4H2IH', 0, 0, 1, 1, cdirsize, offs, 0)

class MiniZipWriter():
    "Crea un archivio ZIP"
    def __init__(p, stream, usezlib=False):
        p.usezlib = usezlib
        p.fp = stream
        p.entries = []  # Lista dei metadati per la directory centrale
        p.cdirsize = 0  # Dimensione della directory centrale cumulativa
        p.offset = 0    # Posizione corrente nell'output stream

    def append(p, entry, data):
        entry = bytes(entry, 'utf-8')
        if p.usezlib:
            compressor = zlib.compressobj(9, 8, -15)
        else:
            compressor = compressobj(9, 8, -15)
        compressed = compressor.compress(data) + compressor.flush()
        if p.usezlib:
            crc = zlib.crc32(data) & 0xFFFFFFFF
        else:
            crc = crc32(data) & 0xFFFFFFFF
        usize, csize = len(data), len(compressed)
        
        # Scrive l'header locale e i dati compressi
        p.fp.write(b'PK\x03\x04' + struct.pack('<5H3I2H', 0x14, 0, 8, 0, 33, crc, csize, usize, len(entry), 0) + entry)
        p.fp.write(compressed)
        
        # Registra le informazioni per la directory centrale
        p.entries.append((entry, crc, csize, usize, p.offset))
        p.offset = p.fp.tell()

    def write(p):
        cdir_start = p.fp.tell()
        
        # Scrive la directory centrale
        for entry, crc, csize, usize, offset in p.entries:
            cdir_entry = b'PK\x01\x02' + struct.pack(
                '<6H3I5H2I', 0x14, 0x14, 0, 8, 0, 33, crc, csize, usize,
                len(entry), 0, 0, 0, 0, 0x20, offset
            ) + entry
            p.fp.write(cdir_entry)
            p.cdirsize += len(cdir_entry)
        
        # Scrive l'header di chiusura
        cdir_end = p.fp.tell()
        p.fp.write(b'PK\x05\x06' + struct.pack(
            '<4H2IH', 0, 0, len(p.entries), len(p.entries), p.cdirsize, cdir_start, 0
        ))
        p.fp.flush()

    def close(p):
        p.fp.close()

if 1:
    class MiniZipReader():
        "Espande un singolo file da un archivio ZIP creato da MiniZipWriter"
        def __init__ (p, stream):
            p.fp = stream
            p.parse()
            cs = p.blob
            if p.method == 0:
                p.s = cs
            else:
                p.s = decompress(cs)
            crc = crc32(p.s) & 0xFFFFFFFF
            if crc != p.crc:
                raise Exception("BAD CRC-32")
                
        def get(p):
            return p.s
            
        def close(p):
            p.fp.close()

        def rewind(p):
            p.fp.seek(0, 0)
            
        def parse(p):
            p.rewind()
            if p.fp.read(4) != b'PK\x03\x04':
                raise Exception("BAD LOCAL HEADER")
            ver1, flag, method, dtime, ddate, crc, csize, usize, namelen, xhlen = struct.unpack('<5H3I2H', p.fp.read(26))
            #~ print (ver1, flag, method, hex(dtime), hex(ddate), hex(crc32), csize, usize, namelen, xhlen)
            if method not in (0, 8):
                raise Exception("COMPRESSION METHOD NOT SUPPORTED")
            if xhlen != 0:
                raise Exception("TOO MANY EXT HEADERS")
            p.entry = p.fp.read(namelen)
            p.blob = p.fp.read(csize)
            p.usize = usize
            p.crc = crc
            p.method = method
else:
    class MiniZipReader():
        "Legge un archivio ZIP"
        def __init__(p, stream):
            p.fp = stream
            p.entries = []
            p.parse_central_directory()
        
        def parse_central_directory(p):
            p.fp.seek(-22, 2)  # Posiziona alla fine dell'archivio per leggere l'header PK\x05\x06
            if p.fp.read(4) != b'PK\x05\x06':
                raise Exception("BAD END OF CENTRAL DIRECTORY")
            _, _, total_entries, _, cdir_size, cdir_offset, _ = struct.unpack('<4H2IH', p.fp.read(18))
            
            # Vai all'inizio della directory centrale
            p.fp.seek(cdir_offset)
            for _ in range(total_entries):
                if p.fp.read(4) != b'PK\x01\x02':
                    raise Exception("BAD CENTRAL DIRECTORY HEADER")
                p.fp.seek(24, 1)  # Salta campi intermedi
                crc, csize, usize, namelen, xhlen, fclen, _, _, _, offset = struct.unpack('<3I2H5HI', p.fp.read(30))
                entry_name = p.fp.read(namelen)
                p.fp.seek(xhlen + fclen, 1)
                p.entries.append((entry_name, crc, csize, usize, offset))
        
        def get(p, entry_name):
            for entry, crc, csize, usize, offset in p.entries:
                if entry == bytes(entry_name, 'utf-8'):
                    p.fp.seek(offset)
                    if p.fp.read(4) != b'PK\x03\x04':
                        raise Exception("BAD LOCAL HEADER")
                    p.fp.seek(26, 1)  # Salta campi intermedi
                    blob = p.fp.read(csize)
                    
                    # Decomprime se necessario
                    if csize == usize:
                        data = blob
                    else:
                        data = decompress(blob)
                    
                    # Verifica CRC
                    if crc32(data) & 0xFFFFFFFF != crc:
                        raise Exception("BAD CRC-32")
                    return data
            raise Exception("FILE NOT FOUND")
        
        def list_files(p):
            return [entry.decode('utf-8') for entry, _, _, _, _ in p.entries]
        
        def close(p):
            p.fp.close()



if __name__ == '__main__':  
    out = open('a.zip','wb')
    zip = MiniZipWriter(out)
    zip.append('cProfile_test2.log', open('cProfile_test2.log','rb').read())
    zip.write()
    zip.close()

    out = open('a.zip','rb')
    zip = MiniZipReader(out)
    print(zip.get())
