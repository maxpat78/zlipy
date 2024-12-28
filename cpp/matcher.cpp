#define PY_SSIZE_T_CLEAN
#include <Python.h>

// Richiede C++17 o superiore
#include <iostream>
#include <fstream>
#include <string>
#include <unordered_map>
#include <variant>
#include <vector>
#include <map>
#include <deque>
#include <utility>
#include <algorithm>

// Richiede C++17 o superiore
//static_assert(__cplusplus >= 201703L, "Questo codice richiede C++17 o superiore");

// lunghezza minima del match valido (Deflate)
#define MIN_MATCH 3
// lunghezza massima del match valido (Deflate)
#define MAX_MATCH 258
// offset massimo del match (Deflate)
#define MAX_OFFSET 32768
// dimensione della finestra di ricerca (Deflate)
#define WINDOW_SIZE 32768
// byte successivi testati per un match prima di emettere quello corrente
#define MAX_LAZY 1

using namespace std;
using Match = pair<uint16_t, uint16_t>; // (lunghezza, offset)
using Matches = variant<uint8_t, Match>; // sequenza di byte o Match
using Dictionary = unordered_map<uint32_t, deque<uint32_t>>;

// simboli di lunghezza (3..258) del Match Deflate
static const uint16_t lengthCodes[] = {
        257, 258, 259, 260, 261, 262, 263, 264, 265, 265, 266, 266, 267, 267, 268, 268,
        269, 269, 269, 269, 270, 270, 270, 270, 271, 271, 271, 271, 272, 272, 272, 272,
        273, 273, 273, 273, 273, 273, 273, 273, 274, 274, 274, 274, 274, 274, 274, 274,
        275, 275, 275, 275, 275, 275, 275, 275, 276, 276, 276, 276, 276, 276, 276, 276,
        277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277, 277,
        278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278, 278,
        279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279, 279,
        280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280, 280,
        281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281,
        281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281, 281,
        282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282,
        282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282, 282,
        283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283,
        283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283, 283,
        284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284,
        284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 284, 285 };

// ordine di grandezza dei simboli di distanza (1..32768)
static const uint16_t distanceBases[30] = {
    1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129,
    193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577 };

// configurazione basata sui livelli di compressione 0-9 (cryptopp, zlib)
static const unsigned int configurationTable[10][4] = {
    /*      good lazy nice chain */
    /* 0 */ {0,    0,  0,    0},  /* store only */
    /* 1 */ {4,    3,  8,    4},  /* maximum speed, no lazy matches */
    /* 2 */ {4,    3, 16,    8},
    /* 3 */ {4,    3, 32,   32},
    /* 4 */ {4,    4, 16,   16},  /* lazy matches */
    /* 5 */ {8,   16, 32,   32},
    /* 6 */ {8,   16, 128, 128},
    /* 7 */ {8,   32, 128, 256},
    /* 8 */ {32, 128, 258, 1024},
    /* 9 */ {32, 258, 258, 4096} }; /* maximum compression */

class Matcher {
public:
    // colleziona le frequenze dei simboli per byte e lunghezze 
    //map<uint16_t, uint32_t> freq_lit;
    uint32_t freq_lit[286];
    // colleziona le frequenze dei simboli per le distanze
    //map<uint16_t, uint32_t> freq_dist;
    uint32_t freq_dist[30];

    Matcher(uint32_t level = 9, uint32_t window_size = WINDOW_SIZE) {
        this->level = level;
        this->window_size = window_size;
        this->good_match = configurationTable[level][0];
        this->lazy_bytes = configurationTable[level][1];
        this->nice_match = configurationTable[level][2];
        this->max_offsets = configurationTable[level][3];
        clear();
    }

    void clear() {
        dictionary.clear();
        //freq_lit.clear();
        memset(freq_lit, 0, sizeof(freq_lit));
        //freq_dist.clear();
        memset(freq_dist, 0, sizeof(freq_dist));
        freq_lit[256]++; // simbolo di fine blocco
        this->max_symbols = 1 << (this->level + 6);
    }

