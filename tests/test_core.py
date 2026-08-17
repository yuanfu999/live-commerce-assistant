"""核心逻辑自动化回归测试

运行方式（项目根目录）：
    python -m pytest tests/test_core.py -v

覆盖模块：
    - script_generator  话术解析 / 自动扩写
    - douyin_connector  商品接口解析 / room_id提取
    - broadcast_engine  跳过机制 / 克隆降级
    - voice_clone_engine 参考音频状态
    - db_manager        商品&话术CRUD
"""
import os
import sys
import time
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# 把项目根目录加入 import 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.product import Product
from models.script import Script, SCRIPT_TYPE_MAIN, STYLE_PROMO
from core.script_generator import ScriptGenerator
from core.douyin_connector import DouyinConnector
from core.broadcast_engine import BroadcastEngine
from core.voice_clone_engine import VoiceCloneEngine
from database.db_manager import DBManager


def make_product(**kwargs):
    defaults = dict(
        id=1, name="幼儿启蒙学英语", price="29.8元",
        feature="字母/单词/对话/互动游戏", target_audience="2-8岁宝宝",
        benefit="边玩边学，赢在起跑线", commission="20%",
        extra_notes="", scripts_per_round=5, enabled=1,
        created_at=time.time(),
    )
    defaults.update(kwargs)
    return Product(**defaults)


# ============================================================
# 1. 话术解析
# ============================================================
class TestParseScripts(unittest.TestCase):
    def setUp(self):
        self.gen = ScriptGenerator(ai_engine=MagicMock())
        self.product = make_product()

    def test_normal_numbered(self):
        resp = (
            "1. 家人们看过来！今天这款幼儿启蒙学英语真的太值了，专为2到8岁宝宝设计，涵盖字母单词日常对话，"
            "还有互动小游戏，孩子边玩边学根本停不下来，现在下单只要二十九块八，赶紧点击下方小黄车！\n"
            "2. 宝妈们注意了！孩子的英语启蒙千万不能等，这套教材从兴趣入手，画面精美发音标准，"
            "每天十分钟轻松磨耳朵，比报班便宜太多了，库存不多了，想要的家人们抓紧时间，手慢无哦！"
        )
        scripts = self.gen._parse_scripts(resp, self.product, STYLE_PROMO)
        self.assertEqual(len(scripts), 2)
        self.assertGreaterEqual(len(scripts[0].content), 50)
        self.assertTrue(scripts[0].content.startswith("家人们"))

    def test_multiline_merged(self):
        """一条话术跨多行时应被合并为一条"""
        resp = (
            "1. 家人们看过来！\n今天这款幼儿启蒙学英语真的太值了，\n"
            "专为2到8岁宝宝设计，涵盖字母单词日常对话，孩子边玩边学根本停不下来，现在下单只要二十九块八！\n"
            "2. 宝妈们注意了！孩子的英语启蒙千万不能等，这套教材从兴趣入手，画面精美发音标准，"
            "每天十分钟轻松磨耳朵，比报班便宜太多了，库存不多了，想要的家人们抓紧时间，手慢无哦！"
        )
        scripts = self.gen._parse_scripts(resp, self.product, STYLE_PROMO)
        self.assertEqual(len(scripts), 2)
        self.assertIn("家人们看过来", scripts[0].content)

    def test_filter_too_short(self):
        """低于50字的话术应被过滤"""
        resp = (
            "1. 太短了\n"
            "2. 这条话术足够长，家人们看过来，今天这款宝贝真的超值，专为有需要的朋友精心设计，"
            "材质安全做工精良，现在下单享受直播间专属优惠，赶紧点击下方小黄车抢购吧，手慢无哦！"
        )
        scripts = self.gen._parse_scripts(resp, self.product, STYLE_PROMO)
        self.assertEqual(len(scripts), 1)
        self.assertIn("足够长", scripts[0].content)

    def test_various_separators(self):
        """支持 . 、 ） ) ． 等多种编号分隔符"""
        # 用程序生成确保 >=50 字的文本，避免被长度阈值过滤
        long_text = ("这是一条足够长的测试话术用来验证各种编号分隔符都能被正确解析" * 2)[:60]
        self.assertGreaterEqual(len(long_text), 50)
        for sep in [".", "、", "）", ")", "．"]:
            resp = f"1{sep} {long_text}\n2{sep} {long_text}"
            scripts = self.gen._parse_scripts(resp, self.product, STYLE_PROMO)
            self.assertEqual(len(scripts), 2, f"分隔符 {sep!r} 解析失败")
            self.assertFalse(scripts[0].content.startswith("1"))

    def test_avg_length(self):
        scripts = [Script(content="a" * 100), Script(content="b" * 60)]
        self.assertAlmostEqual(ScriptGenerator._avg_length(scripts), 80.0)


