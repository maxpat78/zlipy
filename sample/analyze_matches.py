# -*- coding: windows-1252 -*-
import sys, sqlite3, datetime
from zlipy.minizip import MiniZipReader, MiniZipWriter
from zlipy.infldbg import decompress

#
# DEBUG tools
#
def expand(matches):
    "Espande una lista di byte e match nel buffer originale"
    out = bytearray()
    for o in matches:
        if isinstance(o, tuple):
            length, distance = o
            if length < 3 or length > 258:
                print(f'lz_expand: match length {length} is out of Deflate limits 3..258')
                return None
            if distance < 1 or distance > 32768:
                print(f'lz_expand: match distance {distance} is out of Deflate limits 1..32768')
                return None
            if length >= distance:
                s = length * out[-distance:] # ripete la sequenza (finale)
                out.extend(s[:length]) # la limita a length
            else:
                out.extend(out[-distance:-distance+length]) # copia i byte esistenti
        else:
            out.extend(o.to_bytes(1))
    return out

global_errors_count = 0

def check(matches, s):
    "Verifica che l'elenco di match si espanda nella stringa s"
    s1 = expand(matches)
    if s != s1:
        print('check: LZ matches build a different string!')
        global_errors_count += 1
        #~ print(s1)
        return 0
    return 1

def stats(matches):
    n = 0
    offsets = 0
    lengths = 0
    # colleziona i dati
    for m in matches:
        if isinstance(m, tuple):
            n += 1
            lengths += m[0]
            offsets += m[1]
    D = {'count': n, 'compressed': lengths, 'stored': len(matches)-n, 'mean_distance': offsets/(n or 1)}
    print(f"{n} matches for {lengths}/{lengths+D['stored']} bytes. Mean distance {D['mean_distance']}.")
    return D

find_matches = find_matches_hc3
#~ find_matches = find_longest_matches

""" stringhe di test
Input = b'abc' + 300*b'x' + b'abcdabcabc'
Ambedue sono rappresentazioni valide:
[97, 98, 99, 120, (258, 1), (41, 258), 97, 98, 99, 100, 97, 98, 99, 97, 98, 99]
[97, 98, 99, 120, (258, 1), (41, 258), 97, 98, 99, 100, (3, 4), (3, 7)]
Tuttavia sarebbe auspicabile la più compatta? e cioé:
[97, 98, 99, 120, (258, 1), (41, 1), (3, 303), 100, (3, 4), (3, 7)]

Input = b'abcxbcdexabcde'
find_matches_hc3 trova il primo match di 3 su 'abc'
[97, 98, 99, 120, 98, 99, 100, 101, 120, (3, 9), 100, 101]
invece è preferibile trovare il match di 4 su 'bcde', in modo "lazy"
[97, 98, 99, 120, 98, 99, 100, 101, 120, 97, (4, 6)] """

def print_matches(matches, tab):
    offset=0
    LOG = SQLogger(tab)
    for m in matches:
        if not isinstance(m, tuple):
            offset+=1
            continue
        LOG.log(offset, m[0], m[1])
        offset+=m[0]
    LOG.commit()

# select count(len) from my where len=3 and dist=1 union select count(len) from zlib where len=3 and dist=1;
# select sum(bytes) from (select len * count(len) as bytes from "a.zip" group by len);
#~ SELECT 'my' AS source, COUNT(len) AS total
#~ FROM my
#~ WHERE len > 3 AND len < 10
#~ UNION ALL
#~ SELECT 'zlib' AS source, COUNT(len) AS total
#~ FROM zlib
#~ WHERE len > 3 AND len < 10;
#~ SELECT source, COUNT(len) AS total
#~ FROM (
    #~ SELECT 'my' AS source, len FROM my
    #~ UNION ALL
    #~ SELECT 'zlib' AS source, len FROM zlib
#~ ) combined
#~ WHERE len > 3 AND len < 10
#~ GROUP BY source;

class SQLogger:
    def __init__(p, tab):
        p.table = tab
        p.con = sqlite3.connect(f"zlipy.db")
        p.con.cursor().execute(f'drop table if exists "{tab}";')
        p.con.cursor().execute(f'create table "{tab}" (offset integer, len integer, dist integer);')

    def log(p, offs, len, dist):
        p.con.cursor().execute(f'insert into "{p.table}" values ({offs}, {len}, {dist});')

    def commit(p):
        p.con.commit()

if __name__ == '__main__':
    db = sys.argv[1]
    fp = open(sys.argv[1],'rb')
    zip = MiniZipReader(fp)
    m = decompress(zip.blob, return_lz=True)
    print_matches(m, sys.argv[1])