    uint32_t find_matches(uint8_t* s, uint32_t i, uint32_t limit, vector<Matches>& output) {
        clear();

        uint32_t start=i;
        while (i < limit) {
            Match bm = Match(0, 0); // Best Match
            int lazy_offset = 0;
            // cerca, in modo lazy, il miglior Match
            // prova dal byte seguente SOLO SE il Match è più corto di lazy_bytes
            for (uint16_t r = 0; r <= MAX_LAZY && bm.first < lazy_bytes; r++) {
                Match m = Match(0, 0);
                find_next(s, i + r, limit, m);
                // se non c'è Match sul primo byte, interrompe
                // altrimenti, ne cerca uno migliore fino a MAX_LAZY byte successivi
                if (!r && !m.first) break;
                // se il match corrente è migliore
                if (m.first > bm.first) {
                    // ignora i Match di 3 distanti (zlib)
                    if (m.first == 3 && m.second > 4096) continue;
                    lazy_offset = r;
                    bm = m;
                }
                // interrompe se è maggiore di un match buono
                if (m.first > good_match) break;
            }

            // emette il Match o il byte
            if (bm.first) {
                // registra le key nell'area del Match
                insert_keys(s, i, bm.first);
                // se il Match è su posizioni successive, registra i byte intermedi
                while (lazy_offset-- > 0) {
                    output.push_back(s[i]);
                    freq_lit[s[i]]++;
                    max_symbols--;
                    i++;
                }
                output.push_back(bm);
                max_symbols--;
                // avanza oltre il Match
                i += bm.first;
                // aumenta la frequenza del simbolo di lunghezza del Match
                freq_lit[lengthCodes[bm.first - 3]]++;
                // aumenta la frequenza del simbolo di distanza del Match
                uint16_t distanceCode = upper_bound(distanceBases, distanceBases + 30, bm.second) - distanceBases - 1;
                freq_dist[distanceCode]++;
            }
            else {
                // registra la key di 3 byte sotto forma di intero
                uint8_t* p = s + i;
                uint32_t key = p[0] << 16 | p[1] << 8 | p[2];
                deque<uint32_t>& D = dictionary[key];
#ifdef POP_IF_LONGER
                if (D.size() > max_offsets) {
                    D.pop_front();
                }
#endif
                D.push_back(i);
                // emette il byte corrente
                output.push_back(s[i]);
                // ne aumenta la frequenza
                freq_lit[s[i]]++;
                max_symbols--;
                i++;
            }
            if (max_symbols <= 0) break;
            //if ((i-start) >= window_size) break;
        }
        return i;
    }

private:
    int max_symbols; // massimo numero di elementi (literal o match) nel buffer di output
    uint32_t level;
    uint32_t window_size;
    uint32_t max_offsets;
    uint32_t good_match;
    uint32_t nice_match;
    uint16_t lazy_bytes;

    // registra la posizione di ogni sequenza di 3 byte incontrata nel buffer
    Dictionary dictionary;

    __inline void find_next(uint8_t* s, uint32_t i, uint32_t limit, Match& match) {
        uint8_t* p = s + i;
        uint16_t best_length = 0, best_offset = 0;

        // crea una chiave uint32_t dai 3 byte correnti
        uint32_t key = p[0] << 16 | p[1] << 8 | p[2];

        // se è registrata
        if (dictionary.find(key) != dictionary.end()) {
            // recupera la lista di posizioni
            // ?: limitare le posizioni esaminate?
            auto& positions = dictionary[key];
            // per ogni posizione, dalla più vicina
            for (auto pos = positions.rbegin(); pos != positions.rend(); pos++) {
                uint32_t j = *pos;
                uint32_t k = i;
                uint32_t moffset = i - j;
                // esce se raggiunge le distanze oltre window_size
                if (moffset > window_size) break;
                uint16_t mlength = 0;
                // cerca la lunghezza del Match
                while (k < limit && mlength < MAX_MATCH && s[j++] == s[k++])
                    mlength++;
                // esclude i match più corti del minimo
                if (mlength < MIN_MATCH) continue;
                // Match buono: lo ritorna direttamente
                if (mlength > nice_match) {
                    match.first = mlength;
                    match.second = moffset;
                    return;
                }
                // registra il miglior Match provvisorio
                if (mlength > best_length) {
                    best_length = mlength;
                    best_offset = moffset;
                }
            }
            // ritorna il miglior match trovato per la posizione
            match.first = best_length;
            match.second = best_offset;
            return;
        }
    }

