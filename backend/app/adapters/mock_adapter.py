import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import List

from app.adapters.base import BaseSentimentAdapter, CommentDTO, VideoDTO

# ── 模拟评论素材库 ─────────────────────────────────────────────────────────────

_HIGH_INTENT_COMMENTS = [
    "怎么买？",
    "多少钱一个",
    "在哪里可以下单",
    "能发链接吗",
    "我想买，怎么联系",
    "有没有优惠活动",
    "可以批发吗",
    "怎么加你微信",
    "求购买链接",
    "这个哪里有卖",
    "价格多少，私信我",
    "想买，求链接",
    "你们店在哪里",
    "可以代购吗",
    "怎么付款",
]

_CONSULT_COMMENTS = [
    "这个效果怎么样",
    "用过的来说说",
    "质量好不好",
    "和XX品牌比哪个好",
    "适合新手吗",
    "有没有教程",
    "售后怎么样",
    "保质期多久",
    "有没有副作用",
    "成分是什么",
]

_NORMAL_COMMENTS = [
    "挺好的",
    "不错不错",
    "哈哈哈",
    "学到了",
    "收藏了",
    "转发了",
    "支持一下",
    "主播说得对",
    "真的假的",
    "厉害了",
    "爱了爱了",
    "绝绝子",
    "真的吗",
    "666",
    "牛牛牛",
]

_JUNK_COMMENTS = [
    "😀😀😀",
    "🎉🎉🎉",
    "。。。",
    "。。。.",
    "嗯",
    "哦",
    "1",
    "dd",
    "ddddd",
    "...",
    "？",
    "啊",
]

_NICKNAMES = [
    "小明同学", "快乐星球", "夜空中最亮的星", "吃瓜群众", "路人甲",
    "大白鲨", "小可爱", "暴走萝莉", "老司机", "佛系少女",
    "追风少年", "柠檬不萌", "懒猫", "阳光少年", "吃货一枚",
]


