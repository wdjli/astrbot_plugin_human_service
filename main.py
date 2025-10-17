import re
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.message.components import Reply
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

# 导入工具函数
from .utils import (
    extract_text_from_message,
    is_pure_text_message,
    add_prefix_to_message,
    add_suffix_to_message,
    replace_with_random_text,
)

# 导入管理器类
from .managers import (
    QueueManager,
    BlacklistManager,
    SessionManager,
    TimeoutManager,
    TranslationService,
    CommandHandler,
    SilenceModeManager,
)

# 导入辅助工具类
from .helpers import (
    HelpTextBuilder,
    BlacklistFormatter,
    ChatHistoryExporter,
    MessageRouter,
)


@register(
    "astrbot_plugin_human_service",
    "Zhalslar&dongyue",
    "人工客服插件 - 支持智能排队、时间管理、客服名称和黑名单",
    "1.7.2",
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
        self.enable_silence_mode = config.get("enable_silence_mode", False)
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
        self.conversation_timeout = config.get("conversation_timeout", 0)
        self.queue_timeout = config.get("queue_timeout", 0)
        self.timeout_warning_seconds = config.get("timeout_warning_seconds", 120)
        
        # 初始化管理器
        self.queue_manager = QueueManager(self.servicers_id)
        self.blacklist_manager = BlacklistManager(self.servicers_id, self.share_blacklist)
        self.session_manager = SessionManager()
        self.timeout_manager = TimeoutManager(self.conversation_timeout, self.timeout_warning_seconds)
        
        # 翻译服务
        if self.enable_translation and self.openai_api_key:
            self.translation_service = TranslationService(
                self.openai_api_key,
                self.openai_base_url,
                self.openai_model
            )
        else:
            self.translation_service = None
        
        # 命令处理器
        self.command_handler = CommandHandler(self)
        
        # 活动沉默模式管理器
        self.silence_mode_manager = SilenceModeManager(self.enable_silence_mode, self.servicers_id)
        
        # 消息路由器
        self.message_router = MessageRouter(self)
        
        # 聊天记录：{user_id: [{"sender": "user/servicer", "name": "xxx", "message": "xxx", "time": "xxx"}]}
        self.chat_history = {}
    
    def get_servicer_name(self, servicer_id: str) -> str:
        """获取客服名称，如果没有配置则返回QQ号"""
        return self.servicers_config.get(servicer_id, servicer_id)
    
    # 兼容性属性访问器
    @property
    def session_map(self):
        """访问会话映射（兼容旧代码）"""
        return self.session_manager.session_map
    
    @property
    def selection_map(self):
        """访问选择映射（兼容旧代码）"""
        return self.session_manager.selection_map
    
    @property
    def blacklist_view_selection(self):
        """访问黑名单查看选择（兼容旧代码）"""
        return self.session_manager.blacklist_view_selection
    
    @property
    def servicer_queue(self):
        """访问客服队列（兼容旧代码）"""
        return self.queue_manager.servicer_queue
    
    @property
    def conversation_timers(self):
        """访问对话计时器（兼容旧代码）"""
        return self.timeout_manager.timers
    
    # 便捷方法（委托给管理器）
    def is_user_blacklisted(self, user_id: str, servicer_id: str = None) -> bool:
        return self.blacklist_manager.is_blacklisted(user_id, servicer_id)
    
    def add_to_blacklist(self, user_id: str, servicer_id: str):
        self.blacklist_manager.add(user_id, servicer_id)
    
    def remove_from_blacklist(self, user_id: str, servicer_id: str) -> bool:
        return self.blacklist_manager.remove(user_id, servicer_id)
    
    def is_servicer_busy(self, servicer_id: str) -> bool:
        return self.session_manager.is_servicer_busy(servicer_id)
    
    def add_to_queue(self, servicer_id: str, user_id: str, user_name: str, group_id: str):
        return self.queue_manager.add(servicer_id, user_id, user_name, group_id)
    
    def get_queue_position(self, servicer_id: str, user_id: str) -> int:
        return self.queue_manager.get_position(servicer_id, user_id)
    
    def remove_from_queue(self, user_id: str) -> bool:
        return self.queue_manager.remove(user_id)
    
    async def translate_text(self, text: str, target_language: str) -> str:
        """使用OpenAI API翻译文本"""
        if not self.translation_service:
            return None
        return await self.translation_service.translate(text, target_language)
    
    async def check_conversation_timeout(self, event: AiocqhttpMessageEvent):
        """检查对话是否超时"""
        if self.conversation_timeout <= 0:
            return
        
        # 检查需要警告的用户
        users_need_warning = self.timeout_manager.get_users_need_warning()
        for user_id in users_need_warning:
            session = self.session_manager.get_session(user_id)
            if session and session.get("status") == "connected":
                remaining_seconds = int(self.timeout_manager.get_remaining_time(user_id))
                
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
                
                self.timeout_manager.mark_warned(user_id)
        
        # 处理超时的对话
        timeout_users = self.timeout_manager.get_timeout_users()
        for user_id in timeout_users:
            await self._timeout_conversation(event, user_id)
    
    async def _timeout_conversation(self, event: AiocqhttpMessageEvent, user_id: str):
        """处理对话超时"""
        session = self.session_manager.get_session(user_id)
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
        
        # 清理会话和数据
        self.session_manager.delete_session(user_id)
        self.timeout_manager.stop_timer(user_id)
        if user_id in self.chat_history:
            del self.chat_history[user_id]
        
        # 使用CommandHandler处理队列中的下一位
        if servicer_id:
            has_next = await self.command_handler.prepare_next_user_from_queue(
                event, servicer_id, f"⏰ 与用户 {user_id} 的对话已超时自动结束"
            )
            
            if not has_next:
                await self.send(
                    event,
                    message=f"⏰ 与用户 {user_id} 的对话已超时自动结束\n📋 当前队列为空",
                    user_id=servicer_id,
                )
    
    async def check_queue_timeout(self, event: AiocqhttpMessageEvent):
        """检查排队是否超时"""
        if self.queue_timeout <= 0:
            return
        
        # 获取超时的用户
        timeout_users = self.queue_manager.check_timeout(self.queue_timeout)
        
        # 通知超时用户
        for item in timeout_users:
            await self.send(
                event,
                message=(
                    f"⏰ 排队时间已超过 {self.queue_timeout} 秒，已自动退出队列\n"
                    f"如需继续咨询，请重新转人工"
                ),
                group_id=item["group_id"],
                user_id=item["user_id"],
            )

    @filter.command("转人工", priority=1)
    async def transfer_to_human(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        send_name = event.get_sender_name()
        group_id = event.get_group_id() or "0"

        # 使用CommandHandler进行前置检查
        success, error_msg, _ = await self.command_handler.handle_transfer_to_human(event, sender_id, send_name, group_id)
        if not success:
            yield event.plain_result(error_msg)
            return

        # 如果启用了客服选择且有多个客服
        if self.enable_servicer_selection and len(self.servicers_id) > 1:
            # 获取可用客服并格式化列表
            available_servicers = self.command_handler.get_available_servicers(sender_id)
            
            if not available_servicers:
                yield event.plain_result("⚠ 当前没有可用的客服")
                return
            
            servicer_list_items, available_servicers = self.command_handler.format_servicer_list(available_servicers)
            
            self.selection_map[sender_id] = {
                "status": "selecting",
                "group_id": group_id,
                "name": send_name,
                "available_servicers": available_servicers
            }
            
            servicer_list = "\n".join(servicer_list_items)
            yield event.plain_result(
                f"请选择要对接的客服（回复序号）：\n{servicer_list}\n\n回复 0 取消请求"
            )
        else:
            # 单客服模式
            target_servicer = self.servicers_id[0] if len(self.servicers_id) == 1 else None
            
            if target_servicer and self.is_servicer_busy(target_servicer):
                # 客服忙碌，加入队列
                self.add_to_queue(target_servicer, sender_id, send_name, group_id)
                position = self.get_queue_position(target_servicer, sender_id)
                queue_count = self.queue_manager.get_size(target_servicer)
                
                yield event.plain_result(
                    f"客服正在服务中🔴\n"
                    f"您已加入等待队列，当前排队人数：{queue_count}\n"
                    f"您的位置：第 {position} 位\n\n"
                    f"💡 使用 /取消排队 可退出队列"
                )
                
                await self.send(
                    event,
                    message=f"📋 {send_name}({sender_id}) 已加入排队，当前队列：{queue_count} 人",
                    user_id=target_servicer,
                )
            else:
                # 客服空闲，创建会话
                self.session_manager.create_session(sender_id, {
                    "servicer_id": "",
                    "status": "waiting",
                    "group_id": group_id,
                })
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
            self.timeout_manager.stop_timer(sender_id)
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
        
        # 准备配置字典
        config = {
            "servicers_count": len(self.servicers_id),
            "enable_servicer_selection": self.enable_servicer_selection,
            "share_blacklist": self.share_blacklist,
            "enable_chat_history": self.enable_chat_history,
            "enable_silence_mode": self.enable_silence_mode,
            "message_prefix": self.message_prefix,
            "message_suffix": self.message_suffix,
            "enable_random_reply": self.enable_random_reply,
            "random_reply_chars": self.random_reply_chars,
            "enable_translation": self.enable_translation,
            "translation_main_language": self.translation_main_language,
            "translation_target_language": self.translation_target_language,
            "openai_model": self.openai_model,
            "conversation_timeout": self.conversation_timeout,
            "queue_timeout": self.queue_timeout,
        }
        
        # 使用HelpTextBuilder生成帮助文档
        if is_servicer:
            help_text = HelpTextBuilder.build_servicer_help(config)
        else:
            help_text = HelpTextBuilder.build_user_help(config)
        
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
            blacklist = self.blacklist_manager.get_blacklist(sender_id if not self.share_blacklist else None)
            title = "📋 黑名单列表（共用）" if self.share_blacklist else "📋 您的黑名单列表"
            
            if not blacklist:
                yield event.plain_result("✅ 黑名单为空")
                return
            
            # 使用BlacklistFormatter格式化
            blacklist_text = await BlacklistFormatter.format_blacklist(blacklist, event, title)
            if blacklist_text:
                yield event.plain_result(blacklist_text)
        else:
            # 多客服独立黑名单，显示客服列表供选择
            self.blacklist_view_selection[sender_id] = {"status": "selecting"}
            
            servicer_list_items = []
            for idx, sid in enumerate(self.servicers_id, 1):
                servicer_name = self.get_servicer_name(sid)
                count = self.blacklist_manager.get_count(sid)
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
        self.timeout_manager.start_timer(target_id)
        
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
        target_user_id = self.session_manager.get_user_by_servicer(sender_id)
        
        if not target_user_id:
            yield event.plain_result("⚠ 当前没有正在进行的对话")
            return
        
        history = self.chat_history.get(target_user_id, [])
        
        # 使用ChatHistoryExporter导出
        success, message = await ChatHistoryExporter.export_as_forward(history, event, sender_id)
        
        if success:
            yield event.plain_result(message)
        elif message:
            yield event.plain_result(message)
        else:
            # 合并转发失败，使用文本格式
            text_history = ChatHistoryExporter.export_as_text(history)
            yield event.plain_result(text_history)

    @filter.command("结束对话")
    async def end_conversation(self, event: AiocqhttpMessageEvent):
        sender_id = event.get_sender_id()
        if sender_id not in self.servicers_id:
            return

        # 查找客服正在服务的用户
        uid = self.session_manager.get_user_by_servicer(sender_id)
        if not uid:
            yield event.plain_result("当前无对话需要结束")
            return
        
        session = self.session_manager.get_session(uid)
        servicer_name = self.get_servicer_name(sender_id)
        
        # 通知用户
        await self.send(
            event,
            message=f"客服【{servicer_name}】已结束对话",
            group_id=session["group_id"],
            user_id=uid,
        )
        
        # 清理会话和数据
        self.session_manager.delete_session(uid)
        self.timeout_manager.stop_timer(uid)
        if uid in self.chat_history:
            del self.chat_history[uid]
        
        # 使用CommandHandler处理队列中的下一位
        has_next = await self.command_handler.prepare_next_user_from_queue(
            event, sender_id, f"✅ 已结束与用户 {uid} 的对话"
        )
        
        if not has_next:
            yield event.plain_result(f"✅ 已结束与用户 {uid} 的对话\n📋 当前队列为空")

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
        original_text = extract_text_from_message(ob_message)
        
        # 处理消息（添加前后缀或替换为随机文字）
        if add_prefix and self.enable_random_reply and is_pure_text_message(ob_message):
            # 答非所问模式：替换为随机文字
            ob_message = replace_with_random_text(ob_message, self.random_reply_chars)
        elif add_prefix and (self.message_prefix or self.message_suffix):
            # 只对纯文本消息添加前后缀
            if is_pure_text_message(ob_message):
                if self.message_prefix:
                    ob_message = add_prefix_to_message(ob_message, self.message_prefix)
                if self.message_suffix:
                    ob_message = add_suffix_to_message(ob_message, self.message_suffix)
        
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

    @filter.event_message_type(filter.EventMessageType.ALL, priority=0)
    async def silence_mode_filter(self, event: AiocqhttpMessageEvent):
        """活动沉默模式拦截器 - 最高优先级"""
        sender_id = event.get_sender_id()
        message_text = event.message_str.strip()
        
        # 使用SilenceModeManager判断是否应该阻止
        should_block = self.silence_mode_manager.should_block_message(
            sender_id, 
            message_text,
            self.session_map,
            self.selection_map,
            self.blacklist_view_selection
        )
        
        if should_block:
            event.stop_event()
            # 返回空结果，阻止后续处理（包括AstrBot本体的AI）
            return
    
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
        
        # 处理客服查看黑名单时的选择 - 使用MessageRouter
        if sender_id in self.blacklist_view_selection:
            async for result in self.message_router.handle_blacklist_view_selection(event, sender_id, message_text):
                yield result
            event.stop_event()
            return
        
        # 处理用户选择客服
        if sender_id in self.selection_map:
            selection = self.selection_map[sender_id]
            
            if not message_text.isdigit():
                yield event.plain_result("⚠ 请输入数字进行选择")
                event.stop_event()
                return
            
            choice = int(message_text)
            
            if choice == 0:
                # 取消选择
                del self.selection_map[sender_id]
                yield event.plain_result("已取消客服选择")
                event.stop_event()
                return
            
            # 使用CommandHandler处理选择
            success, should_stop, message = await self.command_handler.handle_servicer_selection(
                event, sender_id, choice, selection
            )
            
            if not success:
                # 处理失败（无效选择）
                available_servicers = selection.get("available_servicers", self.servicers_id)
                yield event.plain_result(f"⚠ 无效的选择，请输入 1-{len(available_servicers)} 或 0 取消")
            elif message:
                # 处理成功，显示消息
                yield event.plain_result(message)
            
            if should_stop:
                event.stop_event()
            return
        
        # 客服 → 用户 消息转发 - 使用MessageRouter
        if await self.message_router.route_servicer_to_user(event, sender_id):
            return
        
        # 用户 → 客服 消息转发 - 使用MessageRouter
        if await self.message_router.route_user_to_servicer(event, sender_id):
            return
