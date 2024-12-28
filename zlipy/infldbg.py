# -*- coding: windows-1252 -*-
from zlipy.huffman import Tree
from zlipy import bitio
from zlipy.utils import *

DEBUG=1

class InflateException(Exception):
    pass

def next_symbol(b, t):
    "Cerca di decodificare il prossimo simbolo nell'albero `t` leggendo dal bit stream `b`"
    # Scruta il massimo numero di bit possibile
    C = b.peek(t.max_bits)
    S = None

    # Prova dal codice più corto a quello più lungo
    for cl in range(t.min_bits, t.max_bits + 1):
        prefix = C & ((1 << cl) - 1)  # Ottieni i primi `cl` bit
        S = t.find_symbol(prefix, cl)
        if S is not None:
            b.read(cl)  # Leggi i bit effettivi usati
            return S

def match_expand(out, length, distance):
    "Espande un match direttamente nel buffer `out`"
    if DEBUG>1: print(f'expanding match of ({length}, -{distance})')
    if length >= distance:
        s = length * out[-distance:] # ripete la sequenza (finale)
        out.extend(s[:length]) # la limita a length
    else:
        if DEBUG>1: print('copied', out[-distance:-distance+length])
        out.extend(out[-distance:-distance+length]) # copia i byte esistenti
    return out

def read_dynamic_trees(b):
    "Ricostruisce gli alberi dinamici di Huffman salvati a inizio blocco"
    start = b.tell()
    litLenSize = b.read(5) + 257
    distSize = b.read(5) + 1
    dynCodesLen = b.read(4) + 4
    if DEBUG: print ("count", litLenSize, distSize, dynCodesLen)

    # RFC1951 specifies codes length and order
    l = [0] * 19
    for i in range(dynCodesLen):
        cli = deflate_code_length_order[i]
        clc = b.read(3)
        l[cli] = clc
        if DEBUG>1 and clc: print (f"code {cli} {clc}")

    dynCodesTree = Tree(l)

    # Decode code lengths for both Literals/Lengths and Distances tables
    lengths = []
    i = 0
    while i < (litLenSize + distSize):
        S = next_symbol(b, dynCodesTree)
        if 0 <= S <= 15: # length itself
            n = 1
            l = S
            if DEBUG>1: print(f'lens {S}')
        elif S == 16: # repeat last
            n = 3 + b.read(2)
            l = lengths[-1]
            if DEBUG>1: print(f'repeat {n}')
        elif S == 17: # repeat zeros (few)
            n = 3 + b.read(3)
            l = 0
            if DEBUG>1: print(f'zeros {n}')
        elif S == 18: # repeat zeros (many)
            n = 11 + b.read(7)
            l = 0
            if DEBUG>1: print(f'zeros {n}')
        else:
            raise InflateException(f"Bad dynamic code length {S}")
        lengths.append([l] * n)
        i += n

    if DEBUG: print ("Main tree lengths:", lengths[:litLenSize])
    if DEBUG: print ("Dist tree lengths:", lengths[litLenSize:])
    if DEBUG: print (f"Dynamic Huffman tables have {b.tell()-start} bits.")
    return Tree(lengths[:litLenSize]), Tree(lengths[litLenSize:])