class MockSentimentAdapter(BaseSentimentAdapter):
    """Mock适配器，用于开发和测试"""

    async def fetch_comments(self, video_id: str, since_time: datetime) -> List[CommentDTO]:
        """返回模拟评论数据，数量5-15条"""
        count = random.randint(5, 15)
        now = datetime.now(timezone.utc)

        # 确保since_time是时区感知的
        if since_time.tzinfo is None:
            since_time = since_time.replace(tzinfo=timezone.utc)

        comments = []
        for i in range(count):
            # 评论时间在since_time之后随机分布
            delta_seconds = (now - since_time).total_seconds()
            if delta_seconds <= 0:
                delta_seconds = 3600  # 默认1小时内
            random_offset = random.uniform(0, delta_seconds)
            comment_time = since_time + timedelta(seconds=random_offset)

            # 按权重选择评论类型
            comment_type = random.choices(
                ["high_intent", "consult", "normal", "junk"],
                weights=[25, 20, 35, 20],
                k=1,
            )[0]

            if comment_type == "high_intent":
                content = random.choice(_HIGH_INTENT_COMMENTS)
            elif comment_type == "consult":
                content = random.choice(_CONSULT_COMMENTS)
            elif comment_type == "normal":
                content = random.choice(_NORMAL_COMMENTS)
            else:
                content = random.choice(_JUNK_COMMENTS)

            comments.append(CommentDTO(
                comment_id=f"mock_{uuid.uuid4().hex[:12]}",
                video_id=video_id,
                user_uid=f"mock_user_{random.randint(10000, 99999)}",
                user_nickname=random.choice(_NICKNAMES),
                content=content,
                comment_time=comment_time,
            ))

        return comments

    async def search_videos_by_keyword(self, keyword: str, page: int, page_size: int) -> List[VideoDTO]:
        """按关键词搜索全网视频，返回模拟搜索结果"""
        # 模拟与关键词相关的视频标题模板
        title_templates = [
            f"关于{keyword}的真实经历分享",
            f"{keyword}到底有没有用？亲测告诉你",
            f"三年{keyword}经验，总结出这几点",
            f"{keyword}成功案例，方法很重要",
            f"别再踩{keyword}的坑了，正确做法是",
            f"{keyword}第一步做什么？新手必看",
            f"专业分析：{keyword}的核心逻辑",
            f"{keyword}一个月后的变化太大了",
            f"大家关心的{keyword}问题，统一回复",
            f"{keyword}避坑指南，收藏不亏",
        ]

        # 模拟账号昵称池
        account_nicknames = [
            "情感导师-林", "挽回专家王老师", "心理情感咨询",
            "婚姻修复站", "情感电台FM", "幸福密码情感",
            "心灵港湾心理", "爱在沟通情感", "暖心情感日记",
            "情感共鸣体",
        ]

        now = datetime.now(timezone.utc)
        videos = []
        # 每页返回page_size条，但随页数递减模拟越往后结果越少
        actual_count = max(0, page_size - (page - 1) * 2)
        if actual_count == 0:
            return []

        for i in range(actual_count):
            # 随机生成账号UID
            account_uid = f"discovered_uid_{random.randint(100000, 999999)}"
            # 发文时间：60%在3天内，40%在3-15天
            if random.random() < 0.6:
                publish_time = now - timedelta(
                    hours=random.randint(1, 72)
                )
            else:
                publish_time = now - timedelta(days=random.randint(4, 15))

            videos.append(VideoDTO(
                video_id=f"search_{keyword}_{page}_{i}_{uuid.uuid4().hex[:8]}",
                title=random.choice(title_templates),
                publish_time=publish_time,
                account_uid=account_uid,
                account_nickname=random.choice(account_nicknames),
                comment_count=random.randint(20, 500),
            ))

        return videos

    async def get_video_list(self, account_uid: str) -> List[VideoDTO]:
        """返回模拟视频列表"""
        video_titles = [
            "【好物推荐】这款神器你一定要试试",
            "新品开箱测评，效果惊艳！",
            "日常分享：最近发现的好东西",
            "粉丝推荐的爆款到了，来看看值不值",
            "手把手教你挑选技巧",
        ]
        now = datetime.now(timezone.utc)
        videos = []
        for i, title in enumerate(video_titles):
            videos.append(VideoDTO(
                video_id=f"mock_video_{account_uid}_{i+1}",
                title=title,
                publish_time=now - timedelta(days=random.randint(1, 30)),
                comment_count=random.randint(10, 500),
            ))
        return videos

    async def fetch_topic_comments(self, topic: str, industry: str, since_time: datetime) -> List[CommentDTO]:
        """按话题/行业范围采集全网评论，返回该领域下的混合评论（大部分无意向，少量有意向）"""
        count = random.randint(8, 20)
        now = datetime.now(timezone.utc)

        if since_time.tzinfo is None:
            since_time = since_time.replace(tzinfo=timezone.utc)

        # 根据话题/行业生成领域相关的日常评论素材（非关键词匹配）
        topic_templates = [
            f"最近看到好多人在聊{topic}，感觉挺有意思的",
            f"有没有人推荐一下{topic}相关的博主",
            f"关于{topic}这个话题，大家有什么看法",
            f"刷到好几个{topic}的视频了，最近很火吗",
            f"{topic}这个行业现在发展怎么样",
            f"朋友最近也在关注{topic}，说挺有前景的",
            f"看了一个{topic}的科普视频，涨知识了",
            f"{topic}方面有什么需要注意的吗",
            f"对{topic}不太了解，有懂行的说说",
            f"感觉{topic}越来越受关注了",
        ]

        comments = []
        for i in range(count):
            delta_seconds = (now - since_time).total_seconds()
            if delta_seconds <= 0:
                delta_seconds = 3600
            random_offset = random.uniform(0, delta_seconds)
            comment_time = since_time + timedelta(seconds=random_offset)

            # 大部分是普通/闲聊评论，少量有意向（体现AI识别价值）
            comment_type = random.choices(
                ["topic", "normal", "junk", "high_intent", "consult"],
                weights=[35, 30, 15, 10, 10],
                k=1,
            )[0]

            if comment_type == "topic":
                content = random.choice(topic_templates)
            elif comment_type == "high_intent":
                content = random.choice(_HIGH_INTENT_COMMENTS)
            elif comment_type == "consult":
                content = random.choice(_CONSULT_COMMENTS)
            elif comment_type == "junk":
                content = random.choice(_JUNK_COMMENTS)
            else:
                content = random.choice(_NORMAL_COMMENTS)

            comments.append(CommentDTO(
                comment_id=f"mock_topic_{uuid.uuid4().hex[:12]}",
                video_id=f"mock_topic_video_{random.randint(1000, 9999)}",
                user_uid=f"mock_user_{random.randint(10000, 99999)}",
                user_nickname=random.choice(_NICKNAMES),
                content=content,
                comment_time=comment_time,
            ))

        return comments
