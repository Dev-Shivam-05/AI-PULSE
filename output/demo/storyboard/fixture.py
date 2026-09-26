"""v3-G.1 demo fixture: a narration that exercises all 7 templates, and a hand-written
board standing in for the model's answer (no Gemini key exists locally)."""

NARRATION = (
    "Your phone already does what ChatGPT does. "
    "Type I'll be there in five, and your keyboard suggests minutes. "
    "A language model does the same thing, one word at a time, for a whole essay. "
    "GPT-4 was trained on about 13 trillion tokens. "
    "Small models run on your laptop, big models need a data center. "
    "In one test, the top suggestion was right 71 percent of the time, the second 12 percent, the third 4 percent. "
    "According to the paper, prediction is all it does, and that is the surprising part."
)

RAW = {"beats": [
    {"cue": "Your phone", "template": "statement",
     "slots": {"line": {"text": "Your phone already does this", "cue": "Your"}, "accent": "phone"}},
    {"cue": "Type", "template": "chat",
     "slots": {"user": {"text": "I'll be there in five", "cue": "Type"},
               "ai": {"text": "minutes", "cue": "minutes"}}},
    {"cue": "A language", "template": "steps",
     "slots": {"steps": [{"text": "one word", "cue": "one word"},
                         {"text": "at a time", "cue": "at a"},
                         {"text": "a whole essay", "cue": "whole"}]}},
    {"cue": "GPT-4 was", "template": "number",
     "slots": {"value": {"text": "13 trillion", "cue": "13"},
               "label": {"text": "tokens it was trained on", "cue": "tokens"}}},
    {"cue": "Small models", "template": "compare",
     "slots": {"left": [{"text": "Small models", "cue": "Small"}, {"text": "run on your laptop", "cue": "laptop"}],
               "right": [{"text": "Big models", "cue": "big"}, {"text": "need a data center", "cue": "data"}]}},
    {"cue": "In one test", "template": "bars",
     "slots": {"bars": [{"label": {"text": "top suggestion", "cue": "top"}, "value": "71%"},
                        {"label": {"text": "second", "cue": "second"}, "value": "12%"},
                        {"label": {"text": "third", "cue": "third"}, "value": "4%"}]}},
    {"cue": "According to", "template": "headline",
     "slots": {"line": {"text": "prediction is all it does", "cue": "prediction"}, "accent": "prediction"}},
]}


def uniform_words(text: str, per_word: float = 0.38, pause: float = 0.25):
    out, t = [], 0.0
    for w in text.split():
        out.append((round(t, 3), round(t + per_word * 0.9, 3), w))
        t += per_word + (pause if w[-1] in ".,?!" else 0.0)
    return out, round(t + 0.3, 3)