# ============================================================
# 2. 自动扩写
# ============================================================
class TestAutoExpand(unittest.TestCase):
    def test_expand_triggered_when_short(self):
        """首次生成普遍太短时(50-59字)，应触发二次扩写并采用更长结果"""
        # 构造 55 字话术：能通过50字过滤，但平均<60触发扩写
        short_line = ("家人们快看过来呀今天这款宝贝真的非常不错特别值得入手现在下单有优惠" * 3)[:55]
        short_resp = f"1. {short_line}\n2. {short_line}"
        long_text = (
            "家人们看过来！今天这款幼儿启蒙学英语真的太值了，专为2到8岁宝宝设计，涵盖字母单词日常对话，"
            "还有互动小游戏，孩子边玩边学根本停不下来，现在下单只要二十九块八，赶紧点击下方小黄车！"
        )
        long_resp = f"1. {long_text}\n2. {long_text}"

        ai = MagicMock()
        # 第一次返回短话术，第二次（扩写）返回长话术
        ai.chat.side_effect = [short_resp, long_resp]
        gen = ScriptGenerator(ai_engine=ai)
        scripts = gen.generate_product_scripts(make_product(), count=2, style=STYLE_PROMO)

        self.assertEqual(ai.chat.call_count, 2, "短话术应触发二次扩写")
        self.assertGreaterEqual(len(scripts[0].content), 80)

    def test_retry_when_all_filtered(self):
        """首次生成全部<50字被过滤时，应用更强约束重试一次"""
        too_short_resp = "1. 太短\n2. 也很短"
        long_text = (
            "家人们看过来！今天这款幼儿启蒙学英语真的太值了，专为2到8岁宝宝设计，涵盖字母单词日常对话，"
            "还有互动小游戏，孩子边玩边学根本停不下来，现在下单只要二十九块八，赶紧点击下方小黄车！"
        )
        retry_resp = f"1. {long_text}\n2. {long_text}"

        ai = MagicMock()
        ai.chat.side_effect = [too_short_resp, retry_resp]
        gen = ScriptGenerator(ai_engine=ai)
        scripts = gen.generate_product_scripts(make_product(), count=2, style=STYLE_PROMO)

        self.assertEqual(ai.chat.call_count, 2, "全部被过滤应触发重试")
        self.assertEqual(len(scripts), 2)

    def test_no_expand_when_long_enough(self):
        """首次生成足够长时，不应触发二次扩写"""
        long_text = (
            "家人们看过来！今天这款幼儿启蒙学英语真的太值了，专为2到8岁宝宝设计，涵盖字母单词日常对话，"
            "还有互动小游戏，孩子边玩边学根本停不下来，现在下单只要二十九块八，赶紧点击下方小黄车！"
        )
        long_resp = f"1. {long_text}\n2. {long_text}"
        ai = MagicMock()
        ai.chat.return_value = long_resp
        gen = ScriptGenerator(ai_engine=ai)
        scripts = gen.generate_product_scripts(make_product(), count=2, style=STYLE_PROMO)

        self.assertEqual(ai.chat.call_count, 1, "话术足够长不应触发扩写")
        self.assertEqual(len(scripts), 2)


