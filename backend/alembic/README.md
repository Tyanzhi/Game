# WORLD ENGINE database migrations

Run Alembic from `backend` after installing `requirements.txt`.
Set `DATABASE_URL` to the same async SQLAlchemy URL used by the API, then run:

```sh
alembic upgrade head
```

Revision `0003_runtime_state` merges the two historical heads and adds the
runtime tables and fields used by the simulation. The `0002_relations` revision
is retained as a no-op because its tables already exist in `0001_world_state`.
Existing databases at `0002_actor_decision_engine` are upgraded in place.

CI tests an empty database and an upgrade with an existing actor, repeated
upgrades, a three-tick simulation, snapshot hashes, and downgrade to base on
SQLite and a disposable PostgreSQL database. To run the same tests locally:

```sh
pip install -r requirements.txt -r app/requirements-dev.txt
PYTHONPATH=.:.. pytest -q . ../simulation
```

`MIGRATION_TEST_DATABASE_URL` must point only to a disposable test database:
the migration tests downgrade it to base. Leave it unset to use temporary SQLite
files. Databases previously created directly with `metadata.create_all()` need
schema inspection and an appropriate Alembic baseline before using migrations;
do not blindly stamp them or apply the initial migration over existing tables.
