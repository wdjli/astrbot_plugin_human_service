
<div align="center">

![:name](https://count.getloli.com/@astrbot_plugin_human_service?name=astrbot_plugin_human_service&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

# astrbot_plugin_human_service

_✨ [astrbot](https://github.com/AstrBotDevs/AstrBot) 人工客服插件 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-4.3.3-orange.svg)](https://github.com/Soulter/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-Zhalslar-blue)](https://github.com/Zhalslar)

</div>

## 🤝 介绍

让bot转人工\转人机，管理员接入对话\结束对话

## 📦 安装

- 可以直接在astrbot的插件市场搜索astrbot_plugin_human_service，点击安装，耐心等待安装完成即可
- 若是安装失败，可以尝试直接克隆源码：

```bash
# 克隆仓库到插件目录
cd /AstrBot/data/plugins
git clone https://github.com/Zhalslar/astrbot_plugin_human_service

# 控制台重启AstrBot
```

## ⌨️ 使用说明

### 命令表

|     命令      |                    说明                    |      使用者      |
|:-------------:|:---------------------------------------------:|:----------------:|
| `/转人工`     | 用户请求转人工。如果配置了多个客服且启用了客服选择功能，会显示客服列表供用户选择；否则会通知所有客服等待接入。 | 用户 |
| `/转人机`     | 用户取消转人工请求或客服选择，结束等待状态。     | 用户 |
| `/接入对话`   | 客服接入用户的对话，开始人工服务。通过回复用户的请求消息使用此命令。 | 客服 |
| `/拒绝接入`   | 客服拒绝用户的接入请求。通过回复用户的请求消息使用此命令。 | 客服 |
| `/导出记录`   | 导出当前会话的聊天记录（需启用聊天记录功能）。以QQ聊天记录格式发送。 | 客服 |
| `/结束对话`   | 客服结束当前对话，关闭会话。                   | 客服 |

### 配置说明

插件支持以下配置项（在插件配置页面设置）：

1. **客服QQ号列表** (`servicers_id`)
   - 格式：`["123456789", "987654321", "555666777"]`
   - 说明：填写客服的QQ号列表
   - 如果不填，默认使用全局配置中的管理员作为客服

2. **启用客服选择功能** (`enable_servicer_selection`)
   - 类型：布尔值（true/false）
   - 默认：true
   - 说明：当有多个客服时，是否让用户选择对接哪个客服

3. **启用聊天记录功能** (`enable_chat_history`)
   - 类型：布尔值（true/false）
   - 默认：false
   - 说明：开启后，客服可以使用 `/导出记录` 命令导出当前会话的聊天记录

### 使用流程

#### 单客服模式
1. 用户发送 `/转人工`
2. 系统通知客服有用户请求
3. 客服使用 `/接入对话` 接入
4. 开始双向消息转发
5. 客服使用 `/结束对话` 结束会话

#### 多客服选择模式
1. 用户发送 `/转人工`
2. 系统显示客服列表，用户回复序号选择客服
3. 系统通知被选中的客服
4. 客服使用 `/接入对话` 接入
5. 开始双向消息转发
6. 客服使用 `/结束对话` 结束会话

**注意**：用户在任何阶段都可以使用 `/转人机` 取消请求

### 示例图

![c4c33c6e4ea7687165880e0c55eacd2](https://github.com/user-attachments/assets/4024faae-3932-4c63-9ceb-b72f785fbb03)

## 👥 贡献指南

- 🌟 Star 这个项目！（点右上角的星星，感谢支持！）
- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 📌 注意事项

- 想第一时间得到反馈的可以来作者的插件反馈群（QQ群）：460973561（不点star不给进）
