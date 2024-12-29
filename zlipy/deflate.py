# -*- coding: windows-1252 -*-
from collections import defaultdict
from zlipy import bitio
from zlipy.huffman import *
from zlipy.lz import find_matches, lz_expand
from zlipy.utils import *
from zlipy import *

DEBUG=0

class DeflateException(Exception):
    pass

def rle_enc(L):
    "Comprime le lunghezze ripetute nelle tabelle Literals/Lengths e Distances"
    i=0
    EL = []
    def is_rl(L, i):
        rlen = 1
        zero = L[i]==0
        while i < len(L)-1 and L[i] == L[i+1]:
            i += 1
            rlen += 1
            if not zero and rlen == 7: break # max 3-6 del precedente
            if zero and rlen == 138: break # max 138 di zero
        #~ print('dbg:', zero, i, rlen)
        # valgono sequenze di 3+ zeri o ripetizioni di 4+ simboli
        if (zero and rlen < 3) or (not zero and rlen < 4):
            return (0, L[i])
        return (rlen, L[i]) # (ripetizioni, simbolo)
    while i < len(L):
        rlen, S = is_rl(L, i)
        i+=1
        if not rlen:
            EL.append(S) # scrive il simbolo
            continue
        #~ print(f'found {rlen} of {L[i-1]} at {i-1}', L[i-1:i-1+rlen])
        if S: # non zero
            EL.append(S) # scrive il simbolo
            EL.append((16, rlen-4)) # 16 -> copia 3-6 volte il precedente, in base ai 2 bit successivi
        elif rlen > 10:
            EL.append((18, rlen-11)) # 18 -> ripete zero 11-138 volte, in base ai 7 bit successivi
        else:
            EL.append((17, rlen-3)) # 17 -> ripete zero 3-10 volte, in base ai 3 bit successivi
        i+=(rlen-1)
    if DEBUG: assert rle_dec(EL) == L
    return EL

def gen_dynamic_trees(matches, b, freq_lit=None, freq_dist=None):
    """Genera dinamicamente gli alberi mainTree (Literals/Lengths) e disTree (Distances) e li
    salva su disco compressi con uno speciale metodo RLE e con Huffman, dopo aver generato
    un terzo albero (preTree)"""
    # Se non sono state calcolate le frequenze nel passo LZ...
    if not freq_lit:
        # Crea un dizionario per ogni possibile simbolo degli alberi di Literals/Lengths e Distances
        # con frequenza iniziale zero
        freq_lit = defaultdict(int)
        freq_dist = defaultdict(int)
        freq_lit[256] = 1 # il simbolo End Of Stream compare 1 volta a fine blocco
        # Conteggia le rispettive frequenze
        for m in matches:
            if isinstance(m, tuple): # match
                freq_lit[deflate_length_symbol[m[0]-3]] += 1
                freq_dist[len_to_base(m[1],1)] += 1
            else: # byte
                freq_lit[m] += 1
        if DEBUG: print(freq_lit)
        if DEBUG: print(freq_dist)
    # Crea i due alberi in forma canonica dalle frequenze
    mainTree = Tree.from_freqs(freq_lit, 288)
    distTree = Tree.from_freqs(freq_dist, 32)
    # Ricava le liste delle lunghezze in bit di ciascun albero (esclusi zero in coda)
    lit_lens = mainTree.short_lengths()
    if any(e > 32767 for e in mainTree.lengths):
        raise DeflateException('Main tree with lengths >15 bit')
    dist_lens = distTree.short_lengths()
    if DEBUG: print ("Main tree lengths:", len(lit_lens), lit_lens)
    if DEBUG: print ("Dist tree lengths:", len(dist_lens), dist_lens)
    # Scrive quante lunghezze costituiscono gli alberi Literals/Lengths e Distances
    b.write(len(lit_lens)-257, 5) # scrive solo il n. di lunghezze di match effettivamente in uso
    b.write(len(dist_lens)-1, 5)
    # Le concatena e comprime con uno speciale metodo RLE
    rle = rle_enc(lit_lens+dist_lens)
    if DEBUG: print(len(lit_lens+dist_lens), len(rle))
    if DEBUG: print(lit_lens+dist_lens)
    if DEBUG: print('rle encoded', len(rle), rle)
    # Crea l'albero Huffman per comprimere il flusso RLE
    freq_pre = defaultdict(int)
    for f in rle:
        if isinstance(f, tuple):
            freq_pre[f[0]] += 1
        else:
            freq_pre[f] += 1
    preTree = Tree.from_freqs(freq_pre, 19, 7)
    if DEBUG: print(freq_pre)
    if DEBUG: print(preTree.lengths)
    if any(e > 7 for e in preTree.lengths):
        raise DeflateException('Pre tree with lengths >3 bit')
    # Calcola quante lunghezze sono in uso
    flen = len(deflate_code_length_order)
    for i in range(flen-1,-1,-1):
        if not preTree.lengths[deflate_code_length_order[i]]:
            flen -=1
            continue
        break
    if DEBUG: print ("count", len(lit_lens), len(dist_lens), flen)
    # Scrive il n. di codici (max 19) per decomprimere i 2 alberi
    b.write(flen-4, 4)
    # Scrive le lunghezze da 3-bit nell'ordine imposto da RFC1951
    for i in range(flen):
        cl = preTree.lengths[deflate_code_length_order[i]]
        b.write(cl, 3)
        if DEBUG and cl: print(f'code {deflate_code_length_order[i]} {cl}')
    # Comprime gli alberi (già compressi con RLE) con Huffman
    for S in rle:
        if isinstance(S, tuple):
            C = preTree.find_code(S[0])
            if DEBUG: print(f"{('repeat','zeros')[S[0]>16]} {S[1]+(3,3,11)[S[0]-16]}")
            b.write(C.cod, C.bits)
            b.write(S[1], (2,3,7)[S[0]-16]) # scrive il n° di ripetizione con la giusta q.tà di bit
        else:
            C = preTree.find_code(S)
            b.write(C.cod, C.bits)
            if DEBUG: print(f'lens {S}')
    return mainTree, distTree

