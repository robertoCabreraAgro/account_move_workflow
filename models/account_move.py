from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    workflow_id = fields.Many2one(
        'account.move.workflow',
        string='Generated from Workflow',
        readonly=True,
        copy=False
    )
    related_move_ids = fields.Many2many(
        'account.move',
        'account_move_workflow_rel',
        'move_id',
        'related_move_id',
        string='Related Moves',
        help='Moves related to this one in the same workflow execution',
        readonly=True
    )
    workflow_sequence = fields.Integer(
        string='Workflow Sequence',
        help='Position in the workflow execution',
        readonly=True
    )
    
    def action_run_workflow(self):
        """Open wizard to run workflow based on this move"""
        return {
            'name': _('Run Workflow'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.workflow.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_source_move_id': self.id,
                'default_company_id': self.company_id.id,
                'default_partner_id': self.partner_id.id,
                'default_currency_id': self.currency_id.id,
                'default_amount': self.amount_total,
                'default_date': self.date,
            }
        }