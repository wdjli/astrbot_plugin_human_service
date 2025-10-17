"""
翻译服务
负责调用OpenAI API进行文本翻译
"""
from typing import Optional


class TranslationService:
    """翻译服务"""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        """
        初始化翻译服务
        
        Args:
            api_key: OpenAI API Key
            base_url: API基础URL
            model: 使用的模型
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    
    async def translate(self, text: str, target_language: str) -> Optional[str]:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            target_language: 目标语言
            
        Returns:
            Optional[str]: 翻译结果，失败返回None
        """
        if not self.api_key:
            return None
        
        try:
            import aiohttp
            
            prompt = f"请将以下文本翻译成{target_language}，只返回翻译结果，不要有任何其他内容：\n\n{text}"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一个专业的翻译助手，只返回翻译结果，不添加任何解释或额外内容。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1000
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        translation = result["choices"][0]["message"]["content"].strip()
                        return translation
                    else:
                        print(f"[翻译失败] API返回错误: {response.status}")
                        return None
        except Exception as e:
            print(f"[翻译失败] {e}")
            return None
    
    def is_available(self) -> bool:
        """
        检查翻译服务是否可用
        
        Returns:
            bool: 是否可用
        """
        return bool(self.api_key)