# ============================================================
# 3. 商品接口解析
# ============================================================
class TestParsePromotions(unittest.TestCase):
    def test_standard_structure(self):
        data = {"data": {"promotions": [
            {"title": "幼儿启蒙学英语", "price": 2980, "cover": "http://img/1.jpg"},
            {"title": "儿童磁力积木", "price": 4900, "cover": "http://img/2.jpg"},
        ]}, "status_code": 0}
        products = DouyinConnector._parse_promotions_response(data)
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["name"], "幼儿启蒙学英语")
        self.assertEqual(products[0]["price"], "29.8元")
        self.assertEqual(products[1]["index"], 2)

    def test_nested_product_field(self):
        """商品信息在 item.product 中"""
        data = {"data": {"promotions": [
            {"product": {"title": "测试商品", "min_price": 1999, "img": "http://img/x.jpg"}},
        ]}}
        products = DouyinConnector._parse_promotions_response(data)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["name"], "测试商品")
        self.assertEqual(products[0]["price"], "20.0元")

    def test_alternative_keys(self):
        """兼容 products / product_list 字段"""
        data = {"data": {"products": [{"name": "兼容商品", "price": "99"}]}}
        products = DouyinConnector._parse_promotions_response(data)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["name"], "兼容商品")

    def test_empty_and_invalid(self):
        self.assertEqual(DouyinConnector._parse_promotions_response({}), [])
        self.assertEqual(DouyinConnector._parse_promotions_response({"data": {}}), [])
        self.assertEqual(DouyinConnector._parse_promotions_response([]), [])

    def test_price_format(self):
        """价格分转元"""
        data = {"data": {"promotions": [
            {"title": "A", "price": 100},   # 边界：100 不转
            {"title": "B", "price": 101},   # >100 转为 1.0元
        ]}}
        products = DouyinConnector._parse_promotions_response(data)
        self.assertEqual(products[0]["price"], "100元")
        self.assertEqual(products[1]["price"], "1.0元")


# ============================================================
# 4. room_id / author_id 提取
# ============================================================
class TestExtractRoomAuthor(unittest.TestCase):
    def test_room_info_structure(self):
        data = {"app": {"roomInfo": {"room": {
            "id_str": "7667195795443288870",
            "owner": {"id_str": "4095016854358174"},
        }}}}
        rid, aid = DouyinConnector._extract_room_and_author(data)
        self.assertEqual(rid, "7667195795443288870")
        self.assertEqual(aid, "4095016854358174")

    def test_owner_user_id_fallback(self):
        data = {"roomInfo": {"room": {
            "id_str": "1234567890123456", "owner_user_id": 987654321,
        }}}
        rid, aid = DouyinConnector._extract_room_and_author(data)
        self.assertEqual(rid, "1234567890123456")
        self.assertEqual(aid, "987654321")

    def test_deep_nested(self):
        data = {"a": {"b": {"c": {"roomInfo": {"room": {
            "id_str": "1111111111111111", "owner": {"id_str": "2222"},
        }}}}}}
        rid, aid = DouyinConnector._extract_room_and_author(data)
        self.assertEqual(rid, "1111111111111111")

    def test_not_found(self):
        rid, aid = DouyinConnector._extract_room_and_author({"x": {"y": 1}})
        self.assertEqual(rid, "")
        self.assertEqual(aid, "")


# ============================================================
# 5. 播报引擎：跳过机制 + 克隆降级
# ============================================================
def _make_engine(clone_has_ref=False):
    """构造一个带 mock 依赖的 BroadcastEngine（不启动线程）"""
    tts = MagicMock()
    tts.synthesize.return_value = "/tmp/fake.wav"
    tts.play.return_value = 0.1  # 极短播放时长，避免测试阻塞
    db = MagicMock()
    engine = BroadcastEngine(tts_engine=tts, db=db)
    clone = MagicMock()
    clone.has_reference = clone_has_ref
    clone.synthesize.return_value = "/tmp/clone.wav"
    engine.voice_clone_engine = clone
    return engine, tts, clone


class TestBroadcastSkip(unittest.TestCase):
    def test_skip_event_set(self):
        engine, tts, _ = _make_engine()
        engine._skip_event.clear()
        engine.skip_current()
        self.assertTrue(engine._skip_event.is_set())
        tts.stop.assert_called()

    def test_skip_breaks_wait_loop(self):
        """skip 后 _play_text 的等待循环应立即退出而不是跑满时长"""
        engine, tts, _ = _make_engine()
        # play 被调用时模拟用户点击跳过（_play_text 开头会 clear skip_event）
        def play_and_skip(*args, **kwargs):
            engine._skip_event.set()
            return 30.0  # 假装音频很长
        tts.play.side_effect = play_and_skip
        engine._stop_event.clear()
        start = time.time()
        engine._play_text("测试话术内容", "测试商品", "1/1")
        elapsed = time.time() - start
        self.assertLess(elapsed, 5, "skip 应让等待循环立即退出")


