# -*- coding: windows-1252 -*-
import pprint
from heapq import heapify, heappop, heappush
from collections import defaultdict
import itertools

DEBUG = 0

class HuffmanException(Exception):
    pass

def reverse_bits(n, bits=None):
    "Inverte i bit del numero `n`. Assume la sua lunghezza o `bits` bit"
    num_bits = bits if bits is not None else n.bit_length()
    reversed_n = 0
    for _ in range(num_bits):
        # Sposta `reversed_n` a sinistra di 1 e aggiungi il bit meno significativo di `n`
        reversed_n = (reversed_n << 1) | (n & 1)
        # Sposta `n` a destra di 1
        n >>= 1
    return reversed_n

def get_capacity(counts):
    "Calcola la somma delle capacità per una distribuzione di lunghezze di codice"
    capacity_sum = 0.0
    for bit_length, num_symbols in counts.items():
        capacity_sum += num_symbols / (2 ** bit_length)
    if capacity_sum < 1: print('NOTE: capacity_sum < 1', capacity_sum)
    return capacity_sum

def shrink_codes_miniz(histogram, max_bits):
    "Reduce Huffman code lengths to max_bits (from Stephan Brumme adaptation of Rich Geldreich's Miniz)"
    # move all oversized code lengths to the longest allowed
    for i in range(max_bits+1, len(histogram)):
        histogram[max_bits] += histogram[i]
        histogram[i] = 0
    # compute Kraft-Mc Millan sum using integer math
    ksum = 0
    i = max_bits
    while i > 0:
        ksum += (histogram[i] << (max_bits-i))
        i -= 1
    # iterate until ksum doesn't exceed 1 anymore
    one = 1 << max_bits
    while ksum > one:
        # select a code with maximum length, it will be moved
        histogram[max_bits] -= 1
        # find a second code with shorter length
        for i in range(max_bits-1, 0, -1):
            if histogram[i] > 0:
                histogram[i] -= 1
                # extend that shorter code by one bit
                # and assign the same code length to the selected one
                histogram[i+1] += 2
                break
        # moving these codes reduced the Kraft sum
        ksum -= 1
    return histogram

def shrink_codes_jpeg(histogram, max_bits):
    "Reduce Huffman code lengths to max_bits (from Stephan Brumme adaptation of Annex K.3 of the JPEG standard ITU T.81)"
    # iterate over all "excessive" bit lengths, beginning with the longest
    i = len(histogram)-1
    while i > max_bits:
        if not histogram[i]:
            i -= 1
            continue
        # look for codes that are at least two bits shorter
        j = i - 2
        while j > 0 and not histogram[j]: j-= 1
        # change bit length of 2 of the longest codes
        histogram[i] -= 2
        # one code becomes one bit shorter
        # (using the joint prefix of the old two codes)
        histogram[i-1] += 1
        # the other code has length j+1 now
        # but another, not-yet-involved, code with length j
        # is moved to bit length j+1 as well
        histogram[j+1] += 2
        histogram[j] -= 1
    # return longest code length that is still used
    while i > 0 and histogram[i] == 0: i -= 1
    
    return histogram

def get_code_lengths(frequencies, max_code_length=15):
    "Calcola le lunghezze dei codici di Huffman rispettando un limite massimo di lunghezza."
    # Restringe ai simboli con frequenza > 0
    frequencies = {sym: freq for sym, freq in frequencies.items() if freq > 0}
    
    # Con meno di due simboli (p.e. pre-tree), ne assegna di fittizi
    if len(frequencies) < 2:
        frequencies[0] = frequencies.get(0, 1)
        frequencies[1] = frequencies.get(1, 1)

    #~ print('frequencies', frequencies)
    # Creazione dell'albero di Huffman
    heap = []
    counter = itertools.count()  # Contatore unico per distinguere i nodi
    
    for symbol, freq in frequencies.items():
        heappush(heap, (freq, next(counter), symbol))
    
    while len(heap) > 1:
        freq1, _, node1 = heappop(heap)
        freq2, _, node2 = heappop(heap)
        heappush(heap, (freq1 + freq2, next(counter), [node1, node2]))

    # Calcola le lunghezze iniziali dei codici
    _, _, root = heappop(heap)
    code_lengths = defaultdict(int)

    def assign_lengths(node, depth):
        if isinstance(node, list):  # Se è un nodo interno
            assign_lengths(node[0], depth + 1)
            assign_lengths(node[1], depth + 1)
        else:  # Se è una foglia (simbolo)
            code_lengths[node] = depth

    assign_lengths(root, 0)
    #~ print('code_lengths', code_lengths)
    
    # Determina i simboli per lunghezza di codice e la lunghezza massima
    counts = defaultdict(int)
    for length in code_lengths.values():
        counts[length] += 1

    # Crea una lista di occorrenze per lunghezza di bit
    hgram = (max(counts)+1) * [0]
    for k, v in counts.items():
        hgram[k] = v

    # Se vi sono lunghezze eccedenti o è violata la diseguaglianza Kraft-McMillan
    # (tipico nel pre-tree), le trasforma in altrettanti codici più corti
    if max(counts) > max_code_length or get_capacity(counts) > 1:
        if DEBUG: print('old counts', counts)
        counts = shrink_codes_miniz(hgram, max_code_length)
        if DEBUG: print('new counts', counts)

    # Ricostruisci le lunghezze dei codici
    sorted_symbols = sorted(frequencies.keys(), key=lambda s: (code_lengths[s], -frequencies[s]))
    new_code_lengths = {}
    current_length = 0

    for symbol in sorted_symbols:
        while counts[current_length] == 0:
            current_length += 1
        new_code_lengths[symbol] = current_length
        counts[current_length] -= 1

    #~ print('new_code_lengths', new_code_lengths)
    return new_code_lengths


