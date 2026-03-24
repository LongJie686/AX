import re
import logging

logger = logging.getLogger(__name__)


def translate_text(text: str) -> str:
    """将英文文本翻译为中文，保留 @mentions 和 URLs"""
    if not text or not text.strip():
        return text

    # 检测是否已经是中文为主
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    if chinese_chars > len(text) * 0.3:
        return text

    # 保护 @mentions 和 URLs
    placeholders = {}
    counter = [0]

    def replace_with_placeholder(match):
        key = f"__PH{counter[0]}__"
        placeholders[key] = match.group(0)
        counter[0] += 1
        return key

    processed = re.sub(r'@\w+', replace_with_placeholder, text)
    processed = re.sub(r'https?://\S+', replace_with_placeholder, processed)
    processed = re.sub(r'#\w+', replace_with_placeholder, processed)

    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source='auto', target='zh-CN').translate(processed)
        if not translated:
            return text
    except Exception as e:
        logger.warning(f"翻译失败，返回原文: {e}")
        return text

    # 还原占位符
    for key, value in placeholders.items():
        translated = translated.replace(key, value)

    return translated
