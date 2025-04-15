# models/account_move_workflow.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


class AccountMoveWorkflow(models.Model):
    _name = 'account.move.workflow'
    _description = 'Accounting Workflow Template'
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(required=True, string='Workflow Name', index=True)
    code = fields.Char(string='Reference Code', index=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        comodel_name='res.company', 
        string='Company', 
        default=lambda self: self.env.company,
        index=True
    )
    partner_required = fields.Boolean(
        string='Partner Required',
        default=False,
        help='If checked, a partner will be required when executing this workflow'
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency', 
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        help='Default currency for this workflow'
    )
    note = fields.Text(string='Description')
    workflow_template_ids = fields.One2many(
        comodel_name='account.move.workflow.template',
        inverse_name='workflow_id',
        string='Template Lines',
        copy=True
    )
    generated_move_ids = fields.One2many(
        comodel_name='account.move',
        inverse_name='workflow_id',
        string='Generated Journal Entries',
        copy=False
    )
    generated_move_count = fields.Integer(
        string='Moves',
        compute='_compute_generated_move_count',
        store=True
    )

    @api.depends('generated_move_ids')
    def _compute_generated_move_count(self):
        for record in self:
            record.generated_move_count = len(record.generated_move_ids)

    def action_view_moves(self):
        self.ensure_one()
        action = self.env.ref('account.action_move_journal_line').read()[0]
        if self.generated_move_ids:
            action.update({
                'domain': [('id', 'in', self.generated_move_ids.ids)],
                'context': {'create': False}
            })
        return action
        
    def action_open_wizard(self):
        self.ensure_one()
        return {
            'name': _('Execute Workflow: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.workflow.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_workflow_id': self.id,
                'default_company_id': self.company_id.id,
                'default_currency_id': self.currency_id.id,
            }
        }
        
    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {})
        default.update(name=_("%s (copy)") % self.name)
        if self.code:
            default.update(code=_("%s (copy)") % self.code)
        return super().copy(default)