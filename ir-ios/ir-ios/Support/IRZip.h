#ifndef IRZIP_H
#define IRZIP_H

#include <stddef.h>
#include <stdint.h>

uint8_t *ir_inflate_raw(const uint8_t *src, size_t src_len, size_t *out_len);
uint8_t *ir_deflate_raw(const uint8_t *src, size_t src_len, size_t *out_len);
void ir_free(void *ptr);

#endif
