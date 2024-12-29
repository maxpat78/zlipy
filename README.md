# zlipy

A Python 3 package to explore Deflate compression (RFC1951) and analyze its compressed bit streams with a zlib fashion.

Inspired by [pyflate](https://github.com/pfalcon/pyflate) and [acefile](https://github.com/droe/acefile) - if decompression is possible, why not?

It implements:
- compression and decompression with Static and Dynamic Huffman trees (or no compression);
- some HC3 LZ77, Deflate-style match finders in pure Python (use PyPy to boost performances) and one in a C++17 module to get reasonable speed;
- Huffman encoder and decoder;
- a bit stream reader and writer;
- minimal ZIP reader and writer classes;
- adler32 and crc32.
