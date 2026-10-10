"""
输入清洗工具
防止 prompt injection、XSS、恶意输入
"""
import re
import html


class InputSanitizer:
    """输入清洗器"""

    # Prompt injection 常见模式
    PROMPT_INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"disregard\s+(all\s+)?prior\s+instructions",
        r"forget\s+(all\s+)?previous\s+instructions",
        r"you\s+are\s+now\s+",
        r"system\s*:\s*",
        r"assistant\s*:\s*",
        r"human\s*:\s*",
        r"<\s*\|im_start\|>",
        r"<\s*\|im_end\|>",
        r"###\s*instruction",
        r"---\s*system",
    ]

    # 危险字符
    DANGEROUS_CHARS = {
        "\x00": "",  # null byte
        "\x08": "",  # backspace
        "\x0b": " ",  # vertical tab
        "\x0c": " ",  # form feed
    }

    @classmethod
    def sanitize_message(cls, message: str) -> str:
        """清洗用户消息"""
        if not message:
            return ""

        # 1. 去除控制字符
        for char, replacement in cls.DANGEROUS_CHARS.items():
            message = message.replace(char, replacement)

        # 2. 去除零宽字符
        message = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", message)

        # 3. 限制连续换行
        message = re.sub(r"\n{4,}", "\n\n\n", message)

        # 4. 去除首尾空白
        message = message.strip()

        return message

    @classmethod
    def escape_for_prompt(cls, text: str) -> str:
        """转义用户输入，防止 prompt injection"""
        if not text:
            return ""

        # 转义三引号
        text = text.replace('"""', '\\"\\"\\"')

        # 转义 markdown 标题（在每个 # 前加反斜杠）
        text = re.sub(r"^(#{1,6})", lambda m: r"\#" * len(m.group(1)), text, flags=re.MULTILINE)

        # 转义分隔线
        text = re.sub(r"^---+$", "\\-\\-\\-", text, flags=re.MULTILINE)

        # 转义 XML 标签
        text = re.sub(r"<(\w+)>", r"\<\1\>", text)

        return text

    @classmethod
    def detect_prompt_injection(cls, message: str) -> tuple[bool, list[str]]:
        """检测 prompt injection 攻击"""
        detected_patterns = []
        message_lower = message.lower()

        for pattern in cls.PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, message_lower):
                detected_patterns.append(pattern)

        return len(detected_patterns) > 0, detected_patterns

    @classmethod
    def sanitize_session_id(cls, session_id: str) -> str:
        """清洗 session_id"""
        if not session_id:
            return ""
        # 只允许字母数字、连字符、下划线
        return re.sub(r"[^a-zA-Z0-9\-_]", "", session_id)[:64]

    @classmethod
    def validate_message_length(cls, message: str, max_length: int = 2000) -> bool:
        """验证消息长度"""
        return 0 < len(message) <= max_length


def sanitize_input(message: str) -> str:
    """便捷函数：清洗用户输入"""
    return InputSanitizer.sanitize_message(message)


def escape_prompt_input(text: str) -> str:
    """便捷函数：转义 prompt 输入"""
    return InputSanitizer.escape_for_prompt(text)
