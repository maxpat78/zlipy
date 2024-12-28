# -*- coding: windows-1252 -*-
import sys
from lz_tester import stats, check
from zlipy.minizip import MiniZipReader, MiniZipWriter
from zlipy.infldbg import decompress

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

import sqlite3, datetime
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
