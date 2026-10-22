from .._imports import *
from .logger import *
from .constants import *
class KeyHeavenRNG:
    """Local RNG factory. Never shares global random state between tools."""

    @staticmethod
    def resolve_seed(context=None, seed_override=None):
        if seed_override is not None:
            return int(seed_override)
        try:
            props = context.scene.keyheaven
            seed = int(getattr(props, "random_seed", -1))
            if seed >= 0:
                return seed
        except Exception:
            pass
        return None

    @classmethod
    def create(cls, context=None, seed_override=None):
        seed = cls.resolve_seed(context, seed_override)
        return random.Random(seed)

    @classmethod
    def seed_label(cls, context=None, seed_override=None):
        seed = cls.resolve_seed(context, seed_override)
        return "system" if seed is None else str(seed)
