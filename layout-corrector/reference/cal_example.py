import lfengine as L
from lfengine import logit
RU_ALLOW = "на не но да по из за то ты мы вы он ли ну во со до от ни же бы".split()
EN_ALLOW = "of to in is it on at as be by or an if so do go he we me my no up us".split()
def example_cal():
    thr = {d: {"3-4": logit(0.999), "5-7": logit(0.997), "8+": logit(0.995)} for d in ("en2ru", "ru2en")}
    return {
        "temperature": {"network": 1.0, "ngram": 1.0},
        "pi_train": [0.38, 0.40, 0.22],
        "o_lat": 0.25,
        "w": {a: {"default": 0.01, "after_switch": 0.003, "run": 0.25} for a in ("en", "ru")},
        "lambda_nats": {"network": thr, "ngram": thr},
        "two_key_allow": {"en2ru": set(RU_ALLOW), "ru2en": set(EN_ALLOW)},
    }
