"""Unit tests for SQLAlchemy declarative ORM models and metadata."""

import uuid
from trace.infrastructure.database.models import Base, ProjectOrm, RepositoryOrm

from sqlalchemy import create_engine


def test_orm_models_table_metadata() -> None:
    """Verify ORM table names, constraints, and column metadata."""
    assert ProjectOrm.__tablename__ == "projects"
    assert RepositoryOrm.__tablename__ == "repositories"

    tables = Base.metadata.tables
    assert "projects" in tables
    assert "repositories" in tables

    # Projects table checks
    projects_table = tables["projects"]
    assert "id" in projects_table.c
    assert "name" in projects_table.c
    assert "status" in projects_table.c
    assert projects_table.c.name.unique is True

    # Repositories table checks
    repos_table = tables["repositories"]
    assert "id" in repos_table.c
    assert "project_id" in repos_table.c
    assert "type" in repos_table.c
    assert "location" in repos_table.c
    assert "last_analysis_run_id" in repos_table.c

    # Check composite unique constraint uq_project_location
    constraint_names = [c.name for c in repos_table.constraints]
    assert "uq_project_location" in constraint_names

    # Check foreign key to projects.id without cascade delete
    fk = list(repos_table.c.project_id.foreign_keys)[0]
    assert fk.target_fullname == "projects.id"
    assert fk.ondelete is None or fk.ondelete.upper() != "CASCADE"


def test_orm_models_instantiation() -> None:
    """Verify ORM models instantiate and map relationships cleanly."""
    p_id = uuid.uuid4()
    project = ProjectOrm(
        id=p_id,
        name="ORM Project",
        description="Testing ORM mapping",
        status="ACTIVE",
    )
    assert project.id == p_id
    assert project.name == "ORM Project"

    r_id = uuid.uuid4()
    repo = RepositoryOrm(
        id=r_id,
        project_id=p_id,
        type="LOCAL",
        location="/repos/test",
        default_branch="main",
        status="REGISTERED",
    )
    assert repo.id == r_id
    assert repo.project_id == p_id
    assert repo.last_analysis_run_id is None


def test_orm_schema_creation_in_sqlite() -> None:
    """Verify that Base.metadata can create all tables cleanly in SQLite."""
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as conn:
            assert conn is not None
        Base.metadata.drop_all(engine)
    finally:
        engine.dispose()