    void insert_keys(uint8_t* s, uint32_t i, uint32_t max_size) {
        uint32_t END = i + max_size;
        uint8_t* p = s + i;
        while (i < END) {
            uint32_t key = p[0] << 16 | p[1] << 8 | p[2];
            deque<uint32_t>& D = dictionary[key];
#ifdef POP_IF_LONGER
            if (D.size() > max_offsets) {
                D.pop_front();
            }
#endif
            D.push_back(i);
            i++; p++;
        }
    }
};



// Definizione della classe Python Matcher
typedef struct {
    PyObject_HEAD
    Matcher* matcher;
} PyMatcher;

// Metodo __init__
static int PyMatcher_init(PyMatcher* self, PyObject* args, PyObject* kwargs) {
    uint32_t window_size = WINDOW_SIZE;
    uint32_t level = 9;

    if (!PyArg_ParseTuple(args, "|II", &level, &window_size))
        return -1;

    self->matcher = new Matcher(level, window_size);
    return 0;
}

// Metodo get_freqs
static PyObject* PyMatcher_get_freqs(PyMatcher* self) {
    PyObject* d1 = PyDict_New();
    if (!d1) {
        return PyErr_NoMemory();
    }

    for (int i=0; i < 286; i++) {
        PyObject* k = PyLong_FromLong(i);
        PyObject* v = PyLong_FromLong(self->matcher->freq_lit[i]);
        PyDict_SetItem(d1, k, v);
    }
    //~ for (auto& ob : self->matcher->freq_lit) {
        //~ PyObject* k = PyLong_FromLong(ob.first);
        //~ PyObject* v = PyLong_FromLong(ob.second);
        //~ PyDict_SetItem(d1, k, v);
    //~ }

    PyObject* d2 = PyDict_New();
    if (!d2) {
        Py_DECREF(d1);
        return PyErr_NoMemory();
    }

    for (int i=0; i < 30; i++) {
        PyObject* k = PyLong_FromLong(i);
        PyObject* v = PyLong_FromLong(self->matcher->freq_dist[i]);
        PyDict_SetItem(d2, k, v);
    }
    //~ for (auto& ob : self->matcher->freq_dist) {
        //~ PyObject* k = PyLong_FromLong(ob.first);
        //~ PyObject* v = PyLong_FromLong(ob.second);
        //~ PyDict_SetItem(d2, k, v);
    //~ }

    PyObject* result = PyTuple_Pack(2, d1, d2);

    Py_DECREF(d1);
    Py_DECREF(d2);

    if (!result) {
        return PyErr_NoMemory();
    }

    return result;
}

