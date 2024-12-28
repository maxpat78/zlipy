# -*- coding: windows-1252 -*-
DEBUG = 0
import bisect
from collections import defaultdict, deque
from .utils import *
from .huffman import Tree

def lz_expand(stream):
    "Espande una lista di byte e match nel buffer originale"
    out = b''
    for o in stream:
        if isinstance(o, tuple):
            length, distance = o
            if length >= distance:
                s = out[-distance:] # estrae la sequenza (finale) da ripetere
                s = s * length # la ripete
                s = s[:length] # la limita a length
                out += s
            else:
                out += out[-distance:-distance+length] # copia i byte esistenti
        else:
            out += o.to_bytes(1)
    return out

def calc_block_cost(freqs):
    "Stima la dimensione del blocco compresso, inclusa la dimensione dell'albero Huffman"
    mainTree = Tree.from_freqs(freqs, 288, out_lengths=1)
    cost = 0
    for sym, freq in freqs.items():
        C = mainTree[sym]
        cost += freq * C + C + 3 # assume un costo grezzo dell'albero di n+3 bit per simbolo
    return cost // 8

# Associa a ogni posizione del buffer una chiave di 3 byte iniziante in quella posizione
# A ogni chiave è associata una lista "deque" di posizioni
# Se ritrova la chiave, esamina tutte le posizioni valide dove ricorre, alla ricerca del match più lungo
def find_matches_hc3_best(data, i, window_size=32768, min_length=3, max_length=258, RLE_only=False):
    #~ data = memoryview(data) # incredibilmente, peggiora le prestazioni!
    start_pos = i
    matches = []
    table = {}  # Mappa {key: [offset]}

    # Inizializza i dizionari delle frequenze dei simboli di Deflate
    freq_lit = defaultdict(int)
    freq_dist = defaultdict(int)
    freq_lit[256] = 1 # il simbolo End Of Stream compare 1 volta a fine blocco
    freq_sampled = i # ultimo offset di campionamento
    prev_freq_lit = None
    ratio0 = 0
    
    LEN = len(data) # evita le successive chiamate a len(data)
    while i < LEN:
        # Campiona periodicamente il tasso di compressione
        # (512b, 0.01)  > (512b, 0.02)
        if i - freq_sampled >= 2048:
            if not prev_freq_lit:
                freq_sampled = i
                prev_freq_lit = freq_lit.copy()
                ratio0 = calc_block_cost(freq_lit) / (i-start_pos)
            else:
                freq_sampled = i
                #~ ratio1 = calc_block_cost(freq_lit) / (i-start_pos)
                #~ if (ratio1 - ratio0) > 0.01:
                    #~ if DEBUG: print(f'Ratio decay >0.01% @{i}, ending block')
                    #~ return matches, i, freq_lit, freq_dist
                cost = calc_block_cost(freq_lit)
                ratio1 = cost / (i-start_pos)
                if cost > 32<<10 or (ratio1 - ratio0) > 0.02:
                    if DEBUG: print(f'ending block @{i}')
                    return matches, i, freq_lit, freq_dist
                ratio0 = min(ratio0, ratio1)
                #~ # Se >0.5 conviene chiudere il blocco
                #~ dist = hellinger_distance(prev_freq_lit, freq_lit)
                #~ if dist > 0.5:
                    #~ if DEBUG: print(f'Hellinger distance @{i} = {dist}, ending block')
                    #~ return matches, i, freq_lit, freq_dist

        if i + min_length > LEN:  # Se non ci sono abbastanza byte per un match
            matches.append(data[i])
            freq_lit[data[i]] += 1
            i += 1
            continue

        # PyPy/Python 3.12: cambiare tipo di chiave non accelera
        key = data[i:i + 3]
        #~ key = tuple(data[i:i + 3])
        #~ key = int.from_bytes(data[i:i+3], 'big')
        
        # Testare questa sezione. Eseguirla in modo non RLE peggiora la compressione!
        if RLE_only:
            def is_rl(L, i):
                rlen = 1
                while i < len(L)-1 and L[i] == L[i+1]:
                    i += 1
                    rlen += 1
                    if rlen == max_length+1: break
                if rlen < min_length+1: return
                return rlen
            # Cerca una sequenza di byte uguali
            rlen = is_rl(data, i)
            if rlen:
                if DEBUG: print(f'lz77 detected run of {rlen} at {i}')
                table[key] = i
                table[key] = i + rlen - 3
                matches.append(data[i])
                freq_lit[data[i]] += 1
                matches.append((rlen-1, 1))
                freq_lit[deflate_length_symbol[rlen-4]] += 1
                freq_dist[0] += 1
                i += rlen
                continue

            # Aggiunge il literal e continua
            matches.append(data[i])
            freq_lit[data[i]] += 1
            i += 1
            continue

        best_length = 0
        best_offset = 0

        keyed = table.get(key)
        if keyed:
            for offset in keyed:
            #~ for offset in reversed(keyed):
                # Se la distanza rientra nella finestra
                if i - offset <= window_size:
                    # Trova la lunghezza del match
                    length = 0
                    while length < max_length and i + length < LEN and offset + length < LEN and data[offset + length] == data[i + length]:
                        length += 1
                    # Se è maggiore della lunghezza minima e della migliore, aggiorna quest'ultima
                    # NOTA: occorre calcolare qui cos'è "migliore"
                    if length >= min_length and length > best_length:
                        best_length = length
                        best_offset = i - offset
                else:
                    break # poiché sono ordinate dalla più prossima

        # Aggiorna la tabella hash con la posizione corrente
        if not keyed:
            table[key] = deque([i])
            #~ table[key] = [i]
        else:
            keyed.appendleft(i)
            #~ keyed.append(i)

        def insert_keys(table, data, i, length):
            "inserisce le chiavi nell'area del match"
            # la posizione i è appena stata inserita
            # ignora a fine buffer
            if i+length > LEN-4: return
            for j in range(i+1, i+length):
                key = data[j:j + 3]
                #~ key = tuple(data[j:j + 3])
                #~ key = int.from_bytes(data[j:j+3], 'big')
                keyed = table.get(key)
                if not keyed:
                    table[key] = deque([j])
                    #~ table[key] = [i]
                else:
                    keyed.appendleft(j)
                    #~ keyed.append(i)
                        
        #~ def insert_keys(table, data, i, length, max_inserts=16):
            #~ count = 0
            #~ for j in range(i + 1, i + length):
                #~ if count >= max_inserts:
                    #~ break
                #~ key = data[j:j + 3]
                #~ table.setdefault(key, deque()).appendleft(j)
                #~ count += 1

        #~ if best_length >= min_length:
            #~ matches.append((best_length, best_offset))
            #~ freq_lit[deflate_length_symbol[best_length-3]] += 1
            #~ freq_dist[len_to_base(best_offset,1)] += 1
            #~ insert_keys(table, data, i, best_length)
            #~ i += best_length  # Salta alla fine del match
            #~ continue
        if best_length >= min_length:
            next_best_length = 0
            next_best_offset = 0

            # Controlla se il prossimo byte offre un match migliore
            key_next = data[i+1:i+4]
            keyed_next = table.get(key_next)
            if keyed_next:
                for offset in keyed_next:
                #~ for offset in reversed(keyed_next):
                    if i + 1 - offset <= window_size:
                        length = 0
                        while length < max_length and i + 1 + length < LEN and offset + length < LEN and data[offset + length] == data[i + 1 + length]:
                            length += 1
                        if length > next_best_length:
                            next_best_length = length
                            next_best_offset = i + 1 - offset
                    else: break # <-- dobbiamo interrompere se fuori finestra?

            # Scegli il match migliore
            if next_best_length > best_length:
                matches.append(data[i])
                freq_lit[data[i]] += 1
                i += 1
            else:
                matches.append((best_length, best_offset))
                freq_lit[deflate_length_symbol[best_length-3]] += 1
                #~ freq_dist[len_to_base(best_offset, 1)] += 1
                # Calcola il codice di distanza
                dcode = bisect.bisect_right(deflate_base_distances, best_offset) - 1
                freq_dist[dcode] += 1
                insert_keys(table, data, i, best_length)
                i += best_length
            continue
        # Se non c'è match, aggiunge un literal
        matches.append(data[i])
        freq_lit[data[i]] += 1
        i += 1

    return matches, i, freq_lit, freq_dist