# da 1000 a 33000 volte più lento di zlib, in proporzione alla lunghezza dell'input:
# investigare, poiché compress non è così lento!
def decompress(s, wbits=-15, return_lz=True):
    """Decomprime uno o più blocchi compressi con Deflate. `wbits` è usato per
    determinare la tipologia di blocco (grezzo o zlib). `return_lz` genera una
    lista mista di byte e match, a scopo di analisi e debug."""
    if not s: return s

    is_raw = wbits < 0
    bits = abs(int(wbits))
    if bits < 9 or bits > 15:
        raise InflateException(f"Bad wbits={wbits}, must be in range 9..15")
    window_size = 2**bits
    BIDX = -1

    b = bitio.open(s) # open compressed bit stream
    
    if not is_raw: # zlib header
        if DEBUG: print("zlib")
        m = b.read(4) # compression method (8=Deflated)
        bits = 8+b.read(4) # window (as 2^N)
        checksum = b.read(5)
        userdict = b.read(1) # user dictionary (0=false)
        if userdict:
            raise InflateException("Can't inflate block with user provided dictionary")
        clevel = b.read(2) # suggested compression level
        calculated = ((bits-8)<<4) | m
        if checksum != fcheck(calculated, clevel, userdict):
            raise InflateException("Bad zlib header checksum")

    out = bytearray() # output buffer
    if return_lz:
        matches = []
        blocks_list = []

    # Loop principale (espande tutti i blocchi)
    while 1:
        BCSTART = b.tell()
        BUSTART = len(out)
        BIDX += 1
        BFINAL = b.read(1)
        if DEBUG: print ('Last? ', BFINAL)
        BTYPE = b.read(2)
        if DEBUG: print(f'Block {BIDX} type:', ("Stored", "Fixed Huffman", "Dynamic Huffman","Invalid")[BTYPE])
        #~ print(f'Block {BIDX} type:', ("Stored", "Fixed Huffman", "Dynamic Huffman","Invalid")[BTYPE])
        if BTYPE == 0: # Stored
            if DEBUG: print(b.tell(), 'bit pos at stored block')
            b.read(8-b.tell()%8) # align at byte boundary
            length = b.read(16)
            htgnel = b.read(16)
            if length != ~htgnel&0xFFFF:
                raise InflateException("stored block lengths do not match")
            for i in range(length):
                out.extend(b.read(8).to_bytes(1,'little'))
            if BFINAL:
                break
            else:
                continue
        elif BTYPE == 2: # Dynamic Huffman trees
            litLenTree, distTree = read_dynamic_trees(b)
            if DEBUG: print('Dynamic trees reconstructed')
        elif BTYPE == 1: # Static Huffman trees
            litLenTree, distTree = Tree(fixed_huffman_literal_lengths), Tree(fixed_huffman_distances)
        else:
            raise InflateException("bad block type")

        # Loop secondario (espande il blocco corrente fino al simbolo 256=End Of Block)
        while 1:
            sym = next_symbol(b, litLenTree)
            if sym == 256:
                break # Fine del blocco corrente
            elif 256 < sym < 286:
                if DEBUG>1: print('found match')
                # un match è codificato come (lunghezza, distanza)
                # la lunghezza (3..258) può richiedere la lettura di bit extra dallo stream
                ebits = deflate_length_extra_bits[sym-257]
                if DEBUG>1: print('extra bits required for match length:', ebits)
                ebits = b.read(ebits)
                length = deflate_base_lenghts[sym-257] + ebits
                if DEBUG>1: print('match length is', length)
                # la distanza (codificata con 5 bit) richiede sempre la lettura di bit extra
                d = next_symbol(b, distTree)
                if 0 <= d <= 29:
                    ebits = deflate_distance_extra_bits[d]
                    if DEBUG>1: print ('extra bits required for match distance:', ebits)
                    distance = deflate_base_distances[d] + b.read(ebits)
                    if DEBUG>1: print('match distance is', distance)
                    out = match_expand(out, length, distance)
                    if return_lz:
                        matches.append((length, distance))
                elif 30 <= r1 <= 31:
                    raise f"illegal unused distance symbol in use @ {b.tell()}"
            elif sym < 256:
                if DEBUG>1: print(f'found literal "{sym}"')
                out.extend(sym.to_bytes(1,'little'))
                if return_lz:
                    matches.append(sym)
            else:
                raise InflateException(f"Invalid code at bit {br.tell()}")
        if DEBUG: print(f'Deflated/expanded block size: {((b.tell()-BCSTART)+7)//8}/{len(out)-BUSTART}')
        blocks_list.append( (BIDX, BTYPE, ((b.tell()-BCSTART)+7)//8, len(out)-BUSTART) )
        # esce dal loop se abbiamo espanso l'ultimo blocco
        if BFINAL: break
    print (f'{len(blocks_list)} blocks, {min(blocks_list, key=lambda t: t[-2])[-2]}-{max(blocks_list, key=lambda t: t[-2])[-2]} compressed bytes:\n{blocks_list}')
    if return_lz: return matches
    if not is_raw: # zlib trailer
        if DEBUG: print("adler")
        A = adler32(out) # adler32 checksum
        if DEBUG: print(f"adler32 {A:08X}")
        n = b.tell() % 8
        if n: b.read(8-n) # allinea il blocco a 8 bit
        # legge adler32 come Big-Endian
        a = 0
        a |= (b.read(8)<<24)
        a |= (b.read(8)<<16)
        a |= (b.read(8)<<8)
        a |= b.read(8)
        if a != A:
            raise InflateException("adler32 checksum does not match")
    return out
