"""
人工客服插件 - 工具函数
提取通用工具函数，提高代码可读性
"""
import time
import random
from typing import Optional


def generate_random_text(chars: str, original_length: int) -> str:
    """生成随机文字（答非所问模式）"""
    if not chars:
        return "..."
    
    char_list = list(chars)
    min_length = max(1, int(original_length * 0.5))
    max_length = max(2, int(original_length * 1.5))
    target_length = random.randint(min_length, max_length)
    
    result = ""
    for _ in range(target_length):
        result += random.choice(char_list)
    
    return result


def extract_text_from_message(ob_message) -> str:
    """从OneBot消息中提取文本内容"""
    if isinstance(ob_message, str):
        return ob_message
    elif isinstance(ob_message, list):
        text = ""
        for segment in ob_message:
            if isinstance(segment, dict) and segment.get("type") == "text":
                text += segment["data"].get("text", "")
        return text
    return ""


def is_pure_text_message(ob_message) -> bool:
    """检查是否为纯文本消息"""
    if isinstance(ob_message, str):
        return True
    elif isinstance(ob_message, list):
        return all(
            isinstance(seg, dict) and seg.get("type") == "text" 
            for seg in ob_message
        )
    return False


def add_prefix_to_message(ob_message, prefix: str):
    """为消息添加前缀"""
    if not prefix:
        return ob_message
    
    if isinstance(ob_message, str):
        return prefix + ob_message
    elif isinstance(ob_message, list) and len(ob_message) > 0:
        if is_pure_text_message(ob_message):
            for segment in ob_message:
                if isinstance(segment, dict) and segment.get("type") == "text":
                    segment["data"]["text"] = prefix + segment["data"]["text"]
                    break
    return ob_message


def add_suffix_to_message(ob_message, suffix: str):
    """为消息添加后缀"""
    if not suffix:
        return ob_message
    
    if isinstance(ob_message, str):
        return ob_message + suffix
    elif isinstance(ob_message, list) and len(ob_message) > 0:
        if is_pure_text_message(ob_message):
            for i in range(len(ob_message) - 1, -1, -1):
                segment = ob_message[i]
                if isinstance(segment, dict) and segment.get("type") == "text":
                    segment["data"]["text"] = segment["data"]["text"] + suffix
                    break
    return ob_message


def replace_with_random_text(ob_message, random_chars: str):
    """将消息替换为随机文字"""
    if isinstance(ob_message, str):
        original_length = len(ob_message)
        return generate_random_text(random_chars, original_length)
    elif isinstance(ob_message, list) and len(ob_message) > 0:
        if is_pure_text_message(ob_message):
            original_text = extract_text_from_message(ob_message)
            if original_text:
                random_text = generate_random_text(random_chars, len(original_text))
                for segment in ob_message:
                    if isinstance(segment, dict) and segment.get("type") == "text":
                        segment["data"]["text"] = random_text
                        return [segment]
    return ob_message

