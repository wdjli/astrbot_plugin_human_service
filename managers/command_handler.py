"""
命令处理器
负责处理复杂的命令逻辑
"""
from typing import List, Dict, Optional


class CommandHandler:
    """命令处理器 - 处理复杂的命令逻辑"""
    
    def __init__(self, plugin):
        """
        初始化命令处理器
        
        Args:
            plugin: 主插件实例
        """
        self.plugin = plugin
    
    async def handle_transfer_to_human(self, event, sender_id: str, send_name: str, group_id: str):
        """
        处理转人工命令的核心逻辑
        
        Returns:
            tuple: (success, message, data)
        """
        # 检查黑名单
        if self.plugin.is_user_blacklisted(sender_id):
            return False, "⚠ 您已被加入黑名单，无法使用人工客服", None
        
        # 检查是否已在会话中
        if self.plugin.session_manager.has_session(sender_id):
            return False, "⚠ 您已在等待接入或正在对话", None
        
        # 检查是否在选择客服
        if sender_id in self.plugin.session_manager.selection_map:
            return False, "⚠ 您正在选择客服，请先完成选择", None
        
        # 检查是否已在队列中
        for servicer_id in self.plugin.queue_manager.servicer_queue:
            position = self.plugin.queue_manager.get_position(servicer_id, sender_id)
            if position > 0:
                return False, f"⚠ 您已在排队中，当前队列位置：第 {position} 位", None
        
        return True, None, None
    
    def get_available_servicers(self, sender_id: str) -> List[str]:
        """
        获取用户可选的客服列表（过滤黑名单）
        
        Args:
            sender_id: 用户ID
            
        Returns:
            List[str]: 可用客服ID列表
        """
        available = []
        for sid in self.plugin.servicers_id:
            # 如果不共用黑名单，检查用户是否被该客服拉黑
            if not self.plugin.share_blacklist and self.plugin.is_user_blacklisted(sender_id, sid):
                continue
            available.append(sid)
        return available
    
    def format_servicer_list(self, servicer_ids: List[str]) -> tuple:
        """
        格式化客服列表显示
        
        Args:
            servicer_ids: 客服ID列表
            
        Returns:
            tuple: (list_items, available_servicers)
        """
        servicer_list_items = []
        available_servicers = []
        
        for idx, sid in enumerate(servicer_ids):
            servicer_name = self.plugin.get_servicer_name(sid)
            status = "🔴 忙碌中" if self.plugin.is_servicer_busy(sid) else "🟢 空闲"
            queue_count = self.plugin.queue_manager.get_size(sid)
            queue_info = f"（排队 {queue_count} 人）" if queue_count > 0 else ""
            
            list_idx = len(servicer_list_items) + 1
            servicer_list_items.append(f"{list_idx}. {servicer_name} {status}{queue_info}")
            available_servicers.append(sid)
        
        return servicer_list_items, available_servicers
    
    async def handle_servicer_selection(self, event, sender_id: str, choice: int, selection: Dict):
        """
        处理客服选择
        
        Args:
            event: 事件对象
            sender_id: 用户ID
            choice: 选择的序号
            selection: 选择状态数据
            
        Returns:
            tuple: (success, should_stop)
        """
        available_servicers = selection.get("available_servicers", self.plugin.servicers_id)
        
        if not (1 <= choice <= len(available_servicers)):
            await event.plain_result(f"⚠ 无效的选择，请输入 1-{len(available_servicers)} 或 0 取消")
            return False, True
        
        # 选择了有效的客服
        selected_servicer_id = available_servicers[choice - 1]
        selected_servicer_name = self.plugin.get_servicer_name(selected_servicer_id)
        
        # 删除选择状态
        del self.plugin.session_manager.selection_map[sender_id]
        
        return await self._handle_selected_servicer(
            event, sender_id, selection, 
            selected_servicer_id, selected_servicer_name, choice
        )
    
    async def _handle_selected_servicer(self, event, sender_id: str, selection: Dict,
                                        selected_servicer_id: str, selected_servicer_name: str, choice: int):
        """处理已选择的客服"""
        # 检查客服是否忙碌
        if self.plugin.is_servicer_busy(selected_servicer_id):
            # 客服忙碌，加入队列
            self.plugin.add_to_queue(selected_servicer_id, sender_id, selection['name'], selection["group_id"])
            position = self.plugin.get_queue_position(selected_servicer_id, sender_id)
            queue_count = self.plugin.queue_manager.get_size(selected_servicer_id)
            
            await event.plain_result(
                f"客服【{selected_servicer_name}】正在服务中🔴\n"
                f"您已加入等待队列，当前排队人数：{queue_count}\n"
                f"您的位置：第 {position} 位\n\n"
                f"💡 使用 /取消排队 可退出队列"
            )
            
            # 通知客服有人排队
            await self.plugin.send(
                event,
                message=f"📋 {selection['name']}({sender_id}) 已加入排队（指定您），当前队列：{queue_count} 人",
                user_id=selected_servicer_id,
            )
        else:
            # 客服空闲，创建会话
            self.plugin.session_manager.create_session(sender_id, {
                "servicer_id": "",
                "status": "waiting",
                "group_id": selection["group_id"],
                "selected_servicer": selected_servicer_id
            })
            
            # 通知用户和客服
            await event.plain_result(f"正在等待客服【{selected_servicer_name}】接入...")
            await self.plugin.send(
                event,
                message=f"{selection['name']}({sender_id}) 请求转人工（指定您）",
                user_id=selected_servicer_id,
            )
        
        return True, True
    
    async def prepare_next_user_from_queue(self, event, servicer_id: str, context_message: str = ""):
        """
        从队列准备下一位用户
        
        Args:
            event: 事件对象
            servicer_id: 客服ID
            context_message: 上下文消息（如"对话已结束"）
            
        Returns:
            bool: 是否有下一位用户
        """
        next_user = self.plugin.queue_manager.pop_next(servicer_id)
        
        if not next_user:
            return False
        
        next_user_id = next_user["user_id"]
        next_user_name = next_user["name"]
        next_group_id = next_user["group_id"]
        
        # 创建新的会话（等待接入状态）
        self.plugin.session_manager.create_session(next_user_id, {
            "servicer_id": "",
            "status": "waiting",
            "group_id": next_group_id,
            "selected_servicer": servicer_id
        })
        
        # 通知用户
        await self.plugin.send(
            event,
            message=f"⏰ 轮到您了！客服正在准备接入您的对话...\n客服可以使用 /接入对话 命令开始服务",
            group_id=next_group_id,
            user_id=next_user_id,
        )
        
        # 通知客服
        remaining_queue = self.plugin.queue_manager.get_size(servicer_id)
        queue_info = f"（队列剩余 {remaining_queue} 人）" if remaining_queue > 0 else "（队列已清空）"
        
        context_info = f"{context_message}\n" if context_message else ""
        
        await self.plugin.send(
            event,
            message=(
                f"{context_info}"
                f"📋 队列中的下一位用户已准备就绪：\n"
                f"用户：{next_user_name}({next_user_id})\n"
                f"请使用 /接入对话 命令（回复用户消息）开始服务\n"
                f"{queue_info}"
            ),
            user_id=servicer_id,
        )
        
        return True

