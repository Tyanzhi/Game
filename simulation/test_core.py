from simulation.core import ActorState, Event, SimulationEngine, WorldState


def test_event_and_tick_preserve_bounds():
    world = WorldState(actors={"actor-a": ActorState("actor-a")})
    engine = SimulationEngine(seed=1)
    engine.apply_event(
        world,
        Event("evt-1", "economic", ["actor-a"], {"stability": -0.2, "domestic_pressure": 0.1}),
    )
    engine.tick(world)
    actor = world.actors["actor-a"]
    assert 0.0 <= actor.stability <= 1.0
    assert 0.0 <= actor.domestic_pressure <= 1.0
    assert world.tick == 1
