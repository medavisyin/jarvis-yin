#include "IRZip.h"

#include <stdlib.h>
#include <string.h>
#include <zlib.h>

static uint8_t *grow(uint8_t *buf, size_t *cap) {
    size_t next = (*cap < 65536) ? 65536 : (*cap * 2);
    uint8_t *out = (uint8_t *)realloc(buf, next);
    if (out == NULL) return NULL;
    *cap = next;
    return out;
}

uint8_t *ir_inflate_raw(const uint8_t *src, size_t src_len, size_t *out_len) {
    z_stream strm;
    uint8_t *out;
    size_t cap;
    int ret;

    if (out_len == NULL || (src == NULL && src_len != 0) || src_len > 0xffffffffu) return NULL;
    memset(&strm, 0, sizeof(strm));
    if (inflateInit2(&strm, -MAX_WBITS) != Z_OK) return NULL;

    cap = src_len * 3 + 65536;
    if (cap < 65536) cap = 65536;
    out = (uint8_t *)malloc(cap);
    if (out == NULL) {
        inflateEnd(&strm);
        return NULL;
    }
    strm.next_in = (Bytef *)src;
    strm.avail_in = (uInt)src_len;

    for (;;) {
        size_t room;
        if (strm.total_out + 65536 > cap) {
            uint8_t *bigger = grow(out, &cap);
            if (bigger == NULL) {
                free(out);
                inflateEnd(&strm);
                return NULL;
            }
            out = bigger;
        }
        room = cap - strm.total_out;
        if (room > 1048576u) room = 1048576u;
        strm.next_out = out + strm.total_out;
        strm.avail_out = (uInt)room;
        ret = inflate(&strm, Z_NO_FLUSH);
        if (ret == Z_STREAM_END) break;
        if (ret == Z_OK) continue;
        if (ret == Z_BUF_ERROR && strm.avail_out == 0) continue;
        free(out);
        inflateEnd(&strm);
        return NULL;
    }
    inflateEnd(&strm);
    *out_len = strm.total_out;
    return out;
}

uint8_t *ir_deflate_raw(const uint8_t *src, size_t src_len, size_t *out_len) {
    z_stream strm;
    uint8_t *out;
    size_t cap;
    int ret;

    if (out_len == NULL || (src == NULL && src_len != 0) || src_len > 0xffffffffu) return NULL;
    memset(&strm, 0, sizeof(strm));
    if (deflateInit2(&strm, Z_DEFAULT_COMPRESSION, Z_DEFLATED, -MAX_WBITS, 8, Z_DEFAULT_STRATEGY) != Z_OK) {
        return NULL;
    }
    cap = src_len + 128;
    if (cap < 256) cap = 256;
    out = (uint8_t *)malloc(cap);
    if (out == NULL) {
        deflateEnd(&strm);
        return NULL;
    }
    strm.next_in = (Bytef *)src;
    strm.avail_in = (uInt)src_len;
    for (;;) {
        size_t room;
        if (strm.total_out + 128 > cap) {
            uint8_t *bigger = grow(out, &cap);
            if (bigger == NULL) {
                free(out);
                deflateEnd(&strm);
                return NULL;
            }
            out = bigger;
        }
        room = cap - strm.total_out;
        if (room > 1048576u) room = 1048576u;
        strm.next_out = out + strm.total_out;
        strm.avail_out = (uInt)room;
        ret = deflate(&strm, Z_FINISH);
        if (ret == Z_STREAM_END) break;
        if (ret == Z_OK) continue;
        free(out);
        deflateEnd(&strm);
        return NULL;
    }
    deflateEnd(&strm);
    *out_len = strm.total_out;
    return out;
}

void ir_free(void *ptr) {
    free(ptr);
}
