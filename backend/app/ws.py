from fastapi import WebSocket
from typing import Any
class ConnectionHub:
    def __init__(self): self.connections: dict[str,set[WebSocket]] = {}
    async def connect(self, simulation_id:str, ws:WebSocket):
        await ws.accept(); self.connections.setdefault(simulation_id,set()).add(ws)
    def disconnect(self, simulation_id:str, ws:WebSocket):
        group=self.connections.get(simulation_id,set()); group.discard(ws)
        if not group: self.connections.pop(simulation_id,None)
    async def broadcast(self, simulation_id:str, payload:Any):
        dead=[]
        for ws in list(self.connections.get(simulation_id,set())):
            try: await ws.send_json(payload)
            except Exception: dead.append(ws)
        for ws in dead: self.disconnect(simulation_id,ws)
