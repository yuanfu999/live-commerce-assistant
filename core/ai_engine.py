"""AI引擎 - 多模型后端统一调用"""
from typing import List, Optional
from openai import OpenAI
from models.config import ModelConfig


class AIEngine:
    """AI模型调用引擎，支持多种OpenAI兼容后端"""

    def __init__(self):
        self._client: Optional[OpenAI] = None
        self._model_name: str = ""
        self._current_config: Optional[ModelConfig] = None

    def set_model(self, config: ModelConfig):
        """设置当前使用的模型"""
        self._current_config = config
        self._model_name = config.model_name
        self._client = OpenAI(
            api_key=config.api_key or "no-key",
            base_url=config.base_url,
        )

    def test_connection(self, config: ModelConfig) -> tuple[bool, str]:
        """测试模型连接是否正常"""
        try:
            client = OpenAI(
                api_key=config.api_key or "no-key",
                base_url=config.base_url,
            )
            models = client.models.list()
            data = getattr(models, "data", None)
            if not data:
                return False, (
                    "连接成功，但服务端没有已安装的模型。\n"
                    "如果是本地Ollama，请先拉取模型：ollama pull " + (config.model_name or "qwen2.5:7b")
                )
            model_list = [m.id for m in data[:5]]
            return True, f"连接成功！可用模型: {', '.join(model_list)}"
        except Exception as e:
            return False, f"连接失败: {str(e)}"

    def chat(self, prompt: str, system_prompt: str = None, temperature: float = 0.9, max_tokens: int = None) -> str:
        """发送对话请求。max_tokens控制最大输出长度（生成长文本时需调大，避免被截断）"""
        if not self._client:
            raise RuntimeError("未配置AI模型，请先在模型配置页面设置")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs = {
            "model": self._model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    @property
    def current_model_name(self) -> str:
        if self._current_config:
            return f"{self._current_config.name} ({self._current_config.model_name})"
        return "未配置"
