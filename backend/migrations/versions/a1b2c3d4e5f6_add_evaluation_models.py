"""add evaluation models

Revision ID: a1b2c3d4e5f6
Revises: 76888bd3ee87
Create Date: 2026-10-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '76888bd3ee87'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('topics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('slug', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['parent_id'], ['topics.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_topics_name'), 'topics', ['name'], unique=True)
    op.create_table('evaluations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=False),
        sa.Column('correctness_score', sa.Float(), nullable=True),
        sa.Column('approach_score', sa.Float(), nullable=True),
        sa.Column('complexity_score', sa.Float(), nullable=True),
        sa.Column('optimization_score', sa.Float(), nullable=True),
        sa.Column('coverage_score', sa.Float(), nullable=True),
        sa.Column('overall_score', sa.Float(), nullable=True),
        sa.Column('time_complexity', sa.String(length=50), nullable=True),
        sa.Column('space_complexity', sa.String(length=50), nullable=True),
        sa.Column('detected_patterns', sa.Text(), nullable=True),
        sa.Column('detected_topics', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('submission_id')
    )
    op.create_index(op.f('ix_evaluations_submission_id'), 'evaluations', ['submission_id'], unique=True)
    op.create_table('skill_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('topic_id', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('problems_seen', sa.Integer(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'topic_id', name='uq_skill_user_topic')
    )
    op.create_index(op.f('ix_skill_scores_user_id'), 'skill_scores', ['user_id'], unique=False)
    op.create_table('ai_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('model_used', sa.String(length=120), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('submissions_hash', sa.String(length=64), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_reports_user_id'), 'ai_reports', ['user_id'], unique=False)
    op.create_table('user_goals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('goal_type', sa.String(length=60), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('daily_target_minutes', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )


def downgrade():
    op.drop_table('user_goals')
    op.drop_index(op.f('ix_ai_reports_user_id'), table_name='ai_reports')
    op.drop_table('ai_reports')
    op.drop_index(op.f('ix_skill_scores_user_id'), table_name='skill_scores')
    op.drop_table('skill_scores')
    op.drop_index(op.f('ix_evaluations_submission_id'), table_name='evaluations')
    op.drop_table('evaluations')
    op.drop_index(op.f('ix_topics_name'), table_name='topics')
    op.drop_table('topics')
