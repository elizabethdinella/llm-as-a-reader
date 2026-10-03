from enum import Enum
import consts
import os
from consts import Mode

class Sample:
    def __init__(self, scores, p_scores, model, answer_trial, score_trial, sample_num):
        self.scores = scores #dict of ITEM -> true/false (true means deducted)
        self.p_scores = p_scores
        self.model  = model
        self.answer_trial = answer_trial
        self.score_trial = score_trial

        self.sample_num = str(sample_num)

        if consts.get_mode() == Mode.RDB:
            self.f_submission = os.path.join(consts.get_answer_dir(), model, self.sample_num, f"t{answer_trial}.txt")
        elif consts.get_mode() == Mode.APCS:
             self.f_submission = os.path.join(consts.get_answer_dir(), model, f"answer_{answer_trial}.txt")
        else:
            assert False

    def __str__(self):
        return self.model + ": " + self.answer_trial + "; Score trial: " + self.score_trial + " -> " + str(self.scores)

    def __eq__(self, other):
        return self.model == other.model and self.answer_trial == other.answer_trial
    
    def key(self):
        return self.model + " " + self.answer_trial

    def to_dict(self):
        return {
            "scores": self.scores,
            "p_scores": self.p_scores,
            "model": self.model,
            "answer_trial": self.answer_trial,
            "score_trial": self.score_trial,
            "sample_num": consts.sample_num
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["scores"], d["p_scores"], d["model"], d["answer_trial"], d["score_trial"], d.get("sample_num", str(["sample_num"])))

class Ambiguity:
    def __init__(self, _id, name, side_a, side_b):
        self.id = _id
        self.name = name
        self.status = Status.UNTOUCHED
        self.r_item = self.id.split("_")[0]
        self.side_a = side_a
        self.side_b = side_b
        self.resolvers = []
    
    def is_resolved(self):
        return self.status == Status.SIDE_A or self.status == Status.SIDE_B 

    def __eq__(self, other):
       return self.id == other.id 

    def __hash__(self):
        return hash(self.id)

    def _block(self, label, text):
      return f"  {label}: {text}"

    def __str__(self):
        return "\n".join([
            f"[{self.id}] rubric item {self.r_item}: {self.name}",
            self._block("Side A", self.side_a),
            self._block("Side B", self.side_b),
            f"  Status: {self.status.name}",
        ]) 

    def resolved_str(self):
        assert self.is_resolved()

        winning_side = self.side_a if self.status == Status.SIDE_A else self.side_b

        return (
            f"[{self.id}] {self.name}\n"
            f"     {winning_side}\n"
        )

    def __repr__(self):
        return f"Ambiguity({self.id}, {self.status.name})"


    def to_dict(self):
        return {"id": self.id, "name": self.name,
            "side_a": self.side_a, "side_b": self.side_b}


    @classmethod
    def from_dict(cls, d):
        return cls(d["id"], d["name"], d["side_a"], d["side_b"])

class Status(Enum):
    SIDE_A = 1
    SIDE_B = 2
    CONFLICT = 3
    UNTOUCHED = 4 
