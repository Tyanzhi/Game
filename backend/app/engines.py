from dataclasses import dataclass
@dataclass
class Result:
    changes: dict

def _run(actors): return {aid:Result({}) for aid in actors}
economic=_run
social=_run
conflict=_run
energy=_run