class TestCloneFallback(unittest.TestCase):
    def test_fallback_to_tts_when_no_reference(self):
        """克隆引擎无参考音频时应自动降级 TTS，不进入报错循环"""
        engine, tts, clone = _make_engine(clone_has_ref=False)
        engine.use_clone_voice = True
        engine._stop_event.clear()
        engine._skip_event.clear()
        engine._play_text("测试话术", "测试商品", "")
        tts.synthesize.assert_called()
        clone.synthesize.assert_not_called()
        # 降级后应自动关闭克隆开关
        self.assertFalse(engine.use_clone_voice)

    def test_clone_used_when_has_reference(self):
        engine, tts, clone = _make_engine(clone_has_ref=True)
        engine.use_clone_voice = True
        engine._stop_event.clear()
        engine._skip_event.clear()
        engine._play_text("测试话术", "测试商品", "")
        clone.synthesize.assert_called()

    def test_clone_failure_falls_back_to_tts(self):
        """克隆合成抛异常时应降级 TTS 而不是中断"""
        engine, tts, clone = _make_engine(clone_has_ref=True)
        clone.synthesize.side_effect = RuntimeError("GPT-SoVITS服务未启动")
        engine.use_clone_voice = True
        engine._stop_event.clear()
        engine._skip_event.clear()
        engine._play_text("测试话术", "测试商品", "")
        tts.synthesize.assert_called()


# ============================================================
# 6. 参考音频状态检查
# ============================================================
class TestHasReference(unittest.TestCase):
    def test_no_reference(self):
        engine = VoiceCloneEngine()
        self.assertFalse(engine.has_reference)

    def test_reference_not_exists(self):
        engine = VoiceCloneEngine()
        engine._ref_audio_path = "/nonexistent/path/ref.wav"
        self.assertFalse(engine.has_reference)

    def test_reference_exists(self):
        engine = VoiceCloneEngine()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF" + b"\x00" * 100)
            path = f.name
        try:
            engine._ref_audio_path = path
            self.assertTrue(engine.has_reference)
        finally:
            os.unlink(path)


# ============================================================
# 7. 数据库 CRUD
# ============================================================
class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = DBManager(os.path.join(self.tmpdir, "test.db"))

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass

    def test_product_crud(self):
        p = make_product(id=None)
        pid = self.db.add_product(p)
        self.assertGreater(pid, 0)

        products = self.db.get_all_products()
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0].name, "幼儿启蒙学英语")

        products[0].price = "39.9元"
        self.db.update_product(products[0])
        self.assertEqual(self.db.get_all_products()[0].price, "39.9元")

        self.db.delete_product(pid)
        self.assertEqual(len(self.db.get_all_products()), 0)

    def test_script_crud_and_count(self):
        p = make_product(id=None)
        pid = self.db.add_product(p)

        scripts = [
            Script(product_id=pid, script_type=SCRIPT_TYPE_MAIN,
                   content=f"话术内容{i}", style=STYLE_PROMO, created_at=time.time())
            for i in range(3)
        ]
        self.db.add_scripts_batch(scripts)
        fetched = self.db.get_scripts_by_product(pid, SCRIPT_TYPE_MAIN)
        self.assertEqual(len(fetched), 3)

        sid = fetched[0].id
        self.db.update_script_content(sid, "更新后的话术")
        self.assertEqual(
            self.db.get_scripts_by_product(pid, SCRIPT_TYPE_MAIN)[0].content,
            "更新后的话术"
        )

        self.db.increment_play_count(sid)  # 不抛异常即可
        self.db.delete_script(sid)
        self.assertEqual(len(self.db.get_scripts_by_product(pid, SCRIPT_TYPE_MAIN)), 2)

    def test_script_length_validation(self):
        """验证生成的话术满足长度要求（解析层已过滤<50字）"""
        gen = ScriptGenerator(ai_engine=MagicMock())
        resp = "\n".join(
            f"{i}. 这是一条编号为{i}的足够长的测试话术内容，需要超过五十个字符才能被系统接受，"
            f"所以我在这里填充足够的文字来确保它通过长度校验。"
            for i in range(1, 6)
        )
        scripts = gen._parse_scripts(resp, make_product(), STYLE_PROMO)
        self.assertEqual(len(scripts), 5)
        for s in scripts:
            self.assertGreaterEqual(len(s.content), 50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