# NOTE:
# - la conclusione anticipata di un blocco compresso dovrebbe essere guidata da...?
def compress(s, level=9, method=9, wbits=-15, memLevel=0, strategy=Z_DEFAULT_STRATEGY, zdict=None):
    """Comprime una stringa `s`. Hanno attualmente effetto `wbits` (se negativo,
    genera un bitstream raw, se positivo, aggiunge header e trailer di zlib)
    e `strategy` (Z_NO_COMPRESSION: non comprime; Z_FIXED: usa gli alberi di
    Huffman statici, incorporati in Deflate; Z_HUFFMAN_ONLY: comprime solo con
    Huffman senza ricercare le stringhe ripetute con LZ; Z_RLE: cerca solo le
    ripetizioni di byte in sequenza)"""
    if not s: return s

    is_raw = wbits < 0
    bits = abs(int(wbits))
    if bits < 9 or bits > 15:
        raise DeflateException(f"Bad wbits={wbits}, must be in range 9..15")
    window_size = 2**bits
    pos=old_pos=0
    matches=[]
    TOT_MATCHES=0

    #~ if DEBUG: print(f"Deflating {len(s)} bytes with {('Static Huffman', 'Dynamic Huffman')[mode]}")
    strategies = {Z_DEFAULT_STRATEGY: 'Default (Dynamic) Strategy',
    Z_NO_COMPRESSION: 'No compression',
    Z_FIXED: 'Static Huffman',
    Z_HUFFMAN_ONLY: 'Huffman only',
    Z_RLE: 'RLE encoding'}
    if DEBUG: print(f"Deflating {len(s)} bytes with {strategies[strategy]}")

    # Bitstream di output
    b = bitio.open(bytearray(), 'w')
    
    if not is_raw: # zlib header (2 byte)
        if DEBUG: print("zlib")
        M=3
        if method == 0 or level == Z_NO_COMPRESSION: M=0
        b.write(8, 4) # compression method
        b.write(bits-8, 4) # window (as 2^N)
        CM = ((bits-8)<<4) | 8
        b.write(fcheck(CM, M, 0), 5) # checksum
        b.write(0, 1) # user dictionary (0=false)
        b.write(M, 2) # suggested compression level

    while pos < len(s):
        freq_lit = freq_dist = None

        if strategy == Z_HUFFMAN_ONLY:
            if DEBUG: print("Using Huffman only, without LZ step")
            matches = s
        else:
            if method == 0 or level == Z_NO_COMPRESSION:
                old_pos = pos
                Q = min(65531, len(s)-pos) # scrive al massimo 65531 byte non compressi
                pos += Q
            else:
                old_pos = pos
                # Trova gli eventuali match nel buffer e restituisce una lista mista di byte e match
                matches, pos, freq_lit, freq_dist = find_matches(s, pos, window_size, RLE_only=strategy==Z_RLE)
                if DEBUG: print(f'LZ step produced {len(matches)} items')
                if DEBUG and s[old_pos:pos] != lz_expand(matches):
                    raise DeflateException("LZ step produced bad data")

        BFINAL = pos >= len(s)

        if BFINAL:
            if DEBUG: print("Last Block @", pos)
            b.write(1, 1) # last block
        else:
            if DEBUG: print("Block @", pos)
            b.write(0, 1)
            
        if method == 0 or level == Z_NO_COMPRESSION:
            b.write(0, 7) # stored
            n = Q & 0xFFFF # scrive la lunghezza a 16-bit
            b.write(n, 16) 
            b.write(~n & 0xFFFF, 16) # e il suo complemento
            b.extend(s[old_pos:pos])
            if BFINAL:
                break
            else:
                continue

        if strategy == Z_FIXED:
            b.write(1, 2) # Static Huffman
            # Usa gli alberi predefiniti
            mainTree = Tree(fixed_huffman_literal_lengths)
            distTree = Tree(fixed_huffman_distances)
        else:
            b.write(2, 2) # Dynamic Huffman
            # Genera gli alberi corrispondenti ai dati e li salva compressi
            mainTree, distTree = gen_dynamic_trees(matches, b, freq_lit, freq_dist)

        # Comprime con Huffman: i byte e le lunghezze dei match con mainTree, le distanze dei match con distTree
        for m in matches:
            if isinstance(m, tuple): # if match
                TOT_MATCHES += 1
                if m[0] < 3 or m[0] > 258:
                    raise DeflateException(f"Bad match length {m[0]}")
                if m[1] < 1 or m[1] > 32768:
                    raise DeflateException(f"Bad match distance {m[1]}")
                # calcola e scrive il codice per la lunghezza (più eventuali bit extra)
                base = deflate_length_symbol[m[0]-3]
                if DEBUG: print(f"match {m[0]} {m[1]}")
                C = mainTree.find_code(base)
                b.write(C.cod, C.bits)
                if DEBUG: print(f"writing {C.cod} {C.bits} bits")
                ebits = deflate_length_extra_bits[C.sym-257]
                if ebits:
                    # se vi sono bit extra, corrispondono alla differenza (lunghezza - base) del match
                    #~ if DEBUG: print(f'extra bits for length {m[0]}-{lendist_base(base)}: {ebits} -> {m[0]-lendist_base(base)}')
                    b.write(m[0] - deflate_base_lenghts[base-257], ebits)
                # calcola e scrive il codice per la distanza (più eventuali bit extra)
                base = len_to_base(m[1], 1)
                #~ if DEBUG: print(f'match distance base {base}')
                C = distTree.find_code(base)
                #~ if DEBUG: print(f'match distance code {K}')
                b.write(C.cod, C.bits)
                ebits = deflate_distance_extra_bits[C.sym]
                if ebits:
                    # se vi sono bit extra, corrispondono alla differenza (distanza - base) del match
                    #~ if DEBUG: print(f'extra bits for distance {m[1]}-{lendist_base(base,1)}: {ebits} -> {m[1]-lendist_base(base,1)}')
                    b.write(m[1] - deflate_base_distances[base], ebits)
            else: # literal
                C = mainTree.find_code(m)
                b.write(C.cod, C.bits)
                if DEBUG: print(f"literal '{chr(m).encode('utf8')}")
                if DEBUG: print(f"writing {C.cod} {C.bits} bits")

        # Codifica il simbolo di fine blocco (256)
        C = mainTree.find_code(256)
        b.write(C.cod, C.bits)
        if DEBUG: print("end")

    if not is_raw: # zlib trailer (4 byte)
        if DEBUG: print("adler")
        a = adler32(s) # adler32 checksum
        if DEBUG: print(f"adler32 {a:08X}")
        n = b.tell() % 8
        if n: b.write(0, 8-n) # allinea il blocco a 8 bit
        # scrive adler32 come Big-Endian
        b.write((a>>24) & 0xFF, 8)
        b.write((a>>16) & 0xFF, 8)
        b.write((a>>8) & 0xFF, 8)
        b.write(a & 0xFF, 8)
    b.flush()
    b.stream.seek(0)
    #~ print(f'compress: {TOT_MATCHES} total matches')
    return b.stream.read()