// Metodo find_matches
static PyObject* PyMatcher_find_matches(PyMatcher* self, PyObject* args) {
    Py_buffer buffer;
    uint32_t index;
    uint32_t limit;
    PyObject* output_list;

    if (!PyArg_ParseTuple(args, "y*IIO", &buffer, &index, &limit, &output_list)) {
        return nullptr;
    }

    if (!PyList_Check(output_list)) {
        PyErr_SetString(PyExc_TypeError, "Output must be a list");
        PyBuffer_Release(&buffer);
        return nullptr;
    }

    uint8_t* data = (uint8_t*)buffer.buf;
    vector<Matches> output;

    index = self->matcher->find_matches(data, index, limit, output);

    //~ PyObject* print_func = PyObject_GetAttrString(PyImport_ImportModule("builtins"), "print");

    for (const auto& item : output) {
        if (holds_alternative<uint8_t>(item)) {
            // Aggiunge il byte effettivo alla lista Python
            uint8_t byte = get<uint8_t>(item);
            PyList_Append(output_list, PyLong_FromUnsignedLong(byte));
        } else {
            // Aggiunge una tupla (lunghezza, offset) alla lista Python
            auto match = get<Match>(item);
            PyList_Append(output_list, Py_BuildValue("(HH)", match.first, match.second));
        
            //~ PyObject* py_message = PyUnicode_FromFormat("[DEBUG] appended (%d, %d)", match.first, match.second);
            //~ PyObject_CallFunctionObjArgs(print_func, py_message, nullptr);
            //~ Py_DECREF(py_message);
        }
    }

    //~ Py_DECREF(print_func);

    PyBuffer_Release(&buffer);
    return Py_BuildValue("L", index);
}

// Metodo __dealloc__
static void PyMatcher_dealloc(PyMatcher* self) {
    delete self->matcher;
    Py_TYPE(self)->tp_free((PyObject*)self);
}

// Definizione dei metodi della classe
static PyMethodDef PyMatcher_methods[] = {
    {"find_matches", (PyCFunction)PyMatcher_find_matches, METH_VARARGS, "Find LZ77-style matches for Deflate in the input buffer"},
    {"get_freqs", (PyCFunction)PyMatcher_get_freqs, METH_NOARGS, "Retrieve Literals/Lengths and Distances frequencies"},
    {nullptr}
};

// Definizione della classe Matcher
static PyTypeObject PyMatcherType = {
    PyVarObject_HEAD_INIT(nullptr, 0)
    "matcher.Matcher",              // tp_name: Nome della classe
    sizeof(PyMatcher),              // tp_basicsize: Dimensione dell'oggetto
    0,                              // tp_itemsize: Offset per oggetti variabili
    (destructor)PyMatcher_dealloc,  // tp_dealloc: Deallocatore
    0,                              // tp_vectorcall_offset
    0,                              // tp_getattr
    0,                              // tp_setattr
    0,                              // tp_as_async
    0,                              // tp_repr
    0,                              // tp_as_number
    0,                              // tp_as_sequence
    0,                              // tp_as_mapping
    0,                              // tp_hash
    0,                              // tp_call
    0,                              // tp_str
    0,                              // tp_getattro
    0,                              // tp_setattro
    0,                              // tp_as_buffer
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, // tp_flags
    "Matcher objects",              // tp_doc: Documentazione
    0,                              // tp_traverse
    0,                              // tp_clear
    0,                              // tp_richcompare
    0,                              // tp_weaklistoffset
    0,                              // tp_iter
    0,                              // tp_iternext
    PyMatcher_methods,              // tp_methods: Metodi della classe
    0,                              // tp_members
    0,                              // tp_getset
    0,                              // tp_base
    0,                              // tp_dict
    0,                              // tp_descr_get
    0,                              // tp_descr_set
    0,                              // tp_dictoffset
    (initproc)PyMatcher_init,       // tp_init: Metodo __init__
    0,                              // tp_alloc
    PyType_GenericNew,              // tp_new: Metodo __new__
    0,                              // tp_free
    0,                              // tp_is_gc
    0,                              // tp_bases
    0,                              // tp_mro
    0,                              // tp_cache
    0,                              // tp_subclasses
    0                               // tp_weaklist
};

// Modulo
static PyModuleDef matcher_module = {
    PyModuleDef_HEAD_INIT,
    "matcher",
    "A module for finding LZ77 matches for Deflate compression algorithm",
    -1,
    nullptr
};

PyMODINIT_FUNC PyInit_matcher(void) {
    if (PyType_Ready(&PyMatcherType) < 0)
        return nullptr;

    PyObject* m = PyModule_Create(&matcher_module);
    if (!m) return nullptr;

    Py_INCREF(&PyMatcherType);
    PyModule_AddObject(m, "Matcher", (PyObject*)&PyMatcherType);
    return m;
}