def find_matches_hc3_fast(data, i, window_size=32768, min_length=3, max_length=258, RLE_only=False):
    start_pos = i
    matches = []
    hash_table = {} # {<3 bytes>: offset}

    # Inizializza i dizionari delle frequenze dei simboli di Deflate
    freq_lit = defaultdict(int)
    freq_dist = defaultdict(int)
    freq_lit[256] = 1 # il simbolo End Of Stream compare 1 volta a fine blocco
    freq_sampled = i # ultimo offset di campionamento
    prev_freq_lit = None
    
    LEN = len(data) # evita le successive chiamate a len(data)
    while i < LEN:
        # Campiona periodicamente il tasso di compressione
        if i - freq_sampled >= 512:
            if not prev_freq_lit:
                freq_sampled = i
                prev_freq_lit = freq_lit.copy()
                ratio0 = calc_block_cost(freq_lit) / (i-start_pos)
            else:
                freq_sampled = i
                cost = calc_block_cost(freq_lit)
                ratio1 = cost / (i-start_pos)
                if cost > 32<<10 or (ratio1 - ratio0) > 0.02:
                    if DEBUG: print(f'ending block @{i}')
                    #~ print(f'ending block @{i}')
                    return matches, i, freq_lit, freq_dist
                ratio0 = min(ratio0, ratio1)

        if i + min_length <= LEN:
            # Associa ogni posizione nella finestra a una chiave correlata ai 3 byte
            # contenutivi: se è stata già vista, è probabile che vi sia un match
            # di 3 o più byte.
            key = data[i:i+min_length]
            #~ key = int.from_bytes(data[i:i+3], 'big')
            #~ key = tuple(data[i:i+3])
            
            # Testare questa sezione. Eseguirla in modo non RLE peggiora la compressione!
            if RLE_only:
                def is_rl(L, i):
                    rlen = 1
                    while i < len(L)-1 and L[i] == L[i+1]:
                        i += 1
                        rlen += 1
                        if rlen == max_length+1: break
                    if rlen < min_length+1: return
                    return rlen
                # Cerca una sequenza di byte uguali
                rlen = is_rl(data, i)
                if rlen:
                    if DEBUG: print(f'lz77 detected run of {rlen} at {i}')
                    table[key] = i
                    table[key] = i + rlen - 3
                    matches.append(data[i])
                    freq_lit[data[i]] += 1
                    matches.append((rlen-1, 1))
                    freq_lit[deflate_length_symbol[rlen-4]] += 1
                    freq_dist[0] += 1
                    i += rlen
                    continue

                # Aggiunge il literal e continua
                matches.append(data[i])
                freq_lit[data[i]] += 1
                i += 1
                continue

            match_start = hash_table.get(key, -1)
            length = 0

            # Se esiste un match valido nella finestra, estendiamo la lunghezza del match
            if match_start != -1 and (i - match_start) <= window_size:
                # Iniziamo l'estensione del match confrontando i byte nelle posizioni globali
                while length < max_length and i + length < LEN and data[match_start + length] == data[i + length]:
                    length += 1

                # Se il match è abbastanza lungo (>= min_length), lo aggiungiamo come match
                if length >= min_length:
                    offset = i - match_start  # Calcola la distanza dalla posizione corrente nella finestra
                    hash_table[key] = i # Aggiorna l'offset alla posizione viciniore
                    matches.append((length, offset))
                    freq_lit[deflate_length_symbol[length-3]] += 1
                    #~ freq_dist[len_to_base(offset,1)] += 1
                    # Calcola il codice di distanza
                    dcode = bisect.bisect_right(deflate_base_distances, offset) - 1
                    freq_dist[dcode] += 1
                    i += length  # Avanza alla fine del match
                    continue  # Riprendi la ricerca, senza aggiungere literal

            # Se non c'è un match valido o il match è troppo corto, aggiungi il byte come literal
            matches.append(data[i])
            freq_lit[data[i]] += 1
            
            # Aggiorna la tabella hash e avanza al byte successivo
            hash_table[key] = i
            i += 1
        else:
            # Se non c'è spazio sufficiente per un match, aggiungi il literal
            matches.append(data[i])
            freq_lit[data[i]] += 1
            i += 1
    return matches, i, freq_lit, freq_dist

