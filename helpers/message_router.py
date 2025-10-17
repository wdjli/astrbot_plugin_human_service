"""
消息路由器
负责处理消息转发和路由逻辑
"""
from datetime import datetime
from .blacklist_formatter import BlacklistFormatter


class MessageRouter:
    """消息路由器"""
    
    def __init__(self, plugin):
        """
        初始化消息路由器
        
        Args:
            plugin: 主插件实例
        """
        self.plugin = plugin
    
    async def handle_blacklist_view_selection(self, event, sender_id: str, message_text: str):
        """
        处理查看黑名单时的客服选择
        
        Yields:
            event结果
        """
        if sender_id not in self.plugin.blacklist_view_selection:
            return
        
        if not message_text.isdigit():
            yield event.plain_result("⚠ 请输入数字进行选择")
            return
        
        choice = int(message_text)
        
        if choice == 0:
            del self.plugin.blacklist_view_selection[sender_id]
            yield event.plain_result("已取消查看")
            return
        
        if not (1 <= choice <= len(self.plugin.servicers_id)):
            yield event.plain_result(f"⚠ 无效的选择，请输入 1-{len(self.plugin.servicers_id)} 或 0 取消")
            return
        
        # 选择了有效的客服
        selected_servicer_id = self.plugin.servicers_id[choice - 1]
        selected_servicer_name = self.plugin.get_servicer_name(selected_servicer_id)
        
        del self.plugin.blacklist_view_selection[sender_id]
        
        # 获取该客服的黑名单
        blacklist = self.plugin.blacklist_manager.get_blacklist(selected_servicer_id)
        
        if not blacklist:
            yield event.plain_result(f"✅ 客服【{selected_servicer_name}】的黑名单为空")
            return
        
        # 使用BlacklistFormatter格式化
        blacklist_text = await BlacklistFormatter.format_blacklist(
            blacklist, event, f"📋 客服【{selected_servicer_name}】的黑名单"
        )
        
        if blacklist_text:
            yield event.plain_result(blacklist_text)
    
    async def route_servicer_to_user(self, event, sender_id: str) -> bool:
        """
        路由客服消息到用户
        
        Returns:
            bool: 是否处理了消息
        """
        # 客服 → 用户 (仅私聊生效)
        if not (sender_id in self.plugin.servicers_id and event.is_private_chat()):
            return False
        
        if event.message_str in ("接入对话", "结束对话", "拒绝接入", "导出记录", "翻译测试", "查看黑名单", "拉黑", "取消拉黑", "kfhelp"):
            return False
        
        for user_id, session in self.plugin.session_map.items():
            if session["servicer_id"] == sender_id and session["status"] == "connected":
                # 记录聊天内容
                if self.plugin.enable_chat_history and user_id in self.plugin.chat_history:
                    servicer_name = self.plugin.get_servicer_name(sender_id)
                    self.plugin.chat_history[user_id].append({
                        "sender_id": sender_id,
                        "name": f"客服【{servicer_name}】",
                        "message": event.message_str,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                
                await self.plugin.send_ob(
                    event,
                    group_id=session["group_id"],
                    user_id=user_id,
                    add_prefix=True,
                    is_from_servicer=True,
                )
                event.stop_event()
                return True
        
        return False
    
    async def route_user_to_servicer(self, event, sender_id: str) -> bool:
        """
        路由用户消息到客服
        
        Returns:
            bool: 是否处理了消息
        """
        session = self.plugin.session_map.get(sender_id)
        if not session:
            return False
        
        if session["status"] == "connected":
            # 记录聊天内容
            if self.plugin.enable_chat_history and sender_id in self.plugin.chat_history:
                self.plugin.chat_history[sender_id].append({
                    "sender_id": sender_id,
                    "name": event.get_sender_name(),
                    "message": event.message_str,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            
            await self.plugin.send_ob(
                event,
                user_id=session["servicer_id"],
                add_prefix=False,
                is_from_servicer=False,
            )
            event.stop_event()
            return True
        
        return False

