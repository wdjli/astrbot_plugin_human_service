import re
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import Reply
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@register(
    "astrbot_plugin_human_service",
    "Zhalslar&dongyue",
    "人工客服插件 - 支持智能排队、时间管理、客服名称和黑名单",
    "1.7.1",
    "https://github.com/Zhalslar/astrbot_plugin_human_service",
)
class HumanServicePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        
        # 客服QQ号列表
        self.servicers_id: list[str] = config.get("servicers_id", [])
        if not self.servicers_id:
            # 默认使用管理员作为客服
            for admin_id in context.get_config()["admins_id"]:
                if admin_id.isdigit():
                    self.servicers_id.append(admin_id)
        
        # 客服名称列表
        servicers_names = config.get("servicers_names", [])
        
        # 客服配置：{qq: name}，将两个列表合并为字典
        self.servicers_config: dict[str, str] = {}
        for i, sid in enumerate(self.servicers_id):
            # 如果有对应的名称就用，否则用QQ号
            if i < len(servicers_names) and servicers_names[i]:
                self.servicers_config[str(sid)] = servicers_names[i]
            else:
                self.servicers_config[str(sid)] = str(sid)
        
        self.enable_servicer_selection = config.get("enable_servicer_selection", True)
        self.enable_chat_history = config.get("enable_chat_history", False)
        self.share_blacklist = config.get("share_blacklist", True)
        self.message_prefix = config.get("message_prefix", "")
        self.message_suffix = config.get("message_suffix", "")
        self.enable_random_reply = config.get("enable_random_reply", False)
        self.random_reply_chars = config.get("random_reply_chars", "哈基米")
        
        # 翻译配置
        self.enable_translation = config.get("enable_translation", False)
        self.translation_main_language = config.get("translation_main_language", "中文")
        self.translation_target_language = config.get("translation_target_language", "英文")
        self.openai_api_key = config.get("openai_api_key", "")
        self.openai_base_url = config.get("openai_base_url", "https://api.openai.com/v1")
        self.openai_model = config.get("openai_model", "gpt-3.5-turbo")
        
        # 时间限制配置（秒）
        self.conversation_timeout = config.get("conversation_timeout", 0)  # 0表示不限制
        self.queue_timeout = config.get("queue_timeout", 0)  # 0表示不限制
        self.timeout_warning_seconds = config.get("timeout_warning_seconds", 120)
        
        self.session_map = {}
        # 用户选择客服的临时状态
        self.selection_map = {}
        # 聊天记录：{user_id: [{"sender": "user/servicer", "name": "xxx", "message": "xxx", "time": "xxx"}]}
        self.chat_history = {}
        # 客服队列：{servicer_id: [{"user_id": "xxx", "name": "xxx", "group_id": "xxx", "time": timestamp}]}
        self.servicer_queue = {sid: [] for sid in self.servicers_id}
        # 对话开始时间记录：{user_id: {"start_time": timestamp, "warned": bool}}
        self.conversation_timers = {}
        # 已发送超时警告的记录
        self.timeout_warnings_sent = set()
        
        # 黑名单
        if self.share_blacklist:
            # 共用黑名单：一个集合
            self.blacklist: set[str] = set()
        else:
            # 独立黑名单：每个客服一个集合 {servicer_id: set(user_ids)}
            self.blacklist_per_servicer: dict[str, set[str]] = {sid: set() for sid in self.servicers_id}
        
        # 查看黑名单时的临时选择状态
        self.blacklist_view_selection: dict[str, dict] = {}
    
    def get_servicer_name(self, servicer_id: str) -> str:
        """获取客服名称，如果没有配置则返回QQ号"""
        return self.servicers_config.get(servicer_id, servicer_id)
    
    def generate_random_text(self, original_length: int) -> str:
        """生成随机文字（答非所问模式）"""
        import random
        
        if not self.random_reply_chars:
            return "..."
        
        # 将配置的文字转换为字符列表
        chars = list(self.random_reply_chars)
        
        # 生成随机长度（原消息长度的50%-150%）
        min_length = max(1, int(original_length * 0.5))
        max_length = max(2, int(original_length * 1.5))
        target_length = random.randint(min_length, max_length)
        
        # 随机组合生成文字
        result = ""
        for _ in range(target_length):
            result += random.choice(chars)
        
        return result
    
    async def translate_text(self, text: str, target_language: str) -> str:
        """使用OpenAI API翻译文本"""
        if not self.enable_translation or not self.openai_api_key:
            return None
        
        try:
            import aiohttp
            
            # 构建翻译提示
            prompt = f"请将以下文本翻译成{target_language}，只返回翻译结果，不要有任何其他内容：\n\n{text}"
            
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.openai_model,
                "messages": [
                    {"role": "system", "content": f"你是一个专业的翻译助手，只返回翻译结果，不添加任何解释或额外内容。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1000
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.openai_base_url}/chat/completions",
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
    
    def is_user_blacklisted(self, user_id: str, servicer_id: str = None) -> bool:
        """检查用户是否在黑名单中"""
        if self.share_blacklist:
            # 共用黑名单
            return user_id in self.blacklist
        else:
            # 独立黑名单
            if servicer_id:
                return user_id in self.blacklist_per_servicer.get(servicer_id, set())
            else:
                # 如果没有指定客服，检查是否在任何客服的黑名单中
                return any(user_id in blacklist for blacklist in self.blacklist_per_servicer.values())
    
    def add_to_blacklist(self, user_id: str, servicer_id: str):
        """将用户添加到黑名单"""
        if self.share_blacklist:
            self.blacklist.add(user_id)
        else:
            if servicer_id in self.blacklist_per_servicer:
                self.blacklist_per_servicer[servicer_id].add(user_id)
    
    def remove_from_blacklist(self, user_id: str, servicer_id: str) -> bool:
        """从黑名单中移除用户"""
        if self.share_blacklist:
            if user_id in self.blacklist:
                self.blacklist.remove(user_id)
                return True
            return False
        else:
            if servicer_id in self.blacklist_per_servicer and user_id in self.blacklist_per_servicer[servicer_id]:
                self.blacklist_per_servicer[servicer_id].remove(user_id)
                return True
            return False
    
    def is_servicer_busy(self, servicer_id: str) -> bool:
        """检查客服是否正在服务中"""
        for session in self.session_map.values():
            if session.get("servicer_id") == servicer_id and session.get("status") == "connected":
                return True
        return False
    
    def add_to_queue(self, servicer_id: str, user_id: str, user_name: str, group_id: str):
        """将用户添加到客服队列"""
        import time
        if servicer_id not in self.servicer_queue:
            self.servicer_queue[servicer_id] = []
        
        # 检查用户是否已在队列中
        for item in self.servicer_queue[servicer_id]:
            if item["user_id"] == user_id:
                return False
        
        self.servicer_queue[servicer_id].append({
            "user_id": user_id,
            "name": user_name,
            "group_id": group_id,
            "time": time.time()
        })
        return True
    
    def get_queue_position(self, servicer_id: str, user_id: str) -> int:
        """获取用户在队列中的位置（从1开始）"""
        if servicer_id not in self.servicer_queue:
            return -1
        for i, item in enumerate(self.servicer_queue[servicer_id]):
            if item["user_id"] == user_id:
                return i + 1
        return -1
    
    def remove_from_queue(self, user_id: str) -> bool:
        """从所有队列中移除用户"""
        removed = False
        for servicer_id in self.servicer_queue:
            original_len = len(self.servicer_queue[servicer_id])
            self.servicer_queue[servicer_id] = [
                item for item in self.servicer_queue[servicer_id] 
                if item["user_id"] != user_id
            ]
            if len(self.servicer_queue[servicer_id]) < original_len:
                removed = True
        return removed
    
    async def check_conversation_timeout(self, event: AiocqhttpMessageEvent):
        """检查对话是否超时"""
        if self.conversation_timeout <= 0:
            return
        
        import time
        current_time = time.time()
        timeout_seconds = self.conversation_timeout
        warning_seconds = self.timeout_warning_seconds
        
        users_to_timeout = []
        
        for user_id, timer_info in list(self.conversation_timers.items()):
            elapsed = current_time - timer_info["start_time"]
            remaining = timeout_seconds - elapsed
            
            # 检查是否需要发送警告
            if (self.timeout_warning_seconds > 0 and 
                not timer_info.get("warned", False) and 
                remaining <= warning_seconds and remaining > 0):
                
                session = self.session_map.get(user_id)
                if session and session.get("status") == "connected":
                    remaining_seconds = int(remaining)
                    
                    # 通知用户
                    await self.send(
                        event,
                        message=f"⏰ 提醒：对话将在 {remaining_seconds} 秒后自动结束，请抓紧时间沟通",
                        group_id=session.get("group_id"),
                        user_id=user_id,
                    )
                    
                    # 通知客服
                    servicer_id = session.get("servicer_id")
                    if servicer_id:
                        await self.send(
                            event,
                            message=f"⏰ 提醒：与用户 {user_id} 的对话将在 {remaining_seconds} 秒后自动结束",
                            user_id=servicer_id,
                        )
                    
                    timer_info["warned"] = True
            
            # 检查是否超时
            if elapsed >= timeout_seconds:
                users_to_timeout.append(user_id)
        
        # 处理超时的对话
        for user_id in users_to_timeout:
            await self._timeout_conversation(event, user_id)
    
    async def _timeout_conversation(self, event: AiocqhttpMessageEvent, user_id: str):
        """处理对话超时"""
        session = self.session_map.get(user_id)
        if not session or session.get("status") != "connected":
            return
        
        servicer_id = session.get("servicer_id")
        group_id = session.get("group_id")
        
        # 通知用户
        await self.send(
            event,
            message="⏰ 对话时间已到，本次服务自动结束。如需继续咨询，请重新转人工",
            group_id=group_id,
            user_id=user_id,
        )
        
        # 删除会话
        del self.session_map[user_id]
        if user_id in self.conversation_timers:
            del self.conversation_timers[user_id]
        if user_id in self.chat_history:
            del self.chat_history[user_id]
        
        # 检查队列中是否有等待的用户
        if servicer_id and servicer_id in self.servicer_queue and len(self.servicer_queue[servicer_id]) > 0:
            # 从队列中取出第一个用户
            next_user = self.servicer_queue[servicer_id].pop(0)
            next_user_id = next_user["user_id"]
            next_user_name = next_user["name"]
            next_group_id = next_user["group_id"]
            
            # 创建新的会话（等待接入状态）
            self.session_map[next_user_id] = {
                "servicer_id": "",
                "status": "waiting",
                "group_id": next_group_id,
                "selected_servicer": servicer_id
            }
            
            # 通知用户
            await self.send(
                event,
                message=f"⏰ 轮到您了！客服正在准备接入您的对话...\n客服可以使用 /接入对话 命令开始服务",
                group_id=next_group_id,
                user_id=next_user_id,
            )
            
            # 通知客服
            remaining_queue = len(self.servicer_queue[servicer_id])
            queue_info = f"（队列剩余 {remaining_queue} 人）" if remaining_queue > 0 else "（队列已清空）"
            
            await self.send(
                event,
                message=(
                    f"⏰ 与用户 {user_id} 的对话已超时自动结束\n"
                    f"📋 队列中的下一位用户已准备就绪：\n"
                    f"用户：{next_user_name}({next_user_id})\n"
                    f"请使用 /接入对话 命令（回复用户消息）开始服务\n"
                    f"{queue_info}"
                ),
                user_id=servicer_id,
            )
        elif servicer_id:
            # 通知客服对话已超时结束
            await self.send(
                event,
                message=f"⏰ 与用户 {user_id} 的对话已超时自动结束\n📋 当前队列为空",
                user_id=servicer_id,
            )
    
    async def check_queue_timeout(self, event: AiocqhttpMessageEvent):
        """检查排队是否超时"""
        if self.queue_timeout <= 0:
            return
        
        import time
        current_time = time.time()
        timeout_seconds = self.queue_timeout
        
        for servicer_id in list(self.servicer_queue.keys()):
            queue = self.servicer_queue[servicer_id]
            remaining_queue = []
            
            for item in queue:
                elapsed = current_time - item["time"]
                
                if elapsed >= timeout_seconds:
                    # 排队超时，通知用户
                    await self.send(
                        event,
                        message=(
                            f"⏰ 排队时间已超过 {self.queue_timeout} 秒，已自动退出队列\n"
                            f"如需继续咨询，请重新转人工"
                        ),
                        group_id=item["group_id"],
                        user_id=item["user_id"],
                    )
                else:
                    remaining_queue.append(item)
            
            self.servicer_queue[servicer_id] = remaining_queue

    @filter.command("转人工", priority=1)
    async def transfer_to_human(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        send_name = event.get_sender_name()
        group_id = event.get_group_id() or "0"

        # 检查用户是否在黑名单中
        if self.is_user_blacklisted(sender_id):
            yield event.plain_result("⚠ 您已被加入黑名单，无法使用人工客服")
            return

        if sender_id in self.session_map:
            yield event.plain_result("⚠ 您已在等待接入或正在对话")
            return
        
        if sender_id in self.selection_map:
            yield event.plain_result("⚠ 您正在选择客服，请先完成选择")
            return
        
        # 检查用户是否已在某个队列中
        for servicer_id in self.servicer_queue:
            if any(item["user_id"] == sender_id for item in self.servicer_queue[servicer_id]):
                position = self.get_queue_position(servicer_id, sender_id)
                yield event.plain_result(f"⚠ 您已在排队中，当前队列位置：第 {position} 位")
                return

        # 如果启用了客服选择且有多个客服
        if self.enable_servicer_selection and len(self.servicers_id) > 1:
            # 生成客服列表，显示客服状态（过滤掉已拉黑用户的客服）
            servicer_list_items = []
            available_servicers = []
            
            for idx, sid in enumerate(self.servicers_id):
                # 如果不共用黑名单，检查用户是否被该客服拉黑
                if not self.share_blacklist and self.is_user_blacklisted(sender_id, sid):
                    continue  # 跳过已拉黑该用户的客服
                
                servicer_name = self.get_servicer_name(sid)
                status = "🔴 忙碌中" if self.is_servicer_busy(sid) else "🟢 空闲"
                queue_count = len(self.servicer_queue.get(sid, []))
                queue_info = f"（排队 {queue_count} 人）" if queue_count > 0 else ""
                
                list_idx = len(servicer_list_items) + 1
                servicer_list_items.append(f"{list_idx}. {servicer_name} {status}{queue_info}")
                available_servicers.append(sid)
            
            if not available_servicers:
                yield event.plain_result("⚠ 当前没有可用的客服")
                return
            
            self.selection_map[sender_id] = {
                "status": "selecting",
                "group_id": group_id,
                "name": send_name,
                "available_servicers": available_servicers  # 保存可用客服列表
            }
            
            servicer_list = "\n".join(servicer_list_items)
            
            yield event.plain_result(
                f"请选择要对接的客服（回复序号）：\n{servicer_list}\n\n回复 0 取消请求"
            )
        else:
            # 只有一个客服或未启用选择功能
            target_servicer = self.servicers_id[0] if len(self.servicers_id) == 1 else None
            
            # 检查客服是否忙碌
            if target_servicer and self.is_servicer_busy(target_servicer):
                # 客服忙碌，加入队列
                self.add_to_queue(target_servicer, sender_id, send_name, group_id)
                position = self.get_queue_position(target_servicer, sender_id)
                queue_count = len(self.servicer_queue[target_servicer])
                
                yield event.plain_result(
                    f"客服正在服务中🔴\n"
                    f"您已加入等待队列，当前排队人数：{queue_count}\n"
                    f"您的位置：第 {position} 位\n\n"
                    f"💡 使用 /取消排队 可退出队列"
                )
                
                # 通知客服有人排队
                await self.send(
                    event,
                    message=f"📋 {send_name}({sender_id}) 已加入排队，当前队列：{queue_count} 人",
                    user_id=target_servicer,
                )
            else:
                # 客服空闲，直接等待接入
                self.session_map[sender_id] = {
                    "servicer_id": "",
                    "status": "waiting",
                    "group_id": group_id,
                }
                yield event.plain_result("正在等待客服👤接入...")
                for servicer_id in self.servicers_id:
                    await self.send(
                        event,
                        message=f"{send_name}({sender_id}) 请求转人工",
                        user_id=servicer_id,
                    )

    @filter.command("转人机", priority=1)
    async def transfer_to_bot(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        sender_name = event.get_sender_name()
        
        # 检查是否在选择客服状态
        if sender_id in self.selection_map:
            del self.selection_map[sender_id]
            yield event.plain_result("已取消客服选择")
            return
        
        # 检查是否在排队中
        removed = self.remove_from_queue(sender_id)
        if removed:
            yield event.plain_result("已退出排队，我现在是人机啦！")
            return
        
        session = self.session_map.get(sender_id)

        if not session:
            yield event.plain_result("⚠ 您当前没有人工服务请求")
            return

        if session["status"] == "waiting":
            # 用户在等待状态取消请求
            del self.session_map[sender_id]
            yield event.plain_result("已取消人工客服请求，我现在是人机啦！")
            # 通知所有客服人员该用户已取消请求
            for servicer_id in self.servicers_id:
                await self.send(
                    event,
                    message=f"❗{sender_name}({sender_id}) 已取消人工请求",
                    user_id=servicer_id,
                )
        elif session["status"] == "connected":
            # 用户在对话中结束会话
            servicer_name = self.get_servicer_name(session["servicer_id"])
            await self.send(
                event,
                message=f"❗{sender_name} 已结束对话",
                user_id=session["servicer_id"],
            )
            del self.session_map[sender_id]
            # 清理计时器
            if sender_id in self.conversation_timers:
                del self.conversation_timers[sender_id]
            yield event.plain_result("好的，我现在是人机啦！")
    
    @filter.command("取消排队", priority=1)
    async def cancel_queue(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        
        removed = self.remove_from_queue(sender_id)
        if removed:
            yield event.plain_result("✅ 已退出排队")
        else:
            yield event.plain_result("⚠ 您当前不在排队中")
    
    @filter.command("排队状态", priority=1)
    async def check_queue_status(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        
        # 检查用户是否在队列中
        for servicer_id in self.servicer_queue:
            position = self.get_queue_position(servicer_id, sender_id)
            if position > 0:
                queue_count = len(self.servicer_queue[servicer_id])
                yield event.plain_result(
                    f"📋 您的排队信息：\n"
                    f"当前位置：第 {position} 位\n"
                    f"前面还有：{position - 1} 人\n"
                    f"总排队人数：{queue_count} 人"
                )
                return
        
        yield event.plain_result("⚠ 您当前不在排队中")
    
    @filter.command("拉黑", priority=1)
    async def blacklist_user(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id not in self.servicers_id:
            return
        
        # 获取命令参数（AstrBot会自动移除命令部分）
        # 尝试多种方式获取参数
        message_text = event.message_str.strip()
        
        # 如果消息还包含命令本身，移除它
        if message_text.startswith("/拉黑"):
            target_id = message_text.replace("/拉黑", "", 1).strip()
        elif message_text.startswith("拉黑"):
            target_id = message_text.replace("拉黑", "", 1).strip()
        else:
            # 可能AstrBot已经移除了命令，直接使用消息内容
            target_id = message_text
        
        # 验证QQ号格式
        if not target_id or not target_id.isdigit():
            yield event.plain_result("⚠ 请提供正确的QQ号\n使用格式：/拉黑 QQ号\n示例：/拉黑 123456")
            return
        
        # 添加到黑名单
        self.add_to_blacklist(target_id, sender_id)
        
        # 如果用户正在对话或排队，移除
        if target_id in self.session_map:
            session = self.session_map[target_id]
            await self.send(
                event,
                message="您已被客服拉黑，对话已结束",
                group_id=session.get("group_id"),
                user_id=target_id,
            )
            del self.session_map[target_id]
        
        self.remove_from_queue(target_id)
        
        if self.share_blacklist:
            yield event.plain_result(f"✅ 已将用户 {target_id} 加入黑名单（全局）")
        else:
            servicer_name = self.get_servicer_name(sender_id)
            yield event.plain_result(f"✅ 已将用户 {target_id} 加入您的黑名单")
    
    @filter.command("kfhelp", priority=1)
    async def show_help(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        is_servicer = sender_id in self.servicers_id
        
        if is_servicer:
            # 客服身份，显示所有命令
            help_text = "📖 人工客服插件 - 帮助文档\n" + "="*35 + "\n\n"
            help_text += "👤 用户命令：\n"
            help_text += "━"*35 + "\n"
            help_text += "• /转人工\n  请求转接人工客服\n\n"
            help_text += "• /转人机\n  取消转人工或结束对话\n\n"
            help_text += "• /取消排队\n  退出排队队列\n\n"
            help_text += "• /排队状态\n  查看当前排队位置\n\n"
            
            help_text += "\n👨‍💼 客服命令：\n"
            help_text += "━"*35 + "\n"
            help_text += "• /接入对话\n  接入用户对话（回复用户消息）\n\n"
            help_text += "• /拒绝接入\n  拒绝用户接入请求\n\n"
            help_text += "• /结束对话\n  结束当前对话\n\n"
            help_text += "• /拉黑 QQ号\n  拉黑指定用户\n  示例：/拉黑 123456\n\n"
            help_text += "• /取消拉黑 QQ号\n  取消拉黑指定用户\n  示例：/取消拉黑 123456\n\n"
            help_text += "• /查看黑名单\n  查看黑名单列表\n\n"
            
            if self.enable_translation:
                help_text += "• /翻译测试\n  测试翻译功能是否正常\n\n"
            
            if self.enable_chat_history:
                help_text += "• /导出记录\n  导出当前会话聊天记录\n\n"
            
            help_text += "• /kfhelp\n  显示此帮助信息\n\n"
            
            # 添加配置信息
            help_text += "\n⚙️ 当前配置：\n"
            help_text += "━"*35 + "\n"
            help_text += f"• 客服数量：{len(self.servicers_id)} 人\n"
            help_text += f"• 客服选择：{'开启' if self.enable_servicer_selection else '关闭'}\n"
            help_text += f"• 黑名单模式：{'共用' if self.share_blacklist else '独立'}\n"
            help_text += f"• 聊天记录：{'开启' if self.enable_chat_history else '关闭'}\n"
            
            if self.message_prefix:
                help_text += f"• 消息前缀：\"{self.message_prefix}\"\n"
            
            if self.message_suffix:
                help_text += f"• 消息后缀：\"{self.message_suffix}\"\n"
            
            if self.enable_random_reply:
                help_text += f"• 答非所问：开启（文字：\"{self.random_reply_chars}\"）\n"
            
            if self.enable_translation:
                help_text += f"• 智能翻译：开启（{self.translation_main_language}↔{self.translation_target_language}，模型：{self.openai_model}）\n"
            
            if self.conversation_timeout > 0:
                help_text += f"• 对话时限：{self.conversation_timeout} 秒\n"
            if self.queue_timeout > 0:
                help_text += f"• 排队时限：{self.queue_timeout} 秒\n"
            
        else:
            # 普通用户，只显示用户命令
            help_text = "📖 人工客服插件 - 使用帮助\n" + "="*35 + "\n\n"
            help_text += "• /转人工\n  请求转接人工客服，如有多个客服可选择\n\n"
            help_text += "• /转人机\n  取消转人工请求或结束对话\n\n"
            help_text += "• /取消排队\n  退出排队队列\n\n"
            help_text += "• /排队状态\n  查看当前排队位置和人数\n\n"
            help_text += "• /kfhelp\n  显示此帮助信息\n\n"
            
            help_text += "💡 提示：\n"
            help_text += "━"*35 + "\n"
            help_text += "• 客服忙碌时会自动加入排队\n"
            help_text += "• 可随时使用 /转人机 取消\n"
            
            if self.conversation_timeout > 0:
                help_text += f"• 对话限时 {self.conversation_timeout} 秒\n"
            if self.queue_timeout > 0:
                help_text += f"• 排队限时 {self.queue_timeout} 秒\n"
        
        yield event.plain_result(help_text)
    
    @filter.command("翻译测试", priority=1)
    async def test_translation(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id not in self.servicers_id:
            return
        
        # 检查是否启用了翻译
        if not self.enable_translation:
            yield event.plain_result("⚠ 智能翻译功能未启用\n请在插件配置中开启 enable_translation")
            return
        
        # 检查API Key
        if not self.openai_api_key:
            yield event.plain_result("⚠ 未配置OpenAI API Key\n请在插件配置中填写 openai_api_key")
            return
        
        yield event.plain_result("🔄 正在测试翻译功能，请稍候...")
        
        # 执行测试翻译
        test_text = "你好"
        target_lang = self.translation_target_language
        
        try:
            translation = await self.translate_text(test_text, target_lang)
            
            if translation:
                # 测试成功
                yield event.plain_result(
                    f"✅ 翻译测试成功！\n\n"
                    f"测试文本：{test_text}\n"
                    f"翻译结果：{translation}\n\n"
                    f"📊 配置信息：\n"
                    f"• 主语言：{self.translation_main_language}\n"
                    f"• 目标语言：{self.translation_target_language}\n"
                    f"• 使用模型：{self.openai_model}\n"
                    f"• API地址：{self.openai_base_url}"
                )
            else:
                # 翻译失败
                yield event.plain_result(
                    f"❌ 翻译测试失败\n\n"
                    f"可能的原因：\n"
                    f"• API Key 无效或已过期\n"
                    f"• API 地址不正确\n"
                    f"• 网络连接问题\n"
                    f"• 模型不存在或无权访问\n\n"
                    f"当前配置：\n"
                    f"• 模型：{self.openai_model}\n"
                    f"• API地址：{self.openai_base_url}\n"
                    f"请检查配置或查看控制台日志获取详细错误信息"
                )
        except Exception as e:
            yield event.plain_result(
                f"❌ 翻译测试异常\n\n"
                f"错误信息：{str(e)}\n\n"
                f"请检查配置或查看控制台日志"
            )
    
    @filter.command("查看黑名单", priority=1)
    async def view_blacklist(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id not in self.servicers_id:
            return
        
        # 如果是共用黑名单或单客服
        if self.share_blacklist or len(self.servicers_id) == 1:
            # 直接显示黑名单
            if self.share_blacklist:
                blacklist = self.blacklist
                title = "📋 黑名单列表（共用）"
            else:
                blacklist = self.blacklist_per_servicer.get(sender_id, set())
                title = "📋 您的黑名单列表"
            
            if not blacklist:
                yield event.plain_result("✅ 黑名单为空")
                return
            
            # 构建黑名单列表
            blacklist_text = f"{title}\n" + "="*30 + "\n\n"
            for idx, user_id in enumerate(sorted(blacklist), 1):
                # 尝试获取用户昵称
                try:
                    user_info = await event.bot.get_stranger_info(user_id=int(user_id))
                    nickname = user_info.get("nickname", user_id)
                    blacklist_text += f"{idx}. {nickname} ({user_id})\n"
                except:
                    blacklist_text += f"{idx}. {user_id}\n"
            
            blacklist_text += f"\n共 {len(blacklist)} 个用户"
            yield event.plain_result(blacklist_text)
        else:
            # 多客服独立黑名单，显示客服列表供选择
            self.blacklist_view_selection[sender_id] = {
                "status": "selecting"
            }
            
            servicer_list_items = []
            for idx, sid in enumerate(self.servicers_id, 1):
                servicer_name = self.get_servicer_name(sid)
                count = len(self.blacklist_per_servicer.get(sid, set()))
                servicer_list_items.append(f"{idx}. {servicer_name} - {count} 人")
            
            servicer_list = "\n".join(servicer_list_items)
            
            yield event.plain_result(
                f"请选择要查看的客服黑名单（回复序号）：\n{servicer_list}\n\n回复 0 取消"
            )
    
    @filter.command("取消拉黑", priority=1)
    async def unblacklist_user(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id not in self.servicers_id:
            return
        
        # 获取命令参数（AstrBot会自动移除命令部分）
        # 尝试多种方式获取参数
        message_text = event.message_str.strip()
        
        # 如果消息还包含命令本身，移除它
        if message_text.startswith("/取消拉黑"):
            target_id = message_text.replace("/取消拉黑", "", 1).strip()
        elif message_text.startswith("取消拉黑"):
            target_id = message_text.replace("取消拉黑", "", 1).strip()
        else:
            # 可能AstrBot已经移除了命令，直接使用消息内容
            target_id = message_text
        
        # 验证QQ号格式
        if not target_id or not target_id.isdigit():
            yield event.plain_result("⚠ 请提供正确的QQ号\n使用格式：/取消拉黑 QQ号\n示例：/取消拉黑 123456")
            return
        
        # 从黑名单移除
        success = self.remove_from_blacklist(target_id, sender_id)
        
        if success:
            if self.share_blacklist:
                yield event.plain_result(f"✅ 已将用户 {target_id} 从黑名单移除（全局）")
            else:
                yield event.plain_result(f"✅ 已将用户 {target_id} 从您的黑名单移除")
        else:
            yield event.plain_result(f"⚠ 用户 {target_id} 不在黑名单中")

    @filter.command("接入对话", priority=1)
    async def accept_conversation(
        self, event: AiocqhttpMessageEvent, target_id: str | int | None = None
    ):
        sender_id = event.get_sender_id()
        if sender_id not in self.servicers_id:
            return

        if reply_seg := next(
            (seg for seg in event.get_messages() if isinstance(seg, Reply)), None
        ):
            if text := reply_seg.message_str:
                if match := re.search(r"\((\d+)\)", text):
                    target_id = match.group(1)

        session = self.session_map.get(target_id)

        if not session or session["status"] != "waiting":
            yield event.plain_result(f"用户({target_id})未请求人工")
            return

        if session["status"] == "connected":
            yield event.plain_result("您正在与该用户对话")

        session["status"] = "connected"
        session["servicer_id"] = sender_id
        
        # 记录对话开始时间
        if self.conversation_timeout > 0:
            import time
            self.conversation_timers[target_id] = {
                "start_time": time.time(),
                "warned": False
            }
        
        # 初始化聊天记录
        if self.enable_chat_history:
            self.chat_history[target_id] = []

        # 生成接入提示
        servicer_name = self.get_servicer_name(sender_id)
        timeout_tip = f"\n⏰ 本次对话限时 {self.conversation_timeout} 秒" if self.conversation_timeout > 0 else ""
        
        await self.send(
            event,
            message=f"客服【{servicer_name}】已接入{timeout_tip}",
            group_id=session["group_id"],
            user_id=target_id,
        )
        
        tips = "好的，接下来我将转发你的消息给对方，请开始对话："
        if self.enable_chat_history:
            tips += "\n💡 提示：可使用 /导出记录 命令导出聊天记录"
        if self.conversation_timeout > 0:
            tips += f"\n⏰ 对话限时 {self.conversation_timeout} 秒"
        yield event.plain_result(tips)
        event.stop_event()

    @filter.command("拒绝接入", priority=1)
    async def reject_conversation(self, event: AiocqhttpMessageEvent, target_id: str | int | None = None):
        sender_id = event.get_sender_id()
        if sender_id not in self.servicers_id:
            return

        if reply_seg := next(
            (seg for seg in event.get_messages() if isinstance(seg, Reply)), None
        ):
            if text := reply_seg.message_str:
                if match := re.search(r"\((\d+)\)", text):
                    target_id = match.group(1)

        session = self.session_map.get(target_id)

        if not session or session["status"] != "waiting":
            yield event.plain_result(f"用户({target_id})未请求人工或已被接入")
            return

        # 删除会话
        del self.session_map[target_id]
        
        # 通知用户
        await self.send(
            event,
            message="抱歉，客服暂时无法接入，请稍后再试或联系其他客服",
            group_id=session["group_id"],
            user_id=target_id,
        )
        
        yield event.plain_result(f"已拒绝用户 {target_id} 的接入请求")

    @filter.command("导出记录", priority=1)
    async def export_chat_history(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id not in self.servicers_id:
            return
        
        if not self.enable_chat_history:
            yield event.plain_result("⚠ 聊天记录功能未启用")
            return
        
        # 查找当前客服正在服务的用户
        target_user_id = None
        for uid, session in self.session_map.items():
            if session.get("servicer_id") == sender_id and session.get("status") == "connected":
                target_user_id = uid
                break
        
        if not target_user_id:
            yield event.plain_result("⚠ 当前没有正在进行的对话")
            return
        
        history = self.chat_history.get(target_user_id, [])
        if not history:
            yield event.plain_result("⚠ 暂无聊天记录")
            return
        
        # 生成QQ聊天记录格式的转发消息
        from datetime import datetime
        
        forward_messages = []
        for record in history:
            # 构造转发消息节点
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
            yield event.plain_result(f"✅ 已导出聊天记录（共 {len(history)} 条消息）")
        except Exception as e:
            # 如果合并转发失败，使用文本格式
            text_history = f"📝 聊天记录（共 {len(history)} 条）\n" + "="*30 + "\n\n"
            for record in history:
                text_history += f"[{record['time']}] {record['name']}:\n{record['message']}\n\n"
            
            yield event.plain_result(text_history)

    @filter.command("结束对话")
    async def end_conversation(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id not in self.servicers_id:
            return

        for uid, session in self.session_map.items():
            if session["servicer_id"] == sender_id:
                servicer_name = self.get_servicer_name(sender_id)
                await self.send(
                    event,
                    message=f"客服【{servicer_name}】已结束对话",
                    group_id=session["group_id"],
                    user_id=uid,
                )
                del self.session_map[uid]
                # 清理聊天记录和计时器
                if uid in self.chat_history:
                    del self.chat_history[uid]
                if uid in self.conversation_timers:
                    del self.conversation_timers[uid]
                
                # 检查队列中是否有等待的用户
                if sender_id in self.servicer_queue and len(self.servicer_queue[sender_id]) > 0:
                    # 从队列中取出第一个用户
                    next_user = self.servicer_queue[sender_id].pop(0)
                    next_user_id = next_user["user_id"]
                    next_user_name = next_user["name"]
                    next_group_id = next_user["group_id"]
                    
                    # 创建新的会话（等待接入状态）
                    self.session_map[next_user_id] = {
                        "servicer_id": "",
                        "status": "waiting",
                        "group_id": next_group_id,
                        "selected_servicer": sender_id
                    }
                    
                    # 通知用户
                    await self.send(
                        event,
                        message=f"⏰ 轮到您了！客服正在准备接入您的对话...\n客服可以使用 /接入对话 命令开始服务",
                        group_id=next_group_id,
                        user_id=next_user_id,
                    )
                    
                    # 通知客服
                    remaining_queue = len(self.servicer_queue[sender_id])
                    queue_info = f"（队列剩余 {remaining_queue} 人）" if remaining_queue > 0 else "（队列已清空）"
                    
                    yield event.plain_result(
                        f"✅ 已结束与用户 {uid} 的对话\n"
                        f"📋 队列中的下一位用户已准备就绪：\n"
                        f"用户：{next_user_name}({next_user_id})\n"
                        f"请使用 /接入对话 命令（回复用户消息）开始服务\n"
                        f"{queue_info}"
                    )
                else:
                    yield event.plain_result(f"✅ 已结束与用户 {uid} 的对话\n📋 当前队列为空")
                
                return

        yield event.plain_result("当前无对话需要结束")

    async def send(
        self,
        event: AiocqhttpMessageEvent,
        message,
        group_id: int | str | None = None,
        user_id: int | str | None = None,
        need_translation: bool = False,
        target_language: str = None,
    ):
        """向用户发消息，兼容群聊或私聊"""
        # 如果需要翻译且启用了翻译功能
        if need_translation and self.enable_translation and isinstance(message, str):
            translation = await self.translate_text(message, target_language or self.translation_target_language)
            if translation:
                # 发送原文 + 翻译
                message = f"{message}\n\n[翻译] {translation}"
        
        if group_id and str(group_id) != "0":
            await event.bot.send_group_msg(group_id=int(group_id), message=message)
        elif user_id:
            await event.bot.send_private_msg(user_id=int(user_id), message=message)

    async def send_ob(
        self,
        event: AiocqhttpMessageEvent,
        group_id: int | str | None = None,
        user_id: int | str | None = None,
        add_prefix: bool = False,
        is_from_servicer: bool = False,
    ):
        """向用户发onebot格式的消息，兼容群聊或私聊"""
        ob_message = await event._parse_onebot_json(
            MessageChain(chain=event.message_obj.message)
        )
        
        # 提取原始文本用于翻译
        original_text = ""
        if isinstance(ob_message, str):
            original_text = ob_message
        elif isinstance(ob_message, list):
            for segment in ob_message:
                if isinstance(segment, dict) and segment.get("type") == "text":
                    original_text += segment["data"].get("text", "")
        
        # 如果启用了答非所问模式，替换消息内容
        if add_prefix and self.enable_random_reply:
            # 如果是字符串消息
            if isinstance(ob_message, str):
                original_length = len(ob_message)
                ob_message = self.generate_random_text(original_length)
            # 如果是列表消息（包含多个消息段）
            elif isinstance(ob_message, list) and len(ob_message) > 0:
                # 检查是否只包含纯文本消息
                has_only_text = all(
                    isinstance(seg, dict) and seg.get("type") == "text" 
                    for seg in ob_message
                )
                
                # 只有纯文本消息才替换
                if has_only_text:
                    # 计算原消息长度并替换
                    original_text = ""
                    for segment in ob_message:
                        if isinstance(segment, dict) and segment.get("type") == "text":
                            original_text += segment["data"].get("text", "")
                    
                    # 生成随机文字并替换第一个文本段
                    if original_text:
                        random_text = self.generate_random_text(len(original_text))
                        for i, segment in enumerate(ob_message):
                            if isinstance(segment, dict) and segment.get("type") == "text":
                                segment["data"]["text"] = random_text
                                # 删除其他文本段
                                ob_message = [segment]
                                break
        # 如果未启用答非所问，检查是否需要添加前缀或后缀
        elif add_prefix and (self.message_prefix or self.message_suffix):
            # 如果是字符串消息，直接添加前缀和后缀
            if isinstance(ob_message, str):
                if self.message_prefix:
                    ob_message = self.message_prefix + ob_message
                if self.message_suffix:
                    ob_message = ob_message + self.message_suffix
            # 如果是列表消息（包含多个消息段）
            elif isinstance(ob_message, list) and len(ob_message) > 0:
                # 检查是否只包含纯文本消息
                has_only_text = all(
                    isinstance(seg, dict) and seg.get("type") == "text" 
                    for seg in ob_message
                )
                
                # 只有纯文本消息才添加前缀和后缀
                if has_only_text:
                    # 在第一个文本消息段前添加前缀
                    if self.message_prefix:
                        for i, segment in enumerate(ob_message):
                            if isinstance(segment, dict) and segment.get("type") == "text":
                                segment["data"]["text"] = self.message_prefix + segment["data"]["text"]
                                break
                    
                    # 在最后一个文本消息段后添加后缀
                    if self.message_suffix:
                        for i in range(len(ob_message) - 1, -1, -1):
                            segment = ob_message[i]
                            if isinstance(segment, dict) and segment.get("type") == "text":
                                segment["data"]["text"] = segment["data"]["text"] + self.message_suffix
                                break
        
        # 先发送主消息
        if group_id and str(group_id) != "0":
            await event.bot.send_group_msg(group_id=int(group_id), message=ob_message)
        elif user_id:
            await event.bot.send_private_msg(user_id=int(user_id), message=ob_message)
        
        # 如果启用了翻译且有文本内容，发送翻译
        if self.enable_translation and original_text and not self.enable_random_reply:
            # 判断翻译方向
            if is_from_servicer:
                # 客服 -> 用户：翻译为目标语言
                target_lang = self.translation_target_language
            else:
                # 用户 -> 客服：翻译为主语言
                target_lang = self.translation_main_language
            
            translation = await self.translate_text(original_text, target_lang)
            if translation and translation != original_text:
                # 发送翻译
                translation_msg = f"[翻译] {translation}"
                if group_id and str(group_id) != "0":
                    await event.bot.send_group_msg(group_id=int(group_id), message=translation_msg)
                elif user_id:
                    await event.bot.send_private_msg(user_id=int(user_id), message=translation_msg)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_match(self, event: AiocqhttpMessageEvent):
        """监听对话消息转发和客服选择"""
        # 检查对话和排队超时
        await self.check_conversation_timeout(event)
        await self.check_queue_timeout(event)
        
        chain = event.get_messages()
        if not chain or any(isinstance(seg, (Reply)) for seg in chain):
            return
        sender_id = event.get_sender_id()
        message_text = event.message_str.strip()
        
        # 处理客服查看黑名单时的选择
        if sender_id in self.blacklist_view_selection:
            if message_text.isdigit():
                choice = int(message_text)
                
                if choice == 0:
                    # 取消选择
                    del self.blacklist_view_selection[sender_id]
                    yield event.plain_result("已取消查看")
                    event.stop_event()
                    return
                elif 1 <= choice <= len(self.servicers_id):
                    # 选择了有效的客服
                    selected_servicer_id = self.servicers_id[choice - 1]
                    selected_servicer_name = self.get_servicer_name(selected_servicer_id)
                    
                    # 删除选择状态
                    del self.blacklist_view_selection[sender_id]
                    
                    # 获取该客服的黑名单
                    blacklist = self.blacklist_per_servicer.get(selected_servicer_id, set())
                    
                    if not blacklist:
                        yield event.plain_result(f"✅ 客服【{selected_servicer_name}】的黑名单为空")
                        event.stop_event()
                        return
                    
                    # 构建黑名单列表
                    blacklist_text = f"📋 客服【{selected_servicer_name}】的黑名单\n" + "="*30 + "\n\n"
                    for idx, user_id in enumerate(sorted(blacklist), 1):
                        # 尝试获取用户昵称
                        try:
                            user_info = await event.bot.get_stranger_info(user_id=int(user_id))
                            nickname = user_info.get("nickname", user_id)
                            blacklist_text += f"{idx}. {nickname} ({user_id})\n"
                        except:
                            blacklist_text += f"{idx}. {user_id}\n"
                    
                    blacklist_text += f"\n共 {len(blacklist)} 个用户"
                    yield event.plain_result(blacklist_text)
                    event.stop_event()
                    return
                else:
                    yield event.plain_result(f"⚠ 无效的选择，请输入 1-{len(self.servicers_id)} 或 0 取消")
                    event.stop_event()
                    return
            else:
                yield event.plain_result("⚠ 请输入数字进行选择")
                event.stop_event()
                return
        
        # 处理用户选择客服
        if sender_id in self.selection_map:
            selection = self.selection_map[sender_id]
            
            # 检查是否是数字选择
            if message_text.isdigit():
                choice = int(message_text)
                
                if choice == 0:
                    # 取消选择
                    del self.selection_map[sender_id]
                    yield event.plain_result("已取消客服选择")
                    event.stop_event()
                    return
                else:
                    # 获取可用客服列表
                    available_servicers = selection.get("available_servicers", self.servicers_id)
                    
                    if 1 <= choice <= len(available_servicers):
                        # 选择了有效的客服
                        selected_servicer_id = available_servicers[choice - 1]
                        selected_servicer_name = self.get_servicer_name(selected_servicer_id)
                    else:
                        yield event.plain_result(f"⚠ 无效的选择，请输入 1-{len(available_servicers)} 或 0 取消")
                        event.stop_event()
                        return
                    
                    # 删除选择状态
                    del self.selection_map[sender_id]
                    
                    # 检查客服是否忙碌
                    if self.is_servicer_busy(selected_servicer_id):
                        # 客服忙碌，加入队列
                        self.add_to_queue(selected_servicer_id, sender_id, selection['name'], selection["group_id"])
                        position = self.get_queue_position(selected_servicer_id, sender_id)
                        queue_count = len(self.servicer_queue[selected_servicer_id])
                        
                        yield event.plain_result(
                            f"客服【{selected_servicer_name}】正在服务中🔴\n"
                            f"您已加入等待队列，当前排队人数：{queue_count}\n"
                            f"您的位置：第 {position} 位\n\n"
                            f"💡 使用 /取消排队 可退出队列"
                        )
                        
                        # 通知客服有人排队
                        await self.send(
                            event,
                            message=f"📋 {selection['name']}({sender_id}) 已加入排队（指定您），当前队列：{queue_count} 人",
                            user_id=selected_servicer_id,
                        )
                    else:
                        # 客服空闲，创建会话
                        self.session_map[sender_id] = {
                            "servicer_id": "",
                            "status": "waiting",
                            "group_id": selection["group_id"],
                            "selected_servicer": selected_servicer_id
                        }
                        
                        # 通知用户和客服
                        yield event.plain_result(f"正在等待客服【{selected_servicer_name}】接入...")
                        await self.send(
                            event,
                            message=f"{selection['name']}({sender_id}) 请求转人工（指定您）",
                            user_id=selected_servicer_id,
                        )
                    event.stop_event()
                    return
            else:
                yield event.plain_result("⚠ 请输入数字进行选择")
                event.stop_event()
                return
        
        # 客服 → 用户 (仅私聊生效)
        if (
            sender_id in self.servicers_id
            and event.is_private_chat()
            and event.message_str not in ("接入对话", "结束对话", "拒绝接入", "导出记录")
        ):
            for user_id, session in self.session_map.items():
                if (
                    session["servicer_id"] == sender_id
                    and session["status"] == "connected"
                ):
                    # 记录聊天内容
                    if self.enable_chat_history and user_id in self.chat_history:
                        from datetime import datetime
                        servicer_name = self.get_servicer_name(sender_id)
                        self.chat_history[user_id].append({
                            "sender_id": sender_id,
                            "name": f"客服【{servicer_name}】",
                            "message": event.message_str,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                    
                    await self.send_ob(
                        event,
                        group_id=session["group_id"],
                        user_id=user_id,
                        add_prefix=True,  # 客服发给用户，添加前缀
                        is_from_servicer=True,  # 标记为客服消息，翻译为目标语言
                    )
                    event.stop_event()
                    break

        # 用户 → 客服
        elif session := self.session_map.get(sender_id):
            if session["status"] == "connected":
                # 记录聊天内容
                if self.enable_chat_history and sender_id in self.chat_history:
                    from datetime import datetime
                    self.chat_history[sender_id].append({
                        "sender_id": sender_id,
                        "name": event.get_sender_name(),
                        "message": event.message_str,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                
                await self.send_ob(
                    event,
                    user_id=session["servicer_id"],
                    add_prefix=False,  # 用户发给客服，不添加前缀
                    is_from_servicer=False,  # 标记为用户消息，翻译为主语言
                )
                event.stop_event()
