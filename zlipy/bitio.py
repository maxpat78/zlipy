# -*- coding: windows-1252 -*-
import io

class BitIOException(Exception):
    pass

class BitStream:
    def __init__(self, stream=None, mode='r'):
        if not stream:
            stream = io.BytesIO()
        elif not isinstance(stream, (io.BufferedIOBase, io.BytesIO)):
            raise ValueError("Il parametro stream deve essere un oggetto di I/O bufferizzato (es. file aperto in modalità binaria)")
        
        self.stream = stream
        self.mode = mode
        self.buffer = 0
        self.buffer_len = 0
        self.bit_pos = 0  # Posizione attuale in bit nel flusso di dati

    # ----- Metodi per la lettura -----
    def _fill_buffer(self, bits_needed):
        """Riempi il buffer per avere almeno `bits_needed` bit."""
        while self.buffer_len < bits_needed:
            byte = self.stream.read(1)
            if not byte:
                break  # Fine del flusso di dati
            self.buffer |= (byte[0] << self.buffer_len)
            self.buffer_len += 8

    def read(self, num_bits):
        """Legge `num_bits` bit dallo stream e restituisce il valore come intero in little-endian."""
        if num_bits == 0:
            return 0
        self._fill_buffer(num_bits)
        if self.buffer_len < num_bits:
            raise EOFError("Fine del flusso di dati")
        bits = self.buffer & ((1 << num_bits) - 1)
        self.buffer >>= num_bits
        self.buffer_len -= num_bits
        self.bit_pos += num_bits
        return bits

    def peek(self, num_bits):
        """Legge `num_bits` bit dallo stream senza avanzare il puntatore."""
        self._fill_buffer(num_bits)
        if self.buffer_len < num_bits:
            # Restituisci tutti i bit rimanenti senza sollevare un'eccezione
            num_bits = self.buffer_len
            #~ raise EOFError("Fine del flusso di dati")
        return self.buffer & ((1 << num_bits) - 1)

    def seek(self, bit_pos):
        """Sposta il puntatore a `bit_pos` bit dall'inizio del flusso."""
        byte_pos = bit_pos // 8
        bit_offset = bit_pos % 8
        self.stream.seek(byte_pos)
        self.buffer = 0
        self.buffer_len = 0
        self.bit_pos = byte_pos * 8
        if bit_offset > 0:
            self.read(bit_offset)

    # ----- Metodi per la scrittura -----
    def write(self, value, num_bits):
        """Scrive `num_bits` bit del valore `value` nello stream in ordine Little Endian."""
        for i in range(num_bits):
            bit = (value >> i) & 1
            self.buffer |= (bit << self.buffer_len)
            self.buffer_len += 1
            self.bit_pos += 1
            if self.buffer_len == 8:
                self.stream.write(bytes([self.buffer]))
                self.buffer = 0
                self.buffer_len = 0

    def extend(self, s):
        """Estende il buffer aggiungendo una sequenza di byte `s`."""
        self.flush()
        self.stream.write(s)
        self.bit_pos += 8 * len(s)

    def flush(self):
        """Scrive i bit rimanenti nel buffer, riempiendo con zeri se necessario."""
        if self.buffer_len > 0:
            self.stream.write(bytes([self.buffer]))
            self.buffer = 0
            self.buffer_len = 0

    # ----- Metodi comuni -----
    def tell(self):
        """Ritorna la posizione corrente in bit."""
        return self.bit_pos

    def close(self):
        """Chiude lo stream."""
        if self.mode == 'w':
            self.flush()
        # Non chiudiamo lo stream fornito dall'esterno


def open(s, mode='r'):
    if isinstance(s, bytes) or isinstance(s, bytearray) :
        s = io.BytesIO(s)
        return BitStream(s)
    else:
        raise BitIOException('Bad mode')
