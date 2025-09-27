"""Add invoices table with reconciliation

Revision ID: 002_add_invoices
Revises: 001_initial_tables
Create Date: 2025-01-27 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '002_add_invoices'
down_revision = '001_initial_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add invoices table with JSONB items and reconciliation support."""
    
    # Create invoice status enum
    invoice_status_enum = postgresql.ENUM(
        'draft', 'issued', 'paid', 'overdue',
        name='invoicestatus'
    )
    invoice_status_enum.create(op.get_bind())
    
    # Create invoices table
    op.create_table('invoices',
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        
        # Foreign keys
        sa.Column('account_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('matched_transaction_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Invoice identification
        sa.Column('invoice_number', sa.String(length=50), nullable=False),
        
        # Client information
        sa.Column('client_name', sa.String(length=255), nullable=False),
        sa.Column('client_phone', sa.String(length=20), nullable=False),
        
        # Line items as JSONB
        sa.Column('items', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        
        # Financial amounts
        sa.Column('subtotal', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('tax', sa.Numeric(precision=15, scale=2), nullable=False, default=0.00),
        sa.Column('total', sa.Numeric(precision=15, scale=2), nullable=False),
        
        # Status and tracking
        sa.Column('status', invoice_status_enum, nullable=False, default='draft'),
        sa.Column('pdf_url', sa.Text(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reconciled_at', sa.DateTime(timezone=True), nullable=True),
        
        # Additional fields
        sa.Column('notes', sa.Text(), nullable=True),
        
        # Constraints
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['matched_transaction_id'], ['transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for performance
    op.create_index('ix_invoices_invoice_number', 'invoices', ['invoice_number'], unique=True)
    op.create_index('ix_invoices_account_id', 'invoices', ['account_id'])
    op.create_index('ix_invoices_status', 'invoices', ['status'])
    op.create_index('ix_invoices_due_date', 'invoices', ['due_date'])
    op.create_index('ix_invoices_created_at', 'invoices', ['created_at'])
    op.create_index('ix_invoices_client_name', 'invoices', ['client_name'])
    op.create_index('ix_invoices_matched_transaction_id', 'invoices', ['matched_transaction_id'])
    
    # Create GIN index for JSONB items column for efficient querying
    op.create_index('ix_invoices_items_gin', 'invoices', ['items'], postgresql_using='gin')


def downgrade() -> None:
    """Remove invoices table and related indexes."""
    
    # Drop indexes
    op.drop_index('ix_invoices_items_gin', table_name='invoices')
    op.drop_index('ix_invoices_matched_transaction_id', table_name='invoices')
    op.drop_index('ix_invoices_client_name', table_name='invoices')
    op.drop_index('ix_invoices_created_at', table_name='invoices')
    op.drop_index('ix_invoices_due_date', table_name='invoices')
    op.drop_index('ix_invoices_status', table_name='invoices')
    op.drop_index('ix_invoices_account_id', table_name='invoices')
    op.drop_index('ix_invoices_invoice_number', table_name='invoices')
    
    # Drop table
    op.drop_table('invoices')
    
    # Drop enum
    sa.Enum(name='invoicestatus').drop(op.get_bind(), checkfirst=True)