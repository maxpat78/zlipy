# zlipy

A Python 3 package to explore Deflate compression (RFC1951) and analyze its compressed bit streams.

It implements:
- compression and decompression with Static and Dynamic Huffman trees (or no compression);
- Huffman encoder and decoder;
- some HC3 LZ77, Deflate-style match finders in pure Python (use PyPy to boost performances) and one in a C++ module to get reasonable speed;
- a bit stream reader and writer;
- minimal ZIP reader and writer classes.