from matcher import Matcher
def find_matches_hc3_cpp(data, i, window_size=32768, min_length=3, max_length=258, RLE_only=False):
    start_pos = i
    matches = []
    GRAIN_SIZE = 64<<10

    freq_sampled = i # ultimo offset di campionamento
    prev_freq_lit = None
    ratio0 = 0
    
    LEN = len(data) # evita le successive chiamate a len(data)
    M = Matcher(9)
    while i < LEN:
        #~ # Campiona periodicamente il tasso di compressione
        #~ if i - freq_sampled >= GRAIN_SIZE:
            #~ if not prev_freq_lit:
                #~ freq_sampled = i
                #~ prev_freq_lit = freq_lit.copy()
                #~ ratio0 = calc_block_cost(freq_lit) / (i-start_pos)
            #~ else:
                #~ freq_sampled = i
                #~ cost = calc_block_cost(freq_lit)
                #~ ratio1 = cost / (i-start_pos)
                #~ if cost > 20<<10 or (ratio1 - ratio0) > 0.02:
                    #~ print(f'ending block @{i}, {cost}, {ratio1}, {ratio1 - ratio0}')
                    #~ if DEBUG: print(f'ending block @{i}')
                    #~ return matches, i, freq_lit, freq_dist
                #~ ratio0 = min(ratio0, ratio1)

        i = M.find_matches(data, i, LEN, matches)
        freq_lit, freq_dist = M.get_freqs()
        return matches, i, freq_lit, freq_dist
    return matches, i, freq_lit, freq_dist

find_matches = find_matches_hc3_best # 25 (23) *PyPy*
#~ find_matches = find_matches_hc3_fast # 24.68 (14.02) Python
find_matches = find_matches_hc3_cpp # 11.19 (1.30) Python
