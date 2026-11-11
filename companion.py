"""Small fictional scene state, committed only when an utterance is played."""
from dataclasses import dataclass
import re
import unicodedata

LABELS = {'slacking': '摸鱼', 'working': '假装忙', 'eating': '干饭'}
TRIGGERS = (
    ('boss', ('老板来了', '老板来啦', '我是老板'), 'working', 2),
    ('meal', ('开饭了', '吃饭了', '干饭了'), 'eating', 3),
    ('nudge', ('别偷懒', '不许摸鱼', '认真工作'), 'working', 2),
)


@dataclass(frozen=True)
class ScenePlan:
    activity: str
    remaining_turns: int
    trigger: str | None = None

    def context(self):
        return {'activity': self.activity, 'label': LABELS[self.activity],
                'remaining_turns': self.remaining_turns, 'trigger': self.trigger}


class CompanionScene:
    def __init__(self):
        self.reset()

    def reset(self):
        self.activity, self.remaining_turns = 'slacking', 0

    def plan(self, text=None):
        text = unicodedata.normalize('NFKC', text or '').strip()
        text = re.sub(r'^(?:大肥鱼|小鱼|鱼鱼|肥鱼)[,，!！:：\s]*', '', text)
        for trigger, phrases, activity, duration in TRIGGERS:
            if any(text.startswith(phrase) for phrase in phrases):
                return ScenePlan(activity, duration, trigger)
        return ScenePlan(self.activity, self.remaining_turns)

    def started(self, plan):
        self.activity, self.remaining_turns = plan.activity, plan.remaining_turns

    def completed(self, plan):
        if not plan.trigger and self.remaining_turns:
            self.remaining_turns -= 1
            if not self.remaining_turns:
                self.reset()

    def snapshot(self):
        return {'activity': self.activity, 'label': LABELS[self.activity],
                'remaining_turns': self.remaining_turns}
