"""
聊天记录导出器
负责导出和格式化聊天记录
"""
from typing import List, Dict


class ChatHistoryExporter:
    """聊天记录导出器"""
    
    @staticmethod
    async def export_as_forward(history: List[Dict], event, sender_id: str) -> tuple:
        """
        以合并转发格式导出聊天记录
        
        Args:
            history: 聊天记录列表
            event: 事件对象
            sender_id: 发送者ID
            
        Returns:
            tuple: (success: bool, message: str)
        """
        if not history:
            return False, "⚠ 暂无聊天记录"
        
        # 生成QQ聊天记录格式的转发消息
        forward_messages = []
        for record in history:
            forward_messages.append({
                "type": "node",
                "data": {
                    "name": record["name"],
                    "uin": record["sender_id"],
                    "content": record["message"]
                }
            })
        
        # 发送合并转发消息
        try:
            await event.bot.send_private_forward_msg(
                user_id=int(sender_id),
                messages=forward_messages
            )
            return True, f"✅ 已导出聊天记录（共 {len(history)} 条消息）"
        except Exception as e:
            # 如果合并转发失败，返回None让调用者使用文本格式
            return False, None
    
    @staticmethod
    def export_as_text(history: List[Dict]) -> str:
        """
        以文本格式导出聊天记录
        
        Args:
            history: 聊天记录列表
            
        Returns:
            str: 格式化的文本记录
        """
        text_history = f"📝 聊天记录（共 {len(history)} 条）\n" + "="*30 + "\n\n"
        
        for record in history:
            text_history += f"[{record['time']}] {record['name']}:\n{record['message']}\n\n"
        
        return text_history

