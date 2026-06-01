"""
人设/风格学习模块 - 从聊天记录学习说话风格
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from collections import Counter

from utils.logger import logger


class StyleLearning:
    """风格学习类"""

    def __init__(self):
        self.chat_history_dir = Path(__file__).parent.parent / "data" / "chat_history"
        self.chat_history_dir.mkdir(parents=True, exist_ok=True)

    def learn_from_file(self, file_path: str) -> Dict:
        """从 TXT 聊天记录文件学习风格"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 解析聊天记录
            messages = self._parse_chat_content(content)

            if not messages:
                logger.warning(f"文件 {file_path} 未解析到有效消息")
                return {}

            # 提取风格特征
            profile = self._extract_style_profile(messages)

            logger.info(f"从 {file_path} 学习到 {len(messages)} 条消息的风格")
            return profile

        except Exception as e:
            logger.error(f"学习风格失败: {e}")
            return {}

    def _parse_chat_content(self, content: str) -> List[Dict]:
        """解析聊天记录内容

        支持多种格式：
        1. 微信导出格式: "2024-01-01 12:00:00 张三"
        2. 自定义格式: "[张三] 消息内容"
        3. 纯对话格式: "张三: 消息内容"
        """
        messages = []
        lines = content.strip().split("\n")

        # 正则模式
        patterns = [
            # 微信导出格式: 2024-01-01 12:00:00 张三
            r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.+?)[\s：:](.+)$",
            # [姓名] 内容
            r"^\[(.+?)\]\s*(.+)$",
            # 姓名: 内容
            r"^(.+?)[:：]\s*(.+)$",
        ]

        current_speaker = None
        current_message = []

        for line in lines:
            line = line.strip()
            if not line:
                if current_speaker and current_message:
                    messages.append({
                        "speaker": current_speaker,
                        "content": "\n".join(current_message)
                    })
                    current_speaker = None
                    current_message = []
                continue

            matched = False
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    # 保存之前的消息
                    if current_speaker and current_message:
                        messages.append({
                            "speaker": current_speaker,
                            "content": "\n".join(current_message)
                        })

                    # 解析新消息
                    groups = match.groups()
                    if len(groups) == 3:  # 微信格式
                        current_speaker = groups[1]
                        current_message = [groups[2]]
                    elif len(groups) == 2:
                        current_speaker = groups[0]
                        current_message = [groups[1]]
                    else:
                        current_speaker = groups[0]
                        current_message = [groups[1]]

                    matched = True
                    break

            if not matched and current_speaker:
                current_message.append(line)

        # 保存最后一条消息
        if current_speaker and current_message:
            messages.append({
                "speaker": current_speaker,
                "content": "\n".join(current_message)
            })

        return messages

    def _extract_style_profile(self, messages: List[Dict]) -> Dict:
        """提取风格特征"""
        if not messages:
            return {}

        # 聚合"我"的消息（假设是第一个说话的人，或者用户指定的名字）
        # 这里简单处理：假设用户是最常见的说话者之一
        speaker_counts = Counter(m["speaker"] for m in messages)
        # 取最常出现的说话者作为"用户"
        user_name = speaker_counts.most_common(1)[0][0]

        user_messages = [
            m["content"] for m in messages
            if m["speaker"] == user_name and m["content"].strip()
        ]

        if not user_messages:
            return {}

        profile = {
            "message_count": len(user_messages),
            "avg_length": sum(len(m) for m in user_messages) / len(user_messages),
            "common_phrases": self._extract_common_phrases(user_messages),
            "emoji_usage": self._extract_emoji_usage(user_messages),
            "punctuation_style": self._extract_punctuation_style(user_messages),
            "tone_indicators": self._extract_tone_indicators(user_messages),
            "sample_messages": user_messages[:10],  # 保存示例
        }

        return profile

    def _extract_common_phrases(self, messages: List[str], top_n: int = 20) -> List[str]:
        """提取常用短语"""
        # 简单的短语提取：2-4 字的连续字符
        phrases = []
        for msg in messages:
            # 按标点分割
            parts = re.split(r'[，。！？；：、\s,!?;:]', msg)
            for part in parts:
                part = part.strip()
                if 2 <= len(part) <= 4:
                    phrases.append(part)

        # 统计频率
        phrase_counts = Counter(phrases)
        return [p for p, c in phrase_counts.most_common(top_n)]

    def _extract_emoji_usage(self, messages: List[str]) -> Dict:
        """提取表情使用习惯"""
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # 表情
            "\U0001F300-\U0001F5FF"  # 符号
            "\U0001F680-\U0001F6FF"  # 交通
            "\U0001F700-\U0001F77F"  # 符号
            "\U0001F780-\U0001F7FF"  # 几何
            "\U0001F800-\U0001F8FF"  # 补充
            "\U0001F900-\U0001F9FF"  # 补充符号
            "\U0001FA00-\U0001FA6F"  # 扩展
            "\U0001FA70-\U0001FAFF"  # 符号和图案
            "\U00002702-\U000027B0"  # 符号
            "\U000024C2-\U0001F251"  # 符号
            "]"
        )

        all_emojis = []
        for msg in messages:
            emojis = emoji_pattern.findall(msg)
            all_emojis.extend(emojis)

        emoji_counts = Counter(all_emojis)
        return {
            "total": len(all_emojis),
            "top": [{"emoji": e, "count": c} for e, c in emoji_counts.most_common(10)]
        }

    def _extract_punctuation_style(self, messages: List[str]) -> Dict:
        """提取标点符号风格"""
        period_count = sum(m.count("。") for m in messages)
        exclam_count = sum(m.count("！") + m.count("!") for m in messages)
        question_count = sum(m.count("？") + m.count("?") for m in messages)
        tilde_count = sum(m.count("~") for m in messages)

        total = sum(len(m) for m in messages)
        if total == 0:
            return {}

        return {
            "period_ratio": period_count / total,
            "exclam_ratio": exclam_count / total,
            "question_ratio": question_count / total,
            "tilde_ratio": tilde_count / total,
            "uses_english_punct": exclam_count > 0 or question_count > 0,
        }

    def _extract_tone_indicators(self, messages: List[str]) -> Dict:
        """提取语气指标"""
        # 笑声模式
        laugh_patterns = [r"哈哈+", r"呵呵+", r"嘻嘻+", r"嘿嘿+", r"哈哈哈"]
        laugh_count = 0
        for msg in messages:
            for pattern in laugh_patterns:
                if re.search(pattern, msg):
                    laugh_count += 1
                    break

        # 称呼语
        polite_words = ["请", "谢谢", "麻烦", "帮忙", "请问"]
        polite_count = sum(sum(msg.count(w) for w in polite_words) for msg in messages)

        # 语气词
        modal_words = ["嘛", "呢", "呀", "哦", "啊", "呗"]
        modal_count = sum(sum(msg.count(w) for w in modal_words) for msg in messages)

        return {
            "laugh_frequency": laugh_count / len(messages) if messages else 0,
            "politeness_score": polite_count / len(messages) if messages else 0,
            "modal_particle_score": modal_count / len(messages) if messages else 0,
        }

    def generate_system_prompt(self, profile: Dict, base_name: str = "用户") -> str:
        """根据风格档案生成系统提示词"""
        if not profile:
            return f"你是{base_name}，请用自然、友好的语言回复。"

        prompt_parts = [f"你是{base_name}，请模仿以下说话风格回复消息：\n"]

        # 添加语气描述
        tone = profile.get("tone_indicators", {})
        if tone.get("laugh_frequency", 0) > 0.2:
            prompt_parts.append("- 经常使用笑声表达（哈哈、呵呵等）")
        if tone.get("politeness_score", 0) > 0.1:
            prompt_parts.append("- 比较有礼貌，经常使用请、谢谢等词")
        if tone.get("modal_particle_score", 0) > 0.3:
            prompt_parts.append("- 经常使用语气词（嘛、呢、呀、哦等）")

        # 添加标点风格
        punct = profile.get("punctuation_style", {})
        if punct.get("exclam_ratio", 0) > 0.02:
            prompt_parts.append("- 经常使用感叹号表达情绪")

        # 添加常用短语
        common = profile.get("common_phrases", [])
        if common:
            prompt_parts.append(f"- 常用短语：{', '.join(common[:5])}")

        # 添加表情使用
        emoji = profile.get("emoji_usage", {})
        if emoji.get("total", 0) > 0:
            top_emoji = [e["emoji"] for e in emoji.get("top", [])[:3]]
            prompt_parts.append(f"- 常用表情：{' '.join(top_emoji)}")

        # 添加示例
        samples = profile.get("sample_messages", [])
        if samples:
            prompt_parts.append("\n参考以下回复示例：")
            for i, sample in enumerate(samples[:3], 1):
                prompt_parts.append(f"{i}. {sample[:50]}...")

        prompt_parts.append("\n请保持这种风格自然地回复。")

        return "\n".join(prompt_parts)

    def save_profile(self, contact_name: str, profile: Dict) -> str:
        """保存风格档案"""
        profile_file = self.chat_history_dir / f"{contact_name}_style.json"
        with open(profile_file, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        logger.info(f"风格档案已保存到: {profile_file}")
        return str(profile_file)

    def load_profile(self, contact_name: str) -> Optional[Dict]:
        """加载风格档案"""
        profile_file = self.chat_history_dir / f"{contact_name}_style.json"
        if profile_file.exists():
            with open(profile_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None


# 全局风格学习实例
style_learning = StyleLearning()
