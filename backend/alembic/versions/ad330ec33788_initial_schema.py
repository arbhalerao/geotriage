"""
initial schema

the whole schema in one migration: workflows and their results, the STAC scene cache,
the Postgres job queue, and the registered models and providers

Revision ID: ad330ec33788
Revises:
Create Date: 2026-09-12 22:37:31.076803
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ad330ec33788'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_geospatial_table('aois',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('geometry', Geometry(srid=4326, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_geospatial_index('idx_aois_geometry', 'aois', ['geometry'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_geospatial_index('ix_aois_geometry', 'aois', ['geometry'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_table('job_groups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('pending_count', sa.Integer(), nullable=False),
    sa.Column('on_complete_task', sa.String(), nullable=True),
    sa.Column('on_complete_args', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('on_complete_priority', sa.Integer(), nullable=False),
    sa.Column('on_complete_enqueued', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('recurring_jobs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('task_name', sa.String(), nullable=False),
    sa.Column('args', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('interval_seconds', sa.Integer(), nullable=False),
    sa.Column('next_run_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_name')
    )
    op.create_table('registered_models',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(), nullable=False),
    sa.Column('image', sa.String(), nullable=False),
    sa.Column('descriptor', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('admission', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index('ix_registered_models_enabled', 'registered_models', ['is_enabled'], unique=False)
    op.create_table('registered_providers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(), nullable=False),
    sa.Column('image', sa.String(), nullable=False),
    sa.Column('descriptor', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('admission', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index('ix_registered_providers_enabled', 'registered_providers', ['is_enabled'], unique=False)
    op.create_table('provider_collections',
    sa.Column('collection_slug', sa.String(), nullable=False),
    sa.Column('provider_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['provider_id'], ['registered_providers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('collection_slug')
    )
    op.create_index('ix_provider_collections_provider', 'provider_collections', ['provider_id'], unique=False)
    op.create_geospatial_table('stac_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('collection_slug', sa.String(), nullable=False),
    sa.Column('stac_item_id', sa.String(), nullable=False),
    sa.Column('geometry', Geometry(srid=4326, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('bbox', postgresql.ARRAY(sa.Float()), nullable=True),
    sa.Column('datetime', sa.DateTime(timezone=True), nullable=False),
    sa.Column('properties', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('assets', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('cloud_cover', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('collection_slug', 'stac_item_id', name='uq_stac_items_collection_item')
    )
    op.create_geospatial_index('idx_stac_items_geometry', 'stac_items', ['geometry'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_index('ix_stac_items_cloud_cover', 'stac_items', ['cloud_cover'], unique=False)
    op.create_index('ix_stac_items_collection_datetime', 'stac_items', ['collection_slug', 'datetime'], unique=False)
    op.create_geospatial_index('ix_stac_items_geometry', 'stac_items', ['geometry'], unique=False, postgresql_using='gist', postgresql_ops={})
    op.create_table('jobs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('task_name', sa.String(), nullable=False),
    sa.Column('args', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.Enum('blocked', 'ready', 'running', 'succeeded', 'failed', 'dead', 'skipped', name='jobstatus', native_enum=False, length=12), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('run_after', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('depends_on', postgresql.ARRAY(sa.UUID()), server_default='{}', nullable=False),
    sa.Column('group_id', sa.UUID(), nullable=True),
    sa.Column('locked_by', sa.String(), nullable=True),
    sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['group_id'], ['job_groups.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jobs_claim', 'jobs', ['priority', 'run_after'], unique=False, postgresql_where=sa.text("status = 'ready'"))
    op.create_index('ix_jobs_depends_on', 'jobs', ['depends_on'], unique=False, postgresql_using='gin')
    op.create_index('ix_jobs_group_id', 'jobs', ['group_id'], unique=False)
    op.create_index('ix_jobs_lease', 'jobs', ['locked_until'], unique=False, postgresql_where=sa.text("status = 'running'"))
    op.create_table('workflows',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('aoi_id', sa.UUID(), nullable=False),
    sa.Column('aoi_filter_mode', sa.String(), server_default='intersects', nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('time_mode', sa.Enum('historical', 'fixed_future', name='timemode', native_enum=False, length=20), nullable=False),
    sa.Column('time_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('time_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('poll_interval_minutes', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('draft', 'running', 'completed', 'completed_with_errors', 'failed', name='workflowstatus', native_enum=False, length=30), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('time_end > time_start', name='ck_workflows_time_range'),
    sa.ForeignKeyConstraint(['aoi_id'], ['aois.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workflows_aoi_id', 'workflows', ['aoi_id'], unique=False)
    op.create_index('ix_workflows_status', 'workflows', ['status'], unique=False)
    op.create_table('workflow_collections',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('collection_slug', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_id', 'collection_slug', name='uq_workflow_collections_workflow_collection')
    )
    op.create_table('workflow_items',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('stac_item_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('queued', 'screening', 'screened_out', 'fetching', 'uploading', 'scoring', 'processed', 'fetch_failed', 'upload_failed', 'score_failed', 'failed', name='workflowitemstatus', native_enum=False, length=20), nullable=False),
    sa.Column('overall_severity', sa.Enum('green', 'yellow', 'red', name='severity', native_enum=False, length=10), nullable=True),
    sa.Column('discovered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['stac_item_id'], ['stac_items.id'], ),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_id', 'stac_item_id', name='uq_workflow_items_workflow_stac')
    )
    op.create_index('ix_workflow_items_stac_item_id', 'workflow_items', ['stac_item_id'], unique=False)
    op.create_index('ix_workflow_items_workflow_severity', 'workflow_items', ['workflow_id', 'overall_severity'], unique=False)
    op.create_index('ix_workflow_items_workflow_status', 'workflow_items', ['workflow_id', 'status'], unique=False)
    op.create_table('workflow_model_configs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('model_slug', sa.String(), nullable=False),
    sa.Column('user_label', sa.String(), nullable=True),
    sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_id', 'model_slug', name='uq_workflow_model_configs_workflow_model')
    )
    op.create_table('bookmarks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_item_id', sa.UUID(), nullable=False),
    sa.Column('notes', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workflow_item_id'], ['workflow_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bookmarks_workflow_item', 'bookmarks', ['workflow_item_id'], unique=False)
    op.create_table('model_runs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_item_id', sa.UUID(), nullable=False),
    sa.Column('workflow_model_config_id', sa.UUID(), nullable=False),
    sa.Column('model_slug', sa.String(), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'success', 'failed', 'skipped', name='modelrunstatus', native_enum=False, length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('raw_output', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['workflow_item_id'], ['workflow_items.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workflow_model_config_id'], ['workflow_model_configs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_item_id', 'workflow_model_config_id', name='uq_model_runs_item_config')
    )
    op.create_index('ix_model_runs_status', 'model_runs', ['status'], unique=False)
    op.create_index('ix_model_runs_workflow_item_id', 'model_runs', ['workflow_item_id'], unique=False)
    op.create_index('ix_model_runs_workflow_model_config_id', 'model_runs', ['workflow_model_config_id'], unique=False)
    op.create_table('threshold_configs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_model_config_id', sa.UUID(), nullable=False),
    sa.Column('score_name', sa.String(), nullable=False),
    sa.Column('green_min', sa.Float(), nullable=False),
    sa.Column('green_max', sa.Float(), nullable=False),
    sa.Column('yellow_min', sa.Float(), nullable=False),
    sa.Column('yellow_max', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['workflow_model_config_id'], ['workflow_model_configs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_model_config_id', 'score_name', name='uq_threshold_configs_config_score')
    )
    op.create_table('workflow_item_reviews',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_item_id', sa.UUID(), nullable=False),
    sa.Column('review_status', sa.Enum('new', 'reviewed', 'item_of_interest', 'dismissed', 'false_positive', 'needs_follow_up', name='reviewstatus', native_enum=False, length=30), nullable=False),
    sa.Column('notes', sa.String(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['workflow_item_id'], ['workflow_items.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_item_id', name='uq_workflow_item_reviews_item')
    )
    op.create_index('ix_workflow_item_reviews_item_status', 'workflow_item_reviews', ['workflow_item_id', 'review_status'], unique=False)
    op.create_table('workflow_model_collection_configs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('workflow_id', sa.UUID(), nullable=False),
    sa.Column('workflow_model_config_id', sa.UUID(), nullable=False),
    sa.Column('collection_slug', sa.String(), nullable=False),
    sa.Column('compatibility_level', sa.Enum('full', 'partial', 'incompatible', name='compatibilitylevel', native_enum=False, length=20), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['workflow_model_config_id'], ['workflow_model_configs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workflow_model_config_id', 'collection_slug', name='uq_wf_model_collection_config')
    )
    op.create_index('ix_wf_model_collection_configs_workflow_enabled', 'workflow_model_collection_configs', ['workflow_id', 'is_enabled'], unique=False)
    op.create_table('model_scores',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('model_run_id', sa.UUID(), nullable=False),
    sa.Column('score_name', sa.String(), nullable=False),
    sa.Column('score_value', sa.Float(), nullable=False),
    sa.Column('is_primary', sa.Boolean(), nullable=False),
    sa.Column('severity', sa.Enum('green', 'yellow', 'red', name='severity', native_enum=False, length=10), nullable=False),
    sa.ForeignKeyConstraint(['model_run_id'], ['model_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('model_run_id', 'score_name', name='uq_model_scores_run_name')
    )
    op.create_index('ix_model_scores_run_primary', 'model_scores', ['model_run_id', 'is_primary'], unique=False)
    op.create_index('ix_model_scores_run_severity', 'model_scores', ['model_run_id', 'severity'], unique=False)
    # the periodic monitoring sweep; without this row nothing ever checks whether a
    # fixed_future workflow is due
    op.execute(
        """
        INSERT INTO recurring_jobs (id, task_name, args, interval_seconds, enabled, priority)
        VALUES (gen_random_uuid(), 'check_due_workflows', '[]'::jsonb, 60, true, 0)
        """
    )


def downgrade() -> None:
    op.drop_index('ix_model_scores_run_severity', table_name='model_scores')
    op.drop_index('ix_model_scores_run_primary', table_name='model_scores')
    op.drop_table('model_scores')
    op.drop_index('ix_wf_model_collection_configs_workflow_enabled', table_name='workflow_model_collection_configs')
    op.drop_table('workflow_model_collection_configs')
    op.drop_index('ix_workflow_item_reviews_item_status', table_name='workflow_item_reviews')
    op.drop_table('workflow_item_reviews')
    op.drop_table('threshold_configs')
    op.drop_index('ix_model_runs_workflow_model_config_id', table_name='model_runs')
    op.drop_index('ix_model_runs_workflow_item_id', table_name='model_runs')
    op.drop_index('ix_model_runs_status', table_name='model_runs')
    op.drop_table('model_runs')
    op.drop_index('ix_bookmarks_workflow_item', table_name='bookmarks')
    op.drop_table('bookmarks')
    op.drop_table('workflow_model_configs')
    op.drop_index('ix_workflow_items_workflow_status', table_name='workflow_items')
    op.drop_index('ix_workflow_items_workflow_severity', table_name='workflow_items')
    op.drop_index('ix_workflow_items_stac_item_id', table_name='workflow_items')
    op.drop_table('workflow_items')
    op.drop_table('workflow_collections')
    op.drop_index('ix_workflows_status', table_name='workflows')
    op.drop_index('ix_workflows_aoi_id', table_name='workflows')
    op.drop_table('workflows')
    op.drop_index('ix_jobs_lease', table_name='jobs', postgresql_where=sa.text("status = 'running'"))
    op.drop_index('ix_jobs_group_id', table_name='jobs')
    op.drop_index('ix_jobs_depends_on', table_name='jobs', postgresql_using='gin')
    op.drop_index('ix_jobs_claim', table_name='jobs', postgresql_where=sa.text("status = 'ready'"))
    op.drop_table('jobs')
    op.drop_geospatial_index('ix_stac_items_geometry', table_name='stac_items', postgresql_using='gist', column_name='geometry')
    op.drop_index('ix_stac_items_collection_datetime', table_name='stac_items')
    op.drop_index('ix_stac_items_cloud_cover', table_name='stac_items')
    op.drop_geospatial_index('idx_stac_items_geometry', table_name='stac_items', postgresql_using='gist', column_name='geometry')
    op.drop_geospatial_table('stac_items')
    op.drop_index('ix_registered_models_enabled', table_name='registered_models')
    op.drop_table('registered_models')
    op.drop_index('ix_provider_collections_provider', table_name='provider_collections')
    op.drop_table('provider_collections')
    op.drop_index('ix_registered_providers_enabled', table_name='registered_providers')
    op.drop_table('registered_providers')
    op.drop_table('recurring_jobs')
    op.drop_table('job_groups')
    op.drop_geospatial_index('ix_aois_geometry', table_name='aois', postgresql_using='gist', column_name='geometry')
    op.drop_geospatial_index('idx_aois_geometry', table_name='aois', postgresql_using='gist', column_name='geometry')
    op.drop_geospatial_table('aois')
