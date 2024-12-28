# -*- coding: windows-1252 -*-
import math

# simbolo dell'ordine di grandezza della lunghezza di un match (3..258) nell'albero Literals/Lengths
deflate_base_lenghts = (3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258) # 29

# simbolo dell'ordine di grandezza della distanza di un match (1..32768) nell'albero Distances
deflate_base_distances = (1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577) # 30

# Lista delle lunghezze della tabella fissa di Huffman incorporata in Deflate
# per codificare byte e lunghezze dei match. I primi 144 simboli (0-143)
# sono rappresentati con codici da 8 bit, i successivi 112 con codici
# da 9 bit e così via. Ovviamente, i primi 256 simboli sono i normali byte;
# il 257° rappresenta la fine dello stream; i successivi, le lunghezze (o,
# meglio, il loro ordine di grandezza) dei match.

# RFC1951 richiede l'ordinamento crescente dei codici per numero di bit e per
# valore del simbolo.
fixed_huffman_literal_lengths = [8]*144 + [9]*112 + [7]*24 + [8]*8 # 288
fixed_huffman_distances = [5]*32 # 32 

deflate_code_length_order = (16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15) # 0-18

# tabella dei simboli associati a una lunghezza di match
deflate_length_symbol = (257, 258, 259, 260, 261, 262, 263, 264, 265, 265, 266, 266, 267, 267, 268, 268, 269, 269, 269, 269, 270, 270, 270, 270, 271, 271, 271, 271, 272, 272, 272, 272, 273, 273, 273, 273, 273, 273, 273, 273, 274, 274, 274, 274, 274, 274, 274, 274, 275, 275, 275, 275, 275, 275, 275, 275, 276, 276, 276, 276, 276, 276, 276, 276, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 285)

# tabella dei bit extra associati a un simbolo di lunghezza
deflate_length_extra_bits = (0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0)

# tabella dei bit extra associati a un simbolo di distanza
deflate_distance_extra_bits = (0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13)

def len_to_base(l, mode=0):
    "Data una lunghezza o distanza di match, ritorna il suo ordine di grandezza"
    T = (deflate_base_lenghts, deflate_base_distances)[mode]
    j=0
    for i in T:
        if l <= i: break
        j+=1
    if j == len(T): j-=1
    if mode == 0:
        #~ print(j, len(T), l)
        #~ if l < T[j] and j: j -= 1
        if l < T[j]: j -= 1
        return j+257
    else:
        if j >= len(T): j -= 1
        if l < T[j]: j -= 1
        return j

def adler32(data, a=1):
    """
    Calcola Adler-32 con blocchi adattivi.
    :param data: Dati in input come bytes o bytearray.
    :param a: Valore iniziale (default: 1).
    :return: Checksum Adler-32 come intero a 32 bit.
    """
    MOD_ADLER = 65521
    b = 0
    block_size = 5552  # Blocco massimo per evitare overflow

    for i in range(0, len(data), block_size):
        block = data[i:i + block_size]
        for byte in block:
            a = (a + byte) % MOD_ADLER
            b = (b + a) % MOD_ADLER

    a = (b << 16) | a
    return a

def fcheck(cmf, flevel, fdict):
    """
    Calcola il valore di FCHECK per un header Zlib.
    :param cmf: Primo byte (CMF), contiene CINFO e CM.
    :param flevel: Livello di compressione (2 bit, valori da 0 a 3).
    :param fdict: Indica se viene usato un dizionario predefinito (0 o 1).
    :return: Byte FLG con FCHECK calcolato.
    """
    assert 0 <= flevel <= 3, "FLEVEL deve essere tra 0 e 3"
    assert fdict in (0, 1), "FDICT deve essere 0 o 1"
    
    # Costruisci FLG senza FCHECK
    flg = (flevel << 6) | (fdict << 5)
    
    # Calcola il checksum
    header = (cmf << 8) | flg
    fcheck = (31 - (header % 31)) % 31
    
    # Inserisci FCHECK nei 5 bit meno significativi
    flg |= fcheck
    return flg

def rle_dec(L):
    "Espande un set compresso da rle_enc"
    DL = []
    for S in L:
        if isinstance(S, tuple):
            C, length = S
            if C == 18:
                DL += (length+11)*[0]
            elif C == 17:
                DL += (length+3)*[0]
            elif C == 16:
                DL += (length+3)*[DL[-1]]
            else:
                raise Exception("Bad RLE code", C)
        else:
            DL += [S]
    return DL

def hellinger_distance(freqs1, freqs2):
    # Assicurati che le distribuzioni abbiano le stesse chiavi
    all_symbols = set(freqs1.keys()).union(freqs2.keys())
    
    # Normalizza le frequenze per ottenere distribuzioni di probabilità
    sum1 = sum(freqs1.values())
    sum2 = sum(freqs2.values())
    
    p = {symbol: freqs1.get(symbol, 0) / sum1 for symbol in all_symbols}
    q = {symbol: freqs2.get(symbol, 0) / sum2 for symbol in all_symbols}
    
    # Calcola la distanza di Hellinger
    h_distance = 0.0
    for symbol in all_symbols:
        h_distance += (math.sqrt(p[symbol]) - math.sqrt(q[symbol]))**2
    
    return math.sqrt(0.5 * h_distance)

def kl_divergence(p, q):
    """
    Calcola la divergenza di Kullback-Leibler tra due distribuzioni di probabilità.
    
    Args:
        p (list): Distribuzione di probabilità p.
        q (list): Distribuzione di probabilità q.

    Returns:
        float: La divergenza di Kullback-Leibler tra p e q.
    """
    kl_sum = 0.0
    for p_i, q_i in zip(p, q):
        if p_i > 0 and q_i > 0:
            kl_sum += p_i * math.log2(p_i / q_i)
    return kl_sum

def jsd_variation(freqs1, freqs2):
    """
    Calcola la distanza di Jensen-Shannon tra due distribuzioni di frequenze.
    
    Args:
        freqs1 (dict): Dizionario con le frequenze dei simboli nel primo blocco.
        freqs2 (dict): Dizionario con le frequenze dei simboli nel secondo blocco.

    Returns:
        float: La distanza di Jensen-Shannon tra le due distribuzioni.
    """
    # Trova tutti i simboli presenti in entrambe le distribuzioni
    all_symbols = set(freqs1.keys()).union(freqs2.keys())

    # Crea vettori di probabilità per i simboli
    p = [freqs1.get(symbol, 0) for symbol in all_symbols]
    q = [freqs2.get(symbol, 0) for symbol in all_symbols]

    # Normalizza i vettori in modo da convertirli in distribuzioni di probabilità
    sum_p = sum(p)
    sum_q = sum(q)
    p = [x / sum_p for x in p]
    q = [x / sum_q for x in q]

    # Calcola la media M delle due distribuzioni
    m = [(p_i + q_i) / 2 for p_i, q_i in zip(p, q)]

    # Calcola la divergenza di Jensen-Shannon
    jsd = math.sqrt(0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m))

    return jsd
