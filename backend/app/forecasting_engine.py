"""Small deterministic ensemble forecaster for simulation state variables."""
from __future__ import annotations
import hashlib

def clamp(v): return max(0.0,min(1.0,float(v)))

def forecast(target:str,state:dict,drivers:dict,horizon:int=5,seed:int=1)->dict:
    base=clamp(state.get(target.split(':')[-1],state.get('stability',.5)))
    signal=sum(float(v) for v in drivers.values())
    digest=int(hashlib.sha256(f'{target}:{seed}'.encode()).hexdigest()[:8],16)/0xffffffff
    drift=max(-.15,min(.15,signal*.08+(digest-.5)*.02))
    p_high=clamp(base+drift); p_low=clamp(1-p_high); p_mid=clamp(1-abs(p_high-p_low))
    total=p_low+p_mid+p_high
    return {'target':target,'horizon':int(horizon),'probabilities':{'low':p_low/total,'medium':p_mid/total,'high':p_high/total},'drivers':list(drivers),'uncertainty':clamp(.35+abs(signal)*.08),'model_version':'forecast-v1'}
