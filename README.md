# AI直播带货口播助手

基于 PyQt6 的抖音直播带货桌面工具：AI 生成口播话术 + 自动语音播报 + 弹幕互动回复 + 小黄车商品管理，一套流程跑完直播间带货。

## 功能

| 模块 | 说明 |
|---|---|
| 播报主控 | 话术自动循环播报，全局热键：`Ctrl+Shift+P` 暂停/继续、`Ctrl+Shift+S` 跳过、`Ctrl+Shift+X` 停止 |
| 商品管理 | 拉取直播间小黄车商品（HTTP / 内嵌浏览器双通道），支持手动添加、自动生成卖点 |
| 话术库 | 调用 AI 模型按商品生成口播话术，支持编辑、导入导出 |
| 弹幕互动 | 抖音直播弹幕 wss 实时连接（含签名），进场欢迎、点赞/关注感谢、关键词自动回复 |
| 定时任务 | 定时循环播报、整点报时、自定义 AI 提示词 |
| 数字人 | 数字人形象驱动（实验） |
| 语音配置 | edge-tts 音色/语速/音量，支持变声 |
| 模型配置 | OpenAI 兼容接口多模型管理：本地 Ollama、DeepSeek、通义千问、豆包、Moonshot 等预设 |

## 技术栈

- Python 3.10+ / PyQt6
- edge-tts + miniaudio + pygame（语音合成与播放）
- openai（OpenAI 兼容协议，对接 Ollama 及各家云模型）
- websockets + protobuf（抖音直播弹幕协议）
- aiohttp / openpyxl / pynput

## 安装与运行

```bash
# 1. 安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 启动
python main.py
```

本地模型（可选）：

```bash
ollama pull qwen2.5:7b   # 模型存储位置可用 OLLAMA_MODELS 环境变量指定
```

## 目录结构

```
├── main.py               # 入口 + 全局 QSS 设计系统
├── core/                 # 核心逻辑：AI引擎、抖音连接器、弹幕签名、TTS
│   └── js/               # wss 签名脚本（Node.js 运行）
├── ui/                   # PyQt6 界面：主控/商品/话术/弹幕/定时/模型配置等面板
├── models/               # 配置数据模型
├── database/             # 数据库层
├── assets/               # 图标资源
└── tests/                # 探针与联调脚本
```

## 说明

- `config/`（settings.json、data.db）、`logs/`、`output_audio/`、`digital_human/` 等运行数据**不入库**，首次运行自动生成默认配置。
- 弹幕互动与小黄车拉取需要抖音登录态：在应用内嵌浏览器中扫码登录一次即可。
- 弹幕 wss 签名依赖 Node.js 环境（`core/js/sign.js`）。
