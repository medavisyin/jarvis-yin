package com.jarvis.ir.explain

import com.cactus.Cactus
import com.cactus.CompletionOptions
import com.cactus.Message
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class CactusGlossEngine : GlossEngine {
    private var model: Cactus? = null
    private var readySlug: String? = null

    override fun isDownloaded(slug: String): Boolean {
        val folder = ModelFiles.folder(slug)
        return folder.isDirectory && folder.listFiles()?.isNotEmpty() == true
    }

    override suspend fun download(slug: String, onStatus: (String) -> Unit) {
        withContext(Dispatchers.IO) {
            val mirror = GlossMirrors.url(slug) ?: throw IllegalStateException("没有这个模型的下载地址")
            MirrorModelDownload.fetch(slug, mirror, onStatus)
        }
    }

    override suspend fun complete(slug: String, word: String, sentence: String): String {
        if (GlossPrompt.isPhrase(word)) return explainPhrase(slug, word)
        val text = inChinese(
            slug,
            system = "只输出一句中文释义。不要英文，不要举例。",
            prompts = listOf(GlossPrompt.user(word, sentence), GlossPrompt.userRetry(word, sentence)),
            maxTokens = 80,
        )
        return text.ifEmpty { "这个词没解释成中文" }
    }

    override suspend fun translateSentence(slug: String, sentence: String): String {
        val prompts = listOf(
            GlossPrompt.translation(sentence),
            GlossPrompt.translationRetry(sentence),
        )
        for (prompt in prompts) {
            val text = ask(
                slug,
                system = "只写中文。不要写英文。",
                user = prompt,
                maxTokens = 120,
                temperature = 0f,
            )
            val chinese = GlossText.chinese(text)
            if (chinese.isNotEmpty()) return chinese
        }
        return "这句没译成中文"
    }

    private suspend fun explainPhrase(slug: String, phrase: String): String {
        val meaning = inChinese(
            slug,
            system = "只写中文。不要写英文。",
            prompts = listOf(GlossPrompt.phraseMeaning(phrase), GlossPrompt.phraseMeaningRetry(phrase)),
            maxTokens = 80,
        )
        val line = meaning
            .lineSequence()
            .firstOrNull { it.isNotBlank() }
            .orEmpty()
            .removePrefix("词组：")
            .removePrefix("词组:")
            .trim()
        val end = line.indexOf('。')
        val sentence = if (end >= 0) line.substring(0, end + 1) else line
        return sentence.ifEmpty { "这个词组没解释成中文" }
    }

    private suspend fun inChinese(
        slug: String,
        system: String,
        prompts: List<String>,
        maxTokens: Int,
    ): String {
        for (prompt in prompts) {
            val text = ask(slug, system = system, user = prompt, maxTokens = maxTokens, temperature = 0f)
            val chinese = GlossText.chinese(text)
            if (chinese.isNotEmpty()) return chinese
        }
        return ""
    }

    private suspend fun ask(
        slug: String,
        system: String,
        user: String,
        maxTokens: Int,
        emptyFallback: String = "",
        temperature: Float = 0.2f,
    ): String {
        return withContext(Dispatchers.IO) {
            val opened = open(slug)
            val result = opened.complete(
                messages = listOf(Message.system(system), Message.user(user)),
                options = CompletionOptions(temperature = temperature, maxTokens = maxTokens),
            )
            val text = GlossText.sentence(result.text)
            if (text.isNotEmpty()) text else emptyFallback
        }
    }

    private fun open(slug: String): Cactus {
        val current = model
        if (readySlug == slug && current != null) return current
        try {
            current?.close()
            model = null
            readySlug = null
            val created = Cactus.create(ModelFiles.folder(slug).absolutePath)
            model = created
            readySlug = slug
            return created
        } catch (e: Exception) {
            model = null
            readySlug = null
            throw IllegalStateException(
                ModelOpenFailure.message("", e.message),
                e,
            )
        }
    }
}
