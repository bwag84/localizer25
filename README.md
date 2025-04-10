A project to leverage the power of LLMs for localizing keywords.


The goal is to create an agent, or a RAG pipeline, that localizes keywords reliably. Reliable meaning that the input and output are always the same: a CSV with categorized keywords and backtranslations. Reliable as in: the localization is accurate. It is a keyword, not a translation.

### Localization
Localization is distinctly different from translation. Translation is literla, word for word. Keyword localization however is about taking a search intention, and then expressing that search intention into another language. 

Translating SEO keywords is like giving your foreign friend a direct word-for-word conversion. Localizing, however, is like helping your friend understand and use local slang and cultural references to fit in.

And example:

Translation:
translated_keyword = "best pizza"
translated_keyword_nl = "beste pizza"

Localization
localized_keyword_nl = "lekkerste pizza"

# Release notes

- v0.1 beta is released
- Localizes keywords using the Claude API
- Contains major languages for APAC and EU
- Upload with CSV
- Enter manually
- Write to database 

# Upcoming features

- All global languages
- Set target language to multiple languages for bulk localization
- Refined parameters