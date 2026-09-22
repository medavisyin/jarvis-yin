package com.jarvis.ir.explain

object GlossMirrors {
    fun url(slug: String): String? = when (slug) {
        "qwen3-0.6" ->
            "https://hf-mirror.com/Cactus-Compute/Qwen3-0.6B/resolve/be1f174031d092bee3db5f4ef169f1d9a0c3d750/weights/qwen3-0.6b.zip"
        "qwen3-1.7" ->
            "https://hf-mirror.com/Cactus-Compute/Qwen3-1.7B/resolve/fafba006c8afe222ec138e85148ae207985f6ab3/weights/qwen3-1.7b-int4.zip"
        else -> null
    }
}
