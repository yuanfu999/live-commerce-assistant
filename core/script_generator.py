"""话术生成引擎 - AI生成商品讲解话术"""
import re
import time
from typing import List
from models.product import Product
from models.script import Script, SCRIPT_TYPE_MAIN, STYLE_PROMO, STYLE_REVIEW, STYLE_PARENTING
from core.ai_engine import AIEngine


# 风格对应的系统提示
STYLE_PROMPTS = {
    STYLE_PROMO: "你是一个热情洋溢的直播带货主播，语气夸张、有感染力，常用'家人们''冲''绝了'等口语化表达。",
    STYLE_REVIEW: "你是一个专业的商品测评师，语气理性、专业，从材质、安全性、性价比等多维度分析商品。",
    STYLE_PARENTING: "你是一个育儿专家兼带货主播，主要面向宝妈群体，强调教育价值、安全性、对孩子成长的好处。",
}


class ScriptGenerator:
    """话术生成器"""

    def __init__(self, ai_engine: AIEngine):
        self.ai_engine = ai_engine

    def generate_product_scripts(
        self,
        product: Product,
        count: int = 5,
        style: str = STYLE_PROMO,
        custom_style_desc: str = "",
        progress_callback=None
    ) -> List[Script]:
        """为商品生成多条讲解话术。progress_callback(msg)用于上报生成进度。"""

        def _report(msg):
            if progress_callback:
                try:
                    progress_callback(msg)
                except Exception:
                    pass

        _report("正在生成 " + str(count) + " 条话术（AI创作中，约10-30秒）...")

        is_custom = (style == "自定义" and custom_style_desc)
        style_prompt = custom_style_desc if is_custom else STYLE_PROMPTS.get(style, "")

        # 目标字数：从自定义提示词提取（如“1000字左右”→1000）；标准风格默认80-150字
        target = self._extract_target_length(custom_style_desc) if is_custom else 120

        if target:
            min_len = max(50, int(target * 0.7))
            length_req = "长度" + str(target) + "字左右（不少于" + str(min_len) + "字，过短会被系统拒绝）"
            user_len = "每条" + str(target) + "字左右"
        else:
            # 自定义提示词未写明具体字数时，让AI严格遵循用户要求
            length_req = "严格按照上方要求中指定的长度来写，内容必须充实完整（过短会被系统拒绝）"
            user_len = "长度严格按照上方要求"

        system_prompt = f"""{style_prompt}
你正在抖音直播间带货。请根据商品信息生成讲解话术。
【硬性要求】
1. 每条话术必须是一段连贯完整的话，{length_req}
2. 每条要有完整结构：开场吸引→卖点讲解→使用场景→引导点击小黄车下单
3. 每条的角度和表达方式不同（功能/价格/场景/情感/对比）
4. 口语化、有感染力，适合朗读播报，多用短句和语气词
5. 直接输出话术内容，用数字编号（1. 2. 3. ...），不要任何标题或解释

【示例（仅参考结构，不要照抄内容，长度以上方硬性要求为准）】
1. 家人们看过来！今天这款宝贝真的太值了！专为有需要的朋友设计，材质安全做工精良，细节处处到位，买过的都说好。现在直播间下单只要这个价，比线下便宜太多了！库存真的不多了，想要的赶紧点击下方小黄车，手慢无哦！
"""

        user_prompt = f"""请为以下商品写{count}条不同的直播带货讲解话术（{user_len}）：

商品名称：{product.name}
价格：{product.price}
特点/卖点：{product.feature}
适合人群：{product.target_audience}
好处/价值：{product.benefit}
补充信息：{product.extra_notes or '无'}
"""

        # 长文本生成需要更大的输出上限，避免被截断
        max_tokens = min(max(2000, (target or 150) * count * 2), 8192)

        response = self.ai_engine.chat(user_prompt, system_prompt=system_prompt, max_tokens=max_tokens)
        scripts = self._parse_scripts(response, product, style)

        # 首次生成全部被过滤（都太短）时，用更强约束重试一次
        if not scripts:
            _report("首批话术未达长度要求，正在重新生成...")
            retry_len = ("写满" + str(target) + "字左右" if target else "写够要求的长度")
            retry_prompt = user_prompt + (
                "\n\n【重要提醒】上次生成的话术都太短被系统拒绝了。"
                "这次每条必须" + retry_len + "，内容充实具体，"
                "包含卖点讲解、使用场景描述和促单引导，缺一不可。"
            )
            try:
                retry_resp = self.ai_engine.chat(retry_prompt, system_prompt=system_prompt, max_tokens=max_tokens)
                scripts = self._parse_scripts(retry_resp, product, style)
            except Exception:
                pass

        # 话术普遍偏短时，自动扩写到目标长度
        expand_threshold = int(target * 0.6) if (target and target > 200) else 60
        if scripts and self._avg_length(scripts) < expand_threshold:
            _report("正在扩写充实话术内容...")
            numbered = "\n".join(f"{i + 1}. {s.content}" for i, s in enumerate(scripts))
            expand_len = ("把每一条扩写到" + str(target) + "字左右") if target else "把每一条扩写到80-150字"
            expand_prompt = (
                "以下直播话术太短了，请" + expand_len + "，"
                "增加卖点细节、使用场景描述和促单引导，保持原有风格和角度不变。"
                "直接输出扩写后的话术，用数字编号：\n\n" + numbered
            )
            try:
                expanded = self.ai_engine.chat(expand_prompt, system_prompt=system_prompt, max_tokens=max_tokens)
                expanded_scripts = self._parse_scripts(expanded, product, style)
                # 只有扩写后确实更长才采用
                if expanded_scripts and self._avg_length(expanded_scripts) > self._avg_length(scripts):
                    scripts = expanded_scripts
            except Exception:
                pass  # 扩写失败则保留原话术

        _report("生成完成，共 " + str(min(len(scripts), count)) + " 条")
        return scripts[:count]

    @staticmethod
    def _avg_length(scripts: List[Script]) -> float:
        """计算话术平均长度"""
        return sum(len(s.content) for s in scripts) / len(scripts)

    @staticmethod
    def _extract_target_length(text: str):
        """从自定义提示词中提取目标字数（如“1000字左右”→1000），未找到返回None"""
        m = re.search(r'(\d{2,})\s*字', text or "")
        if m:
            return int(m.group(1))
        return None

    def _parse_scripts(self, response: str, product: Product, style: str) -> List[Script]:
        """解析AI响应为话术列表（按编号分块，支持一条话术跨多行）"""
        scripts = []
        # 按编号分块：匹配行首的 1. / 1、 / 1） / 1) / 1． 等格式
        blocks = re.split(r'\n\s*(?=\d+\s*[.、）)．])', response.strip())
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            # 去掉开头编号
            block = re.sub(r'^\d+\s*[.、）)．]\s*', '', block)
            # 合并多行为一条话术
            content = ' '.join(line.strip() for line in block.split('\n') if line.strip())
            # 过滤过短话术（低于50字视为不完整）
            if len(content) >= 50:
                scripts.append(Script(
                    product_id=product.id,
                    script_type=SCRIPT_TYPE_MAIN,
                    content=content,
                    style=style,
                    created_at=time.time(),
                ))
        return scripts

    def generate_transition(self, product_from: Product, product_to: Product) -> str:
        """生成商品切换过渡话术"""
        prompt = f"""写一句直播带货时从"{product_from.name}"切换到"{product_to.name}"的过渡话术，20-40字，自然流畅，口语化。只输出话术内容。"""
        return self.ai_engine.chat(prompt, temperature=0.8).strip()

    def generate_danmaku_reply(self, danmaku_text: str, username: str, current_product: Product = None) -> str:
        """根据弹幕内容生成回复"""
        context = ""
        if current_product:
            context = f"\n当前正在讲解的商品：{current_product.name}，价格{current_product.price}，特点：{current_product.feature}"

        prompt = f"""你是抖音直播间主播。有观众"{username}"发了弹幕："{danmaku_text}"{context}
请用亲切、简短的语气回复（20-50字），适合口头播报。只输出回复内容。"""
        return self.ai_engine.chat(prompt, temperature=0.7).strip()

    def generate_opening(self) -> str:
        """生成开场白"""
        prompt = "写一段抖音直播带货的开场白，50-80字，热情欢迎观众，提醒点关注。只输出话术内容。"
        return self.ai_engine.chat(prompt, temperature=0.8).strip()

    def generate_urge(self, product: Product) -> str:
        """生成促单话术"""
        prompt = f"""为"{product.name}"（价格{product.price}）写一句促单话术，30-50字，制造紧迫感（库存有限/限时优惠），引导立即下单。只输出话术内容。"""
        return self.ai_engine.chat(prompt, temperature=0.8).strip()
