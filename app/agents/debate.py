from __future__ import annotations

from collections import defaultdict

import numpy as np

from app.models.schemas import DebateRound, MasterOpinion
from app.services.llm_client import LLMClient, LLMMessage


class MAADDebate:
    style_distance_threshold = 0.42
    max_turns_per_master = 3
    max_participants = 3

    def __init__(self) -> None:
        self.llm = LLMClient()

    def run(self, opinions: list[MasterOpinion]) -> list[DebateRound]:
        grouped: dict[str, list[MasterOpinion]] = defaultdict(list)
        for opinion in opinions:
            grouped[opinion.symbol].append(opinion)

        debates: list[DebateRound] = []
        for symbol, symbol_opinions in grouped.items():
            participants = self._select_participants(symbol_opinions)
            if len(participants) < 2:
                continue
            transcript: list[str] = []
            for turn_index in range(self.max_turns_per_master):
                ordered = self._speaker_order(participants, turn_index)
                for speaker in ordered:
                    opponent = self._strongest_opponent(speaker, participants)
                    style_distance = self._style_distance(speaker, opponent)
                    round_item = self._debate_turn(turn_index, speaker, opponent, style_distance, transcript)
                    debates.append(round_item)
                    self._apply_revision(speaker, round_item)
                    transcript.append(f"{speaker.master}: {round_item.argument}")
        return debates

    def _select_participants(self, opinions: list[MasterOpinion]) -> list[MasterOpinion]:
        scores = np.array([item.score for item in opinions], dtype=float)
        mean_score = float(scores.mean())
        candidates: dict[str, tuple[MasterOpinion, float]] = {}
        for opinion in opinions:
            max_style_distance = max((self._style_distance(opinion, other) for other in opinions if other.master != opinion.master), default=0)
            action_pressure = 0.18 if opinion.action != self._majority_action(opinions) else 0
            trigger = max_style_distance * 0.45 + abs(opinion.score - mean_score) * 0.4 + opinion.confidence * 0.1 + action_pressure
            if max_style_distance >= self.style_distance_threshold or action_pressure > 0 or abs(opinion.score - mean_score) >= 0.08:
                candidates[opinion.master] = (opinion, trigger)
        if len(candidates) < 2:
            ranked = sorted(opinions, key=lambda item: abs(item.score - mean_score) + item.confidence * 0.2, reverse=True)
            return ranked[:2]
        return [item for item, _ in sorted(candidates.values(), key=lambda pair: pair[1], reverse=True)[: self.max_participants]]

    def _speaker_order(self, participants: list[MasterOpinion], turn_index: int) -> list[MasterOpinion]:
        ordered = sorted(
            participants,
            key=lambda item: ((item.revised_confidence or item.confidence), abs((item.revised_score or item.score) - 0.5)),
            reverse=True,
        )
        shift = turn_index % len(ordered)
        return ordered[shift:] + ordered[:shift]

    def _strongest_opponent(self, speaker: MasterOpinion, participants: list[MasterOpinion]) -> MasterOpinion:
        return max(
            [item for item in participants if item.master != speaker.master],
            key=lambda item: abs((item.revised_score or item.score) - (speaker.revised_score or speaker.score)) + self._style_distance(speaker, item) * 0.35,
        )

    def _majority_action(self, opinions: list[MasterOpinion]) -> str:
        counts = {"buy": 0, "hold": 0, "sell": 0}
        for opinion in opinions:
            counts[opinion.action] += 1
        return max(counts, key=counts.get)

    def _debate_turn(
        self,
        turn_index: int,
        speaker: MasterOpinion,
        opponent: MasterOpinion,
        style_distance: float,
        transcript: list[str],
    ) -> DebateRound:
        attack_strength = self._attack_strength(speaker, opponent, style_distance, transcript)
        defense_strength = self._defense_strength(speaker, opponent, transcript)
        confidence_delta = self._confidence_delta(attack_strength, defense_strength, speaker)
        factor_delta = self._factor_delta(speaker, attack_strength, defense_strength)
        revised_score = float(np.clip((speaker.revised_score or speaker.score) + sum(factor_delta.values()), 0, 1))
        revised_confidence = float(np.clip((speaker.revised_confidence or speaker.confidence) + confidence_delta, 0.2, 0.98))
        return DebateRound(
            round_name=f"第 {turn_index + 1} 轮发言",
            speaker=speaker.master,
            opponent=opponent.master,
            target_symbol=speaker.symbol,
            stance=speaker.action,
            argument=self._argument(turn_index, speaker, opponent, attack_strength, defense_strength, transcript),
            attack_strength=round(attack_strength, 3),
            defense_strength=round(defense_strength, 3),
            confidence_delta=round(confidence_delta, 3),
            factor_delta={key: round(value, 3) for key, value in factor_delta.items()},
            revised_score=round(revised_score, 3),
            revised_confidence=round(revised_confidence, 3),
            style_distance=round(style_distance, 3),
        )

    def _style_distance(self, left: MasterOpinion, right: MasterOpinion) -> float:
        keys = sorted(set(left.style_prior) | set(right.style_prior))
        a = np.array([left.style_prior.get(key, 0) for key in keys], dtype=float)
        b = np.array([right.style_prior.get(key, 0) for key in keys], dtype=float)
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.clip(1 - float(np.dot(a, b) / denom), 0, 1))

    def _attack_strength(self, speaker: MasterOpinion, opponent: MasterOpinion, style_distance: float, transcript: list[str]) -> float:
        score_gap = abs((speaker.revised_score or speaker.score) - (opponent.revised_score or opponent.score))
        action_gap = 0.18 if speaker.action != opponent.action else 0
        transcript_pressure = min(len(transcript), 8) * 0.012
        return float(np.clip(0.28 + style_distance * 0.26 + score_gap * 0.34 + action_gap + transcript_pressure, 0.08, 0.95))

    def _defense_strength(self, speaker: MasterOpinion, opponent: MasterOpinion, transcript: list[str]) -> float:
        factor_values = list((speaker.preferred_factors or speaker.visible_factors).values()) or [0.5]
        style_conviction = abs((speaker.revised_score or speaker.score) - 0.5)
        confidence_edge = max((speaker.revised_confidence or speaker.confidence) - (opponent.revised_confidence or opponent.confidence), -0.25)
        fatigue = min(len(transcript), 12) * 0.006
        return float(np.clip(0.26 + np.mean(factor_values) * 0.32 + style_conviction * 0.22 + confidence_edge * 0.22 - fatigue, 0.08, 0.95))

    def _confidence_delta(self, attack_strength: float, defense_strength: float, speaker: MasterOpinion) -> float:
        raw = (defense_strength - attack_strength) * 0.13
        if attack_strength > 0.72 and defense_strength < 0.52:
            raw -= 0.018
        return float(np.clip(raw, -0.085, 0.075))

    def _factor_delta(self, speaker: MasterOpinion, attack_strength: float, defense_strength: float) -> dict[str, float]:
        net = defense_strength - attack_strength
        factors = speaker.preferred_factors or speaker.visible_factors or speaker.factors
        if not factors:
            return {}
        sorted_factors = sorted(factors.items(), key=lambda item: item[1], reverse=True)
        primary = sorted_factors[0][0]
        secondary = sorted_factors[1][0] if len(sorted_factors) > 1 else primary
        return {
            primary: float(np.clip(net * 0.026, -0.035, 0.032)),
            secondary: float(np.clip(net * 0.014, -0.02, 0.018)),
        }

    def _apply_revision(self, speaker: MasterOpinion, debate_round: DebateRound) -> None:
        speaker.revised_score = debate_round.revised_score
        speaker.revised_confidence = debate_round.revised_confidence

    def _argument(
        self,
        turn_index: int,
        speaker: MasterOpinion,
        opponent: MasterOpinion,
        attack_strength: float,
        defense_strength: float,
        transcript: list[str],
    ) -> str:
        llm_argument = self._llm_argument(turn_index, speaker, opponent, attack_strength, defense_strength, transcript)
        if llm_argument:
            return llm_argument
        tone = self._tone(attack_strength, defense_strength)
        preferred = sorted((speaker.preferred_factors or speaker.visible_factors).items(), key=lambda item: item[1], reverse=True)[:3]
        evidence = "、".join(f"{key}={value:.2f}" for key, value in preferred)
        prior_note = "在听取前序发言后，" if transcript else ""
        return (
            f"{prior_note}{speaker.master} 仍以{tone}立场看待 {speaker.symbol}。"
            f"其核心依据集中在 {evidence}，因此对 {opponent.master} 的不同判断保持反驳："
            f"分歧可以提示风险，但不足以推翻该风格下的主判断。"
        )

    def _tone(self, attack_strength: float, defense_strength: float) -> str:
        if defense_strength - attack_strength > 0.12:
            return "较坚定的"
        if attack_strength - defense_strength > 0.2:
            return "有所保留但不退让的"
        return "审慎而坚定的"

    def _llm_argument(
        self,
        turn_index: int,
        speaker: MasterOpinion,
        opponent: MasterOpinion,
        attack_strength: float,
        defense_strength: float,
        transcript: list[str],
    ) -> str | None:
        if not self.llm.enabled:
            return None
        tone = self._tone(attack_strength, defense_strength)
        prompt = (
            "请生成多 Agent 投资辩论中的一轮中文发言。"
            "要求：70-130字，只输出最终发言，不输出思考过程；不得输出 attack_strength、defense_strength、"
            "confidence_delta、factor_delta 等数值；发言者可以看到全部因子和此前所有发言，"
            "但必须坚定地基于自己的投资风格回应、反驳或补充。"
            f"语气要求：{tone}。\n"
            f"第几次发言：{turn_index + 1}\n"
            f"发言者：{speaker.master}\n股票：{speaker.symbol}\n"
            f"发言者立场/修正评分/修正信心：{speaker.action}/{speaker.revised_score or speaker.score}/{speaker.revised_confidence or speaker.confidence}\n"
            f"全部因子：{speaker.visible_factors}\n"
            f"发言者风格优先证据：{speaker.preferred_factors}\n"
            f"主要反驳对象：{opponent.master}/{opponent.action}\n"
            f"此前发言记录：{transcript[-10:]}"
        )
        try:
            return self.llm.complete(
                [
                    LLMMessage(role="system", content=speaker.system_prompt or "你是A股多Agent系统中的结构化辩论代理。"),
                    LLMMessage(role="user", content=prompt),
                ],
                temperature=0.36,
            )
        except Exception:
            return None