class Node:
    "Nodo foglia dell'albero di Huffman"
    __slots__ = ('bits', 'cod', 'sym')

    def __init__(p, bits, sym):
        p.bits = bits # lunghezza in bit del codice
        p.cod = 0 # codice binario rappresentativo del percorso al simbolo
        p.sym = sym # simbolo rappresentato dal codice

    #~ def __eq__(p, o):
        #~ return p.bits==o.bits and p.cod==o.cod and p.sym==o.sym

    def __repr__(p):
        return f"Node<bits={p.bits},code={format(p.cod, '0%db'%p.bits)}({p.cod}),symbol={p.sym}>"

class Tree:
    "Albero canonico di Huffman come tabella di codici ordinati per lunghezza e simbolo"

    def __init__(p, lengths):
        "Riceve una lista o tupla di lunghezze in bit ordinate per simbolo"
        if len(lengths) < 2:
            raise HuffmanException("At lest 2 code lenghts required by canonical Huffman tree")
        p.lengths = lengths
        p.leafs_d = {} # dict {(<bits>, <cod>): <sym>}} per find_symbol
        p.leafs_c = len(lengths) * [None] # lista ordinata di Node per find_code
        p.nodes = p._expand_table(lengths) # crea la tabella di nodi ordinati a partire dalle lunghezze
        if len(p.nodes):
            p.min_bits = p.nodes[0].bits # determina le lunghezze minima e massima di un codice
            p.max_bits = p.nodes[-1].bits

    def __eq__(p, o):
        return p.nodes==o.nodes

    def from_freqs(freqs, max_codes, max_length=15, out_lengths=False):
        "Genera l'albero da un dizionario {simbolo: frequenza}, con un massimo di codici di limite di lunghezza"
        codes = get_code_lengths(freqs, max_length)
        L = max_codes*[0]
        for k, v in codes.items():
            L[k] = v
        if out_lengths: return L
        return Tree(L)

    def short_lengths(p):
        # rimuove i simboli non in uso (in coda)
        while p.lengths and p.lengths[-1] == 0: p.lengths.pop()
        return p.lengths

    def _expand_table(p, a):
        # ricrea una tabella di nodi Node da un array di lunghezze in bit
        L = []
        for i in range(len(a)):
            if not a[i]: continue # ignora i nodi vuoti
            L.append(Node(a[i], i))
        # ordina per di bit e simbolo
        L = sorted(L, key=lambda x: (x.bits, x.sym))
        n=0
        for i in range(len(L)):
           # quando aumentano i bit, cala la frequenza dei simboli e ci 
           # spostiamo a un altro nodo padre: ciò viene rappresentato 
           # aumentando la lunghezza del codice di tanti bit quanto è il
           # "salto"
           if L[i].bits > L[i-1].bits: n <<= (L[i].bits - L[i-1].bits)
           # un byte è scritto di regola in modo naturale, dal MSB al LSB;
           # un albero binario di Huffman viene rappresentato graficamente "Top-Down"
           # (i codici più frequenti in alto, i meno frequenti in basso) ma l'assegnazione
           # dei bit avviene in senso contrario ("Bottom-Up": in alto meno bit e dunque codici
           # più corti, in basso più lunghi): ecco perché i bit del simbolo vanno invertiti.
           # Per esempio, il codice "6" (0b110 in modo binario naturale) va letto come 0-1-1
           # ai fini dello spostamento nell'albero.
           L[i].cod = reverse_bits(n, L[i].bits)
           if not p.leafs_d.get(L[i].bits):
               p.leafs_d[L[i].bits] = {}
           p.leafs_d[ (L[i].bits, L[i].cod) ] = L[i].sym
           p.leafs_c[L[i].sym] = L[i]
           n+=1
        return L

    def find_symbol(p, cod, bits):
        'Trova il simbolo lungo "bits" bit e corrispondente al codice "cod"'
        return p.leafs_d.get((bits, cod))

    def find_code(p, sym):
        'Trova il codice corrispondente al simbolo "sym"'
        n = p.leafs_c[sym]
        if not n:
            raise HuffmanException(f"No Huffman code found for symbol {sym}")
        if DEBUG>1: print(f'find_code {sym} found {n}')
        return n
